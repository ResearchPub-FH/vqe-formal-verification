#!/usr/bin/env python3
"""Time-unrolled DTMC size and recorded cost from CSV/raw metadata.

The construction time is one observation per horizon. Checking is the median
of three tool-reported observations. No uncertainty estimate is invented.
"""
import csv,json
import numpy as np
from style import *
from matplotlib.ticker import FuncFormatter

# A distinct saturated palette from the probability comparison.
SIZE_COST_COLOR = '#005BFF'
TRANSITION_CHECK_COLOR = '#F26700'

def main():
    d=WORK/'Probabilistic verification - 2 methods comparision/artifacts/h2_vqe/additional_experiments/model_checking_scalability'
    rows=list(csv.DictReader((d/'scalability_results.csv').open())); meta=json.loads((d/'metadata.json').read_text())
    k=np.array([int(r['K']) for r in rows]); states=np.array([int(r['reachable_states']) for r in rows]); transitions=np.array([int(r['transitions']) for r in rows])
    construction=np.array([float(r['dtmc_construction_time_s']) for r in rows])
    checking=np.array([float(r['storm_checking_time_s']) for r in rows])
    for u,s,r in zip(k,states,rows):
        assert sum(meta['details'][str(u)]['level_state_counts'])+1+int(float(r['gaussian_pK'])>0)==s
    with (PAPER/'data/scalability_figure_points.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['K','reachable_states','transitions','construction_seconds','checking_median_seconds']);w.writerows(zip(k,states,transitions,construction,checking))
    fig,(ax,bx)=plt.subplots(2,1,figsize=(3.5,4.05),sharex=True,layout='constrained',gridspec_kw={'height_ratios':[1.15,1]})
    ax.plot(k,states,color=SIZE_COST_COLOR,lw=1.35,marker='o',ms=3.5,mfc='white',label='States')
    ax.plot(k,transitions,color=TRANSITION_CHECK_COLOR,lw=1.35,marker='s',ms=3.5,mfc='white',ls='--',label='Transitions')
    ax.set_yscale('log');ax.set_ylabel('Reachable model size')
    ax.set_xticks(k);ax.set_yticks([1000,10000,100000,1000000]);ax.yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{int(x):,}'))
    ax.minorticks_off();ax.grid(axis='y',alpha=.18,lw=.5);ax.legend(loc='upper left',frameon=False)
    bx.plot(k,construction,color=SIZE_COST_COLOR,lw=1.35,marker='o',ms=3.5,mfc='white',label='Construction')
    bx.plot(k,checking,color=TRANSITION_CHECK_COLOR,lw=1.35,marker='s',ms=3.5,mfc='white',ls='--',label='Storm checking')
    bx.set(xlabel='Unrolled iteration bound $K$',ylabel='Runtime (s)',ylim=(0,None))
    bx.grid(axis='y',alpha=.18,lw=.5);bx.legend(loc='upper left',frameon=False)
    export(fig,'storm-scalability.pdf')

if __name__=='__main__': main()
