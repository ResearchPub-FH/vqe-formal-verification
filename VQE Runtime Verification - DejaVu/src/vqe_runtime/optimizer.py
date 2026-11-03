"""Deterministic two-phase optimizer for monitored VQE experiments.

The optimizer in this module is deliberately small and transparent.  It uses a
bound-constrained coordinate pattern search and exposes the mutation boundary
needed by :class:`vqe_runtime.session.RuntimeSession`::

    next_theta, token = optimizer.preview_update(theta, energy)
    session.authorize_optimizer_update(next_theta)
    optimizer.commit_update(token, authorized_theta=next_theta)
    session.mark_optimizer_updated(next_theta)

``preview_update`` is side-effect free.  It computes a complete prospective
state transition and returns it in an authenticated, opaque token.
``commit_update`` is the sole method that changes optimizer state.  This makes
it possible for the runtime verifier to approve a proposed parameter vector
before the optimizer is permitted to adopt it.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
import secrets
from typing import Sequence


class OptimizerProtocolError(RuntimeError):
    """Base class for an invalid ask/tell optimizer operation."""


class InvalidUpdateToken(OptimizerProtocolError):
    """Raised when a token is malformed, foreign, or has been altered."""


class StaleUpdateToken(OptimizerProtocolError):
    """Raised when a valid token describes an optimizer state already passed."""


class ConsumedUpdateToken(OptimizerProtocolError):
    """Raised when the same update token is committed more than once."""


@dataclass(frozen=True, slots=True)
class _Transition:
    """Complete next state computed without mutating the optimizer."""

    source_generation: int
    evaluated_theta: tuple[float, ...]
    evaluated_energy: float
    next_theta: tuple[float, ...]
    incumbent_theta: tuple[float, ...]
    incumbent_energy: float
    active_move_index: int
    step_sizes: tuple[float, ...]
    sweep_improved: bool
    evaluation_count: int


@dataclass(frozen=True, slots=True, eq=False)
class _UpdateToken:
    """Private capability authorizing one prospective state transition."""

    owner: object
    transition: _Transition
    authentication_tag: bytes


def _finite_float(value: object, name: str) -> float:
    if isinstance(value, (bool, str, bytes)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _numeric_vector(
    value: float | Sequence[float], dimension: int, name: str
) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)):
        raise ValueError(f"{name} must be numeric or a length-{dimension} sequence")
    try:
        scalar = _finite_float(value, name)
    except (TypeError, ValueError):
        try:
            raw_values = tuple(value)  # type: ignore[arg-type]
        except TypeError as exc:
            raise ValueError(
                f"{name} must be numeric or a length-{dimension} sequence"
            ) from exc
        if len(raw_values) != dimension:
            raise ValueError(f"{name} has length {len(raw_values)}, expected {dimension}")
        return tuple(
            _finite_float(item, f"{name}[{index}]")
            for index, item in enumerate(raw_values)
        )
    return (scalar,) * dimension


class AskTellPatternSearch:
    """A deterministic, minimizing coordinate pattern-search optimizer.

    Parameters are polled one coordinate at a time.  For each coordinate the
    positive direction is tried first; the negative direction is tried only if
    the positive trial fails to improve the incumbent.  A successful trial
    becomes the new incumbent.  After a complete sweep with no improvement,
    all step sizes are multiplied by ``step_shrink``.

    The first call to :meth:`preview_update` supplies the initial evaluated
    point and energy.  Every later call must supply exactly the candidate that
    the preceding committed transition produced.  The class is intended for a
    sequential VQE loop; it is not a concurrent optimizer.

    Args:
        dimension: Number of variational parameters.
        lower_bounds: Scalar lower bound or one bound per parameter.
        upper_bounds: Scalar upper bound or one bound per parameter.
        initial_step: Positive scalar step or one step per parameter.
        step_shrink: Factor in ``(0, 1)`` applied after an unsuccessful sweep.
        improvement_tolerance: Minimum energy decrease required to accept a
            trial as the new incumbent.
    """

    def __init__(
        self,
        dimension: int,
        lower_bounds: float | Sequence[float],
        upper_bounds: float | Sequence[float],
        *,
        initial_step: float | Sequence[float] = 0.25,
        step_shrink: float = 0.5,
        improvement_tolerance: float = 0.0,
    ) -> None:
        if isinstance(dimension, bool) or not isinstance(dimension, int):
            raise ValueError("dimension must be a positive integer")
        if dimension <= 0:
            raise ValueError("dimension must be a positive integer")

        lower = _numeric_vector(lower_bounds, dimension, "lower_bounds")
        upper = _numeric_vector(upper_bounds, dimension, "upper_bounds")
        steps = _numeric_vector(initial_step, dimension, "initial_step")
        for index, (low, high) in enumerate(zip(lower, upper)):
            if low >= high:
                raise ValueError(
                    f"lower_bounds[{index}] must be less than upper_bounds[{index}]"
                )
        for index, step in enumerate(steps):
            if step <= 0.0:
                raise ValueError(f"initial_step[{index}] must be positive")

        shrink = _finite_float(step_shrink, "step_shrink")
        if not 0.0 < shrink < 1.0:
            raise ValueError("step_shrink must be strictly between zero and one")
        tolerance = _finite_float(
            improvement_tolerance, "improvement_tolerance"
        )
        if tolerance < 0.0:
            raise ValueError("improvement_tolerance must be nonnegative")

        self._dimension = dimension
        self._lower_bounds = lower
        self._upper_bounds = upper
        self._initial_step_sizes = steps
        self._step_shrink = shrink
        self._improvement_tolerance = tolerance

        # The owner marker rejects tokens from another optimizer.  The secret
        # authenticates transition contents, including when callers use
        # dataclasses.replace() on the otherwise-frozen token.
        self._owner = object()
        self._token_secret = secrets.token_bytes(32)
        self._consumed_tokens: set[_UpdateToken] = set()

        self._generation = 0
        self._evaluation_count = 0
        self._expected_theta: tuple[float, ...] | None = None
        self._incumbent_theta: tuple[float, ...] | None = None
        self._incumbent_energy: float | None = None
        self._active_move_index: int | None = None
        self._step_sizes = steps
        self._sweep_improved = False

    @property
    def dimension(self) -> int:
        """Number of optimizer parameters."""

        return self._dimension

    @property
    def generation(self) -> int:
        """Number of successfully committed transitions."""

        return self._generation

    @property
    def evaluation_count(self) -> int:
        """Number of evaluated points incorporated by committed transitions."""

        return self._evaluation_count

    @property
    def expected_theta(self) -> tuple[float, ...] | None:
        """Candidate that must be evaluated next, or ``None`` before startup."""

        return self._expected_theta

    @property
    def incumbent_theta(self) -> tuple[float, ...] | None:
        """Best committed parameter vector observed so far."""

        return self._incumbent_theta

    @property
    def incumbent_energy(self) -> float | None:
        """Best committed energy observed so far."""

        return self._incumbent_energy

    @property
    def step_sizes(self) -> tuple[float, ...]:
        """Coordinate step sizes in the current committed search state."""

        return self._step_sizes

    def preview_update(
        self, theta: Sequence[float], energy: float
    ) -> tuple[tuple[float, ...], object]:
        """Purely compute the next candidate and an opaque commit token.

        This method performs validation and allocation only; it never changes
        optimizer state.  Repeated calls with the same optimizer state and
        inputs therefore return the same ``next_theta``.  Only a token returned
        for the current generation can be passed to :meth:`commit_update`.
        """

        values = self._theta(theta)
        objective = _finite_float(energy, "energy")
        if self._expected_theta is not None and values != self._expected_theta:
            raise OptimizerProtocolError(
                "evaluated theta does not match the previously committed candidate"
            )

        if self._incumbent_theta is None:
            incumbent_theta = values
            incumbent_energy = objective
            step_sizes = self._step_sizes
            sweep_improved = False
            next_move_index = 0
        else:
            if self._incumbent_energy is None or self._active_move_index is None:
                raise OptimizerProtocolError("optimizer state is internally inconsistent")
            improved = (
                objective
                < self._incumbent_energy - self._improvement_tolerance
            )
            if improved:
                incumbent_theta = values
                incumbent_energy = objective
            else:
                incumbent_theta = self._incumbent_theta
                incumbent_energy = self._incumbent_energy

            step_sizes = self._step_sizes
            sweep_improved = self._sweep_improved or improved
            (
                next_move_index,
                step_sizes,
                sweep_improved,
            ) = self._advance_cursor(
                self._active_move_index,
                improved,
                step_sizes,
                sweep_improved,
            )

        (
            next_theta,
            active_move_index,
            step_sizes,
            sweep_improved,
        ) = self._next_feasible_candidate(
            incumbent_theta,
            next_move_index,
            step_sizes,
            sweep_improved,
        )
        transition = _Transition(
            source_generation=self._generation,
            evaluated_theta=values,
            evaluated_energy=objective,
            next_theta=next_theta,
            incumbent_theta=incumbent_theta,
            incumbent_energy=incumbent_energy,
            active_move_index=active_move_index,
            step_sizes=step_sizes,
            sweep_improved=sweep_improved,
            evaluation_count=self._evaluation_count + 1,
        )
        token = _UpdateToken(
            owner=self._owner,
            transition=transition,
            authentication_tag=self._authenticate(transition),
        )
        return next_theta, token

    def commit_update(
        self,
        token: object,
        *,
        authorized_theta: Sequence[float],
    ) -> None:
        """Atomically apply one previewed state transition.

        A token is valid only for the optimizer instance and generation that
        produced it.  Reuse, cross-instance use, post-preview alteration, and
        committing an alternate token after another transition won the race are
        all rejected before any state changes.
        """

        if not isinstance(token, _UpdateToken) or token.owner is not self._owner:
            raise InvalidUpdateToken("update token was not issued by this optimizer")
        if token in self._consumed_tokens:
            raise ConsumedUpdateToken("update token has already been committed")
        transition = token.transition
        expected_tag = self._authenticate(transition)
        if not hmac.compare_digest(token.authentication_tag, expected_tag):
            raise InvalidUpdateToken("update token contents were altered")
        if transition.source_generation != self._generation:
            raise StaleUpdateToken(
                "update token describes a stale optimizer generation"
            )
        approved = self._theta(authorized_theta)
        if approved != transition.next_theta:
            raise InvalidUpdateToken(
                "verifier-authorized theta does not match the token proposal"
            )

        # All checks precede this block.  This is the only post-construction
        # mutation point in the optimizer.
        self._consumed_tokens.add(token)
        self._generation += 1
        self._evaluation_count = transition.evaluation_count
        self._expected_theta = transition.next_theta
        self._incumbent_theta = transition.incumbent_theta
        self._incumbent_energy = transition.incumbent_energy
        self._active_move_index = transition.active_move_index
        self._step_sizes = transition.step_sizes
        self._sweep_improved = transition.sweep_improved

    def _theta(self, theta: Sequence[float]) -> tuple[float, ...]:
        if isinstance(theta, (str, bytes)):
            raise ValueError("theta must be a numeric sequence")
        try:
            raw_values = tuple(theta)
        except TypeError as exc:
            raise ValueError("theta must be a numeric sequence") from exc
        if len(raw_values) != self._dimension:
            raise ValueError(
                f"theta has length {len(raw_values)}, expected {self._dimension}"
            )
        values = tuple(
            _finite_float(value, f"theta[{index}]")
            for index, value in enumerate(raw_values)
        )
        for index, (value, low, high) in enumerate(
            zip(values, self._lower_bounds, self._upper_bounds)
        ):
            if not low <= value <= high:
                raise ValueError(
                    f"theta[{index}]={value!r} is outside [{low!r}, {high!r}]"
                )
        return values

    def _advance_cursor(
        self,
        active_move_index: int,
        improved: bool,
        step_sizes: tuple[float, ...],
        sweep_improved: bool,
    ) -> tuple[int, tuple[float, ...], bool]:
        coordinate = active_move_index // 2
        positive_direction = active_move_index % 2 == 0
        if positive_direction and not improved:
            return active_move_index + 1, step_sizes, sweep_improved

        coordinate += 1
        if coordinate < self._dimension:
            return 2 * coordinate, step_sizes, sweep_improved

        if not sweep_improved:
            step_sizes = tuple(step * self._step_shrink for step in step_sizes)
        return 0, step_sizes, False

    def _next_feasible_candidate(
        self,
        incumbent: tuple[float, ...],
        move_index: int,
        step_sizes: tuple[float, ...],
        sweep_improved: bool,
    ) -> tuple[tuple[float, ...], int, tuple[float, ...], bool]:
        # At least one direction is feasible because every bound interval is
        # strict.  The nextafter fallback also handles a step below one ULP.
        for _ in range(2 * self._dimension):
            coordinate = move_index // 2
            direction = 1.0 if move_index % 2 == 0 else -1.0
            candidate_value = incumbent[coordinate] + (
                direction * step_sizes[coordinate]
            )
            candidate_value = min(
                self._upper_bounds[coordinate],
                max(self._lower_bounds[coordinate], candidate_value),
            )
            if candidate_value == incumbent[coordinate]:
                target = (
                    self._upper_bounds[coordinate]
                    if direction > 0.0
                    else self._lower_bounds[coordinate]
                )
                candidate_value = math.nextafter(incumbent[coordinate], target)

            if candidate_value != incumbent[coordinate]:
                candidate = list(incumbent)
                candidate[coordinate] = candidate_value
                return (
                    tuple(candidate),
                    move_index,
                    step_sizes,
                    sweep_improved,
                )

            # An outward move at a bound is infeasible.  Advance as though it
            # had failed, without consuming a backend evaluation.
            (
                move_index,
                step_sizes,
                sweep_improved,
            ) = self._advance_cursor(
                move_index, False, step_sizes, sweep_improved
            )

        raise OptimizerProtocolError(
            "no representably distinct in-bounds candidate can be generated"
        )

    def _authenticate(self, transition: _Transition) -> bytes:
        payload = {
            "active_move_index": transition.active_move_index,
            "evaluated_energy": transition.evaluated_energy.hex(),
            "evaluated_theta": [value.hex() for value in transition.evaluated_theta],
            "evaluation_count": transition.evaluation_count,
            "incumbent_energy": transition.incumbent_energy.hex(),
            "incumbent_theta": [value.hex() for value in transition.incumbent_theta],
            "next_theta": [value.hex() for value in transition.next_theta],
            "source_generation": transition.source_generation,
            "step_sizes": [value.hex() for value in transition.step_sizes],
            "sweep_improved": transition.sweep_improved,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        return hmac.new(self._token_secret, encoded, hashlib.sha256).digest()


__all__ = [
    "AskTellPatternSearch",
    "ConsumedUpdateToken",
    "InvalidUpdateToken",
    "OptimizerProtocolError",
    "StaleUpdateToken",
]
