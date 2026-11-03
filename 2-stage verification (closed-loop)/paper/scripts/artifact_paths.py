"""Resolve a documented directory relocation without changing recorded hashes.

The original source manifest keeps the paths recorded during the audited run.
Only this explicit directory alias is accepted. Every source byte checksum is
still verified against that manifest by verify_recorded_sources.
"""
from pathlib import Path
import hashlib

WORK = Path(__file__).resolve().parents[2].parent
DIRECTORY_ALIASES = {'VQE Runtime Verification - DejaVu copy':
                     'VQE Runtime Verification - DejaVu'}

def resolve_recorded_path(path):
    path = Path(path)
    if path.exists():
        return path
    try:
        relative = path.relative_to(WORK)
    except ValueError:
        raise FileNotFoundError(path)
    replacement = DIRECTORY_ALIASES.get(relative.parts[0])
    if replacement:
        candidate = WORK/replacement/Path(*relative.parts[1:])
        if candidate.exists():
            return candidate
    raise FileNotFoundError(path)

def verify_recorded_sources(sources):
    relocated = {}
    for name, expected in sources.items():
        recorded = WORK/name
        actual = resolve_recorded_path(recorded)
        checksum = hashlib.sha256(actual.read_bytes()).hexdigest()
        assert checksum == expected, (name, str(actual), 'source checksum mismatch')
        if actual != recorded:
            relocated[name] = str(actual.relative_to(WORK))
    return {'status': 'PASS', 'verified_source_count': len(sources),
            'relocated_source_count': len(relocated), 'relocated_paths': relocated,
            'recorded_manifest_unchanged': True}
