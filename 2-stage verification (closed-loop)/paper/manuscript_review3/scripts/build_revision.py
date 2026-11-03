#!/usr/bin/env python3
"""Build review3 in place, sharing the parent bibliography and unchanged assets."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

REVISION = Path(__file__).resolve().parents[1]
PAPER = REVISION.parent

def main():
    env = os.environ.copy()
    if Path('/private/tmp/vqe-paper-python').exists():
        env['PYTHONPATH'] = '/private/tmp/vqe-paper-python' + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    tectonic = env.get('VQE_TECTONIC') or shutil.which('tectonic')
    if not tectonic and Path('/private/tmp/vqe-tectonic-bin/tectonic').is_file():
        tectonic = '/private/tmp/vqe-tectonic-bin/tectonic'
    if not tectonic:
        raise SystemExit('Install Tectonic or set VQE_TECTONIC to its executable.')
    if Path('/private/tmp/vqe-tex-cache').exists():
        env.setdefault('TECTONIC_CACHE_DIR', '/private/tmp/vqe-tex-cache')
    def run(args, cwd=REVISION):
        subprocess.run([str(x) for x in args], cwd=cwd, env=env, check=True)
    run([sys.executable, REVISION / 'scripts/generate_tables.py'])
    run([tectonic, '--keep-logs', '--outdir', REVISION / 'figures', PAPER / 'figures/architecture.tex'], PAPER)
    run([tectonic, '--keep-logs', '--keep-intermediates', 'manuscript_review3.tex'])
    run([sys.executable, PAPER / 'scripts/validate_paper.py', '--manuscript', 'manuscript_review3/manuscript_review3.tex'], PAPER)
    run([sys.executable, REVISION / 'scripts/validate_revision.py'])

if __name__ == '__main__':
    main()
