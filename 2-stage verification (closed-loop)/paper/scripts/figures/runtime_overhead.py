#!/usr/bin/env python3
"""Raw per-run timing medians, independent bootstrap intervals and differences.

Repetitions use the same workload seed. Intervals describe timing variability
for that workload, not variability over independent optimization trajectories.
"""
import csv,json,sys
import numpy as np
from style import *
sys.path.insert(0, str(PAPER/'scripts'))
from artifact_paths import resolve_recorded_path

def main(write_points=True):
    root=WORK/'VQE Runtime Verification - DejaVu copy/artifacts/sampler_verification_scaling_restart02_20260930'
    rows=list(csv.DictReader(resolve_recorded_path(root/'runs.csv').open())); metadata=json.loads(resolve_recorded_path(root/'summary.json').read_text())
    rng=np.random.default_rng(20261006); B=10000; points=[]
    for n in sorted(set(int(r['evaluations']) for r in rows)):
        values={}; ci={}; boot={}
        for cond in ['baseline','verified']:
            vals=[]
            for r in rows:
                if r['phase']=='measured' and r['condition']==cond and int(r['evaluations'])==n:
                    raw=json.loads(resolve_recorded_path(root/'runs'/'measured'/cond/f'n{n:03d}'/f"r{int(r['repetition']):03d}"/'run_summary.json').read_text())
                    assert raw['total_seconds']==float(r['total_seconds']);vals.append(raw['total_seconds'])
            v=np.asarray(vals);assert len(v)==metadata['measured_repetitions']
            boot[cond]=np.median(v[rng.integers(0,len(v),size=(B,len(v)))],axis=1)
            values[cond]=float(np.median(v));ci[cond]=np.quantile(boot[cond],[.025,.975])
        delta=values['verified']-values['baseline'];dci=np.quantile(boot['verified']-boot['baseline'],[.025,.975])
        points.append([n,values['baseline'],*ci['baseline'],values['verified'],*ci['verified'],delta,*dci])
    if write_points:
        with (PAPER/'data/runtime_figure_points.csv').open('w') as f:
            w=csv.writer(f);w.writerow(['evaluations','baseline_median','baseline_low','baseline_high','verified_median','verified_low','verified_high','added_median','added_low','added_high']);w.writerows(points)
    a=np.array(points);fig,(ax,bx)=plt.subplots(2,1,figsize=(3.5,3.65),sharex=True,layout='constrained',gridspec_kw={'height_ratios':[1.2,1]})
    for center,lo,hi,color,marker,ls,label in [(1,2,3,BLUE,'o','-','Baseline'),(4,5,6,ORANGE,'s','--','With verification')]:
        ax.errorbar(a[:,0],a[:,center],yerr=[a[:,center]-a[:,lo],a[:,hi]-a[:,center]],color=color,marker=marker,ms=3.2,mfc='white',ls=ls,capsize=2,label=label)
    ax.set_ylabel('Total runtime (s)');ax.legend(loc='upper left',frameon=False);ax.set_ylim(bottom=0)
    bx.errorbar(a[:,0],a[:,7],yerr=[a[:,7]-a[:,8],a[:,9]-a[:,7]],color='#333333',marker='^',ms=3.2,mfc='white',ls='-',capsize=2)
    bx.set(xlabel='Energy evaluations',ylabel='Added extra time (s)',ylim=(0,None));bx.set_xticks(a[:,0])
    for axis in [ax,bx]: axis.grid(axis='y',alpha=.16,lw=.5)
    export(fig,'runtime-overhead.pdf')

if __name__=='__main__': main()
