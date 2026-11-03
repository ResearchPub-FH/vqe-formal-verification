#!/usr/bin/env python3
"""Rebuild all manuscript artifacts from source; never mutate experiment inputs."""
from pathlib import Path
import argparse, os, re, subprocess, sys
paper=Path(__file__).resolve().parents[1]
versions=list(paper.glob('manuscript_review*.tex'))
default=max(versions,key=lambda p:int(re.search(r'_review(\d+)\.tex$',p.name)[1])).name if versions else 'manuscript.tex'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--manuscript',default=default,help='Main source to compile (default: latest existing revision).')
args=parser.parse_args()
assert (paper/args.manuscript).parent==paper and (paper/args.manuscript).is_file()
commands=[[sys.executable,'scripts/extract_results.py']]
commands += [[sys.executable,f'scripts/figures/{name}.py'] for name in ['storm_scalability','runtime_overhead','probability_comparison','fault_discrepancies']]
engine=os.environ.get('TECTONIC','tectonic')
commands += [[engine,'figures/architecture.tex','--outdir','figures','--keep-logs'],[engine,args.manuscript,'--keep-logs','--keep-intermediates'],[sys.executable,'scripts/validate_paper.py','--manuscript',args.manuscript]]
for command in commands:
    print('Running:', ' '.join(command),flush=True)
    subprocess.run(command,cwd=paper,check=True)
