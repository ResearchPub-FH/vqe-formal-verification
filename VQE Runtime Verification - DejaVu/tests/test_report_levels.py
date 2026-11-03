from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

from vqe_runtime.report import (
    Level,
    PROPERTY_LEVEL_REGISTRY,
    UnknownPropertyLevelWarning,
    VerificationReport,
    level_for_property,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PROPERTY_ID = re.compile(r"^(?:intra|inter|run)_[a-z][a-z0-9_]*$")


class PropertyLevelRegistryTests(unittest.TestCase):
    def test_every_python_contract_id_is_registered_at_its_audited_level(self):
        # These are schema/field values rather than property IDs. Inspect every
        # other snake_case scoped string in the executable verifier so additions
        # cannot silently fall through the registry.
        non_properties = {
            "inter_iteration",
            "intra_iteration",
            "run_id",
            "run_level",
            "run_sampled_vqe",
            "run_shots",
        }
        discovered: set[str] = set()
        package = REPOSITORY_ROOT / "src/vqe_runtime"
        for source in package.glob("*.py"):
            if source.name == "report.py":
                continue
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            discovered.update(
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and PROPERTY_ID.fullmatch(node.value)
            )
        discovered.difference_update(non_properties)

        self.assertFalse(
            discovered - PROPERTY_LEVEL_REGISTRY.keys(),
            f"unregistered Python property IDs: "
            f"{sorted(discovered - PROPERTY_LEVEL_REGISTRY.keys())}",
        )
        for property_id in discovered:
            if property_id == "run_iteration_limit_once":
                expected = Level.INTER_ITERATION
            elif property_id.startswith("intra_"):
                expected = Level.INTRA_ITERATION
            elif property_id.startswith("inter_"):
                expected = Level.INTER_ITERATION
            else:
                expected = Level.RUN_LEVEL
            self.assertEqual(level_for_property(property_id), expected, property_id)

    def test_every_qtl_property_uses_its_declared_section(self):
        section: Level | None = None
        discovered: dict[str, Level] = {}
        spec = REPOSITORY_ROOT / "specs/vqe_runtime.qtl"
        for line in spec.read_text(encoding="utf-8").splitlines():
            if line.startswith("// Intra-iteration:"):
                section = Level.INTRA_ITERATION
            elif line.startswith("// Inter-iteration:"):
                section = Level.INTER_ITERATION
            elif line.startswith("// Run level:"):
                section = Level.RUN_LEVEL
            match = re.match(r"^prop\s+(\w+)\s*:", line)
            if match is not None:
                self.assertIsNotNone(section, f"property before a section: {line}")
                discovered[match.group(1)] = section  # type: ignore[assignment]

        self.assertTrue(discovered)
        self.assertFalse(
            discovered.keys() - PROPERTY_LEVEL_REGISTRY.keys(),
            f"unregistered QTL property IDs: "
            f"{sorted(discovered.keys() - PROPERTY_LEVEL_REGISTRY.keys())}",
        )
        for property_id, expected in discovered.items():
            self.assertEqual(level_for_property(property_id), expected, property_id)

    def test_iteration_limit_qtl_property_is_inter_iteration(self):
        self.assertEqual(
            level_for_property("run_iterationLimitOnce"), Level.INTER_ITERATION
        )

    def test_unknown_id_warns_and_uses_schema_compatible_safe_fallback(self):
        report = VerificationReport("run", "config")
        with self.assertWarnsRegex(
            UnknownPropertyLevelWarning, "unregistered property ID"
        ):
            report.add_inconclusive("external_extension_property", "not registered")

        self.assertEqual(report.findings[0].level, Level.RUN_LEVEL)
        rendered = report.as_dict()
        self.assertEqual(
            set(rendered["levels"]),
            {"intra_iteration", "inter_iteration", "run_level"},
        )
        self.assertEqual(
            rendered["levels"]["run_level"]["findings"][0]["property_id"],
            "external_extension_property",
        )

    def test_registry_is_read_only(self):
        with self.assertRaises(TypeError):
            PROPERTY_LEVEL_REGISTRY["new_property"] = Level.RUN_LEVEL  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
