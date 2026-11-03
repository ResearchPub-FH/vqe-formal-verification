#!/usr/bin/env python3
"""Full CDF from final raw kernel/quantitative file and raw runtime terminals.

No interpolation of model measurements: both curves are discrete-update CDFs.
Wilson intervals are marginal, pointwise intervals, not simultaneous bands.
"""
import csv, gzip, hashlib, json, math
from statistics import NormalDist
import numpy as np
from style import *

# Presentation colors only. Estimates and intervals are read from artifacts.
MODEL_COLOR = '#009B63'
EMPIRICAL_COLOR = '#D60078'

def main():
    pre=json.loads((RUN/'stage1/pre_execution.json').read_text()); cfg=pre['configuration']
    q=json.loads((RUN/'stage1/quantitative.json').read_text())
    report=json.loads((RUN/'stage2/baseline/results.json').read_text()); T=[]
    for r in report['results']:
        p=RUN/r['trace']; assert hashlib.sha256(p.read_bytes()).hexdigest()==r['trace_sha256']
        with gzip.open(p,'rt') as f: terminal=[json.loads(l) for l in f if '"terminal"' in l][-1]
        assert terminal['type']=='terminal'; T.append(terminal['updates'] if terminal['reason']=='success' else -1)
    T=np.asarray(T); n=len(T); k=np.arange(cfg['maximum_updates']+1); model=np.asarray(q['success_cdf'])
    successes=np.array([np.sum((T>=0)&(T<=u)) for u in k]); empirical=successes/n
    z=NormalDist().inv_cdf(.975); den=1+z*z/n
    center=(empirical+z*z/(2*n))/den
    rad=z*np.sqrt(empirical*(1-empirical)/n+z*z/(4*n*n))/den
    low=np.where(successes==0,0,np.maximum(0,center-rad)); high=np.where(successes==n,1,np.minimum(1,center+rad))
    with (PAPER/'data/probability_figure_points.csv').open('w') as f:
        w=csv.writer(f); w.writerow(['k','model_probability','empirical_probability','successes','n','wilson_low','wilson_high'])
        w.writerows(zip(k,model,empirical,successes,np.repeat(n,len(k)),low,high))
    fig,ax=plt.subplots(figsize=(3.5,2.72),layout='constrained')
    ax.fill_between(k,100*low,100*high,step='post',color=GRAY,alpha=.19,lw=0)
    ax.step(k,100*model,where='post',color=MODEL_COLOR,lw=1.35,ls='-',label='Gaussian DTMC')
    ax.step(k,100*empirical,where='post',color=EMPIRICAL_COLOR,lw=1.35,ls='--',label=f'Finite-shot runs ($n={n}$)')
    checkpoints=cfg['checkpoints']
    ax.plot(checkpoints,[100*q['storm']['results'][str(u)] for u in checkpoints],ls='none',marker='o',ms=3.4,mfc='white',mec=MODEL_COLOR,label='Storm checkpoints')
    marker_k=k[(k>=25)&(k%5==0)]
    ax.plot(marker_k,100*empirical[marker_k],ls='none',marker='s',ms=2.8,mfc='white',mec=EMPIRICAL_COLOR)
    ax.set(xlim=(0,cfg['maximum_updates']),ylim=(0,100),xlabel='Optimizer iteration $k$',ylabel='Cumulative success probability (%)')
    ax.set_xticks(cfg['checkpoints']+[0]); ax.set_yticks([0,25,50,75,100]); ax.grid(axis='y',alpha=.15,lw=.5)
    ax.legend(loc='upper left',frameon=False,handlelength=2.1)
    export(fig,'probability-comparison.pdf')

if __name__=='__main__': main()
