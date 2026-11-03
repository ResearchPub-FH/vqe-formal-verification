#!/usr/bin/env python3
"""Read-only reconstruction of the evidence used by the paper.

All writes are confined to paper/. Measured values are never embedded in this
script. It validates the sealed run, reconstructs every baseline estimator from
raw counts, recomputes statistical summaries, and exports LaTeX tables/macros.
"""
from pathlib import Path
from collections import Counter, defaultdict
from fractions import Fraction
import csv, gzip, hashlib, json, math, re, subprocess, sys
import numpy as np
from scipy import stats
from artifact_paths import resolve_recorded_path

PAPER = Path(__file__).resolve().parents[1]
EXP = PAPER.parent
WORK = EXP.parent
RUN = EXP / 'artifacts/approved-experiment'
SCALING = WORK / 'Probabilistic verification - 2 methods comparision/artifacts/h2_vqe/additional_experiments/model_checking_scalability'
TIMING = WORK / 'VQE Runtime Verification - DejaVu copy/artifacts/sampler_verification_scaling_restart02_20260930'
HARDWARE = WORK / 'VQE Runtime Verification - DejaVu copy'
OLDPROB = WORK / 'Probabilistic verification - 2 methods comparision/artifacts/h2_vqe'
DATA = PAPER / 'data'
TABLES = PAPER / 'tables'
sys.path.insert(0, str(EXP))
from closed_loop.common import validate_frozen
from closed_loop.comparison import audit_results

def read(p): return json.loads(resolve_recorded_path(p).read_text())
def sha(p): return hashlib.sha256(resolve_recorded_path(p).read_bytes()).hexdigest()
def save(p, d): Path(p).write_text(json.dumps(d, indent=2, sort_keys=True, allow_nan=False)+'\n')
def csv_rows(p): return list(csv.DictReader(resolve_recorded_path(p).open()))
def wilson(s, n):
    z = stats.norm.ppf(.975); p = s/n; den = 1+z*z/n
    cen = (p+z*z/(2*n))/den; rad = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [0. if s == 0 else max(0.,cen-rad), 1. if s == n else min(1.,cen+rad)]
def boot_mean(x, cfg):
    x=np.asarray(x,dtype=float)
    rng=np.random.default_rng(np.random.SeedSequence([cfg['seed'],99]))
    b=x[rng.integers(0,len(x),size=(cfg['bootstrap_samples'],len(x)))].mean(axis=1)
    return np.quantile(b,[.025,.975]).tolist()
def holm(pvals):
    out={}; acc=0.; ordered=sorted(pvals.items(),key=lambda v:v[1]); m=len(ordered)
    for i,(name,p) in enumerate(ordered):
        acc=max(acc,min(1.,(m-i)*p)); out[name]=acc
    return out
def tex_table(filename, text): (TABLES/filename).write_text(text+'\n'+r'\bottomrule'+'\n')
def comma(n): return f'{int(n):,}'
def sci_tex(v):
    a,e=f'{v:.3e}'.split('e'); return f'{a}\\times 10^{{{int(e)}}}'

def main():
    DATA.mkdir(exist_ok=True); TABLES.mkdir(exist_ok=True)
    pre, seal=validate_frozen(RUN); cfg=pre['configuration']; q=read(RUN/'stage1/quantitative.json')
    baseline=read(RUN/'stage2/baseline/results.json'); faults=read(RUN/'stage2/faults/results.json')
    old=read(RUN/'comparison/verdict_agreement.json'); complete=read(RUN/'completion_audit.json')
    assert baseline['started_at'] > pre['frozen_at']
    assert sha(RUN/'stage2/baseline/results.json') == complete['baseline_result_sha256']
    assert sha(RUN/'stage2/faults/results.json') == complete['fault_result_sha256']
    assert sha(RUN/'comparison/verdict_agreement.json') == complete['result_sha256']
    # Full replay and DejaVu log/hash validation have no artifact writes.
    audit_results(RUN,pre,seal,baseline,full_replay=True)
    audit_results(RUN,pre,seal,faults,full_replay=True)
    print('Frozen source hashes, seals, all baseline/fault traces and replay verified',flush=True)
    results=baseline['results']; assert len(results)==cfg['runs']
    terms=cfg['hamiltonian']['terms']; scale=cfg['hamiltonian']['coefficient_scale']
    groups=cfg['measurement_groups']; shots_update=3*len(groups)*cfg['shots_per_group']
    T=[]; updates=[]; total_shots=0; evals=0; measures=0; max_error=Fraction(0)
    for ri,r in enumerate(results):
        observed={}; energies={}; committed=[]; shot_count=0; terminal=None
        with gzip.open(RUN/r['trace'],'rt') as f:
            for line in f:
                ev=json.loads(line); typ=ev['type']
                assert ev['configuration_digest']==pre['configuration_digest']
                if typ=='measurement':
                    counts=ev['counts']; assert len(counts)==4 and all(type(c) is int and c>=0 for c in counts)
                    assert sum(counts)==ev['shots']==cfg['shots_per_group']
                    key=(ev['update'],ev['candidate'],ev['group']); assert key not in observed
                    observed[key]=counts; shot_count+=sum(counts); measures+=1
                elif typ=='evaluation':
                    u,c=ev['update'],ev['candidate']; reference=Fraction(0); score=0
                    for gi,grp in enumerate(groups):
                        counts=observed[(u,c,gi)]
                        for term in grp:
                            signs=[(-1)**sum(((o>>(1-j))&1) for j,p in enumerate(term) if p!='I') for o in range(4)]
                            num=sum(n*s for n,s in zip(counts,signs)); expectation=Fraction(num,sum(counts))
                            assert Fraction(ev['expectations'][term])==expectation
                            contribution=Fraction(terms[term],scale)*expectation; reference+=contribution
                            assert abs(Fraction(ev['contributions'][term])-contribution) <= Fraction(cfg['energy_tolerance'])
                            score+=terms[term]*num
                    err=abs(Fraction(ev['energy'])-reference); max_error=max(max_error,err)
                    assert err<=Fraction(cfg['energy_tolerance']) and ev['score']==score
                    energies[(u,c)]=(ev['energy'],score); evals+=1
                elif typ=='optimizer_commit':
                    u=ev['update']; expected=[energies[(u,c)] for c in range(3)]
                    assert ev['energies_used']==[v[0] for v in expected]
                    assert ev['scores_used']==[v[1] for v in expected]
                    assert ev['choice']==min(range(3),key=lambda c:expected[c][1])
                    committed.append(u); assert ev['physical_shots']==shot_count
                elif typ=='terminal': terminal=ev
        assert terminal is not None and terminal['physical_shots']==shot_count==r['physical_shots']
        assert terminal['updates']==r['updates']==len(committed)
        # RuntimeChecker replay above checks ideal success and all provenance.
        t=r['success_step'] if terminal['reason']=='success' else None
        assert terminal['reason']==r['terminal_reason'] and t==r['success_step']
        T.append(t); updates.append(len(committed)); total_shots+=shot_count
        if (ri+1)%100==0: print(f'Reconstructed raw estimators: {ri+1}/{len(results)}',flush=True)
    assert total_shots==old['total_physical_shots'] and float(max_error)==old['maximum_energy_reconstruction_error']
    # Reconstruct the full model CDF from the retained raw Gaussian kernel.
    kd=np.load(RUN/'stage1/gaussian-kernels.npz'); kernel=kd['kernels']; success=kd['success']
    mass=np.zeros(success.shape); mass[tuple(cfg['initial_index'])]=1
    cdf=[float(mass[success].sum())]; mass[success]=0
    for u in range(cfg['maximum_updates']):
        coord=cfg['coordinate_schedule'][u%len(cfg['coordinate_schedule'])]; p=kernel[coord]
        mass=mass*p[0]+np.roll(mass*p[1],-1,axis=coord)+np.roll(mass*p[2],1,axis=coord)
        cdf.append(cdf[-1]+float(mass[success].sum())); mass[success]=0
    assert np.allclose(cdf,q['success_cdf'],rtol=0,atol=1e-14)
    storm_values=[float(v) for v in re.findall(r'Result \(for initial states\):\s*([-+0-9.eE]+)',(RUN/'stage1/storm.log').read_text())]
    assert storm_values==[q['storm']['results'][str(k)] for k in cfg['checkpoints']]
    tau=np.array([t if t is not None else -1 for t in T]); n=len(tau); successful=tau[tau>=0]
    probs=[]; pvals={}
    for k,model in zip(cfg['checkpoints'],storm_values):
        s=int(((tau>=0)&(tau<=k)).sum()); interval=wilson(s,n)
        row={'k':k,'model':model,'successes':s,'n':n,'empirical':s/n,'wilson_95':interval,'absolute_difference':abs(model-s/n)}
        if 0<model<1:
            z=(s/n-model)/math.sqrt(model*(1-model)/n)
            row['p_raw']=float(2*stats.norm.sf(abs(z))); pvals[f'P1@{k}']=row['p_raw']
        probs.append(row)
        original=next(v for v in old['probability_comparison'] if v['update_bound']==k)
        assert np.allclose(interval,original['wilson_95'],rtol=0,atol=1e-14) and s==original['runtime_successes']
    first=np.diff(np.array([0.]+cdf)); model_mean=float(np.dot(np.arange(len(cdf)),first)/cdf[-1])
    assert abs(model_mean-q['expected_updates_given_success'])<1e-12
    ci=boot_mean(successful,cfg); mean=float(successful.mean())
    assert ci==old['conditional_means'][0]['bootstrap_95'] and mean==old['conditional_means'][0]['runtime_mean']
    z=(mean-model_mean)/(successful.std(ddof=1)/math.sqrt(len(successful)))
    pvals['P2']=float(2*stats.norm.sf(abs(z))); adjusted=holm(pvals)
    for row in probs:
        if 'p_raw' in row: row['p_holm']=adjusted[f"P1@{row['k']}"]
    p2={'model':model_mean,'empirical':mean,'bootstrap_95':ci,'absolute_difference':abs(model_mean-mean),'p_raw':pvals['P2'],'p_holm':adjusted['P2'],'successful_runs':len(successful),'classification':'AGREEMENT (statistically compatible after Holm adjustment)'}
    p3={'model':model_mean*shots_update,'empirical':mean*shots_update,'bootstrap_95':[v*shots_update for v in ci],'absolute_difference':abs(model_mean-mean)*shots_update,'derived_from':'P2','classification':'AGREEMENT (derived from P2; not an independent test)'}
    assert np.allclose(p3['bootstrap_95'],old['conditional_means'][1]['bootstrap_95'])
    # Descriptive total resource expenditure includes budget-terminated runs.
    unconditional=np.asarray(updates,dtype=float)
    resource={'model_mean_updates':sum(1-v for v in cdf[:-1]),'empirical_mean_updates':float(unconditional.mean()),'bootstrap_95':boot_mean(unconditional,cfg),'total_updates':int(unconditional.sum()),'total_shots':total_shots,'evaluations':evals,'measurements':measures,'max_energy_error':float(max_error)}
    pre_ltl=re.findall(r'^-- specification (.+?) is (true|false)$',(RUN/'stage1/nuxmv.log').read_text(),re.M)
    assert len(pre_ltl)==len(pre['logical']['properties']) and all(v=='true' for _,v in pre_ltl)
    numeric=[]
    for entry in pre['numeric']:
        text=(RUN/'stage1'/f"dafny-{entry['source']}.log").read_text(); match=re.search(r'finished with (\d+) verified, (\d+) errors',text)
        assert match and int(match[2])==0 and int(match[1])==entry['verified_count']
        numeric.append({'source':entry['source'],'verified':int(match[1]),'errors':int(match[2])})
    contract_rows=[]
    for row in old['logical_numeric']:
        counts=dict(Counter(r['contracts'][row['contract']]['runtime_verdict'] for r in results))
        assert counts==row['runtime_counts']; contract_rows.append({**row,'qualification':'Only terminal absorption and budget bounds prospectively; reason checks at runtime' if row['contract']=='L4' else 'Mapping assumptions stated in Table I'})
    fault_rows=[]
    for name in sorted(set(r['fault'] for r in faults['results'])):
        rr=[r for r in faults['results'] if r['fault']==name]
        vectors=[{cid:v['runtime_verdict'] for cid,v in r['contracts'].items()} for r in rr]
        assert all(v==vectors[0] for v in vectors)
        fault_rows.append({'fault':name,'n':len(rr),'expected_contract':rr[0]['expected_contract'],'expected_verdict':rr[0]['expected_verdict'],'detected':sum(r['detected_as_expected'] for r in rr),'vector':vectors[0],'dejavu_passed':sum(r['dejavu']['passed'] for r in rr),'scope':rr[0]['fault_scope'],'probabilistic_applicability_recorded':dict(Counter(r['probabilistic_applicability'] for r in rr))})
    # Retained layer-specific scalability: raw detail level counts and timings.
    smeta=read(SCALING/'metadata.json'); scaling=csv_rows(SCALING/'scalability_results.csv')
    for row in scaling:
        k=int(row['K']); detail=smeta['details'][str(k)]
        # The unrolled export merges timeout, and (when reachable) success,
        # into additional absorbing states outside the active depth counts.
        assert sum(detail['level_state_counts'])+1+int(float(row['gaussian_pK'])>0)==int(row['reachable_states'])
        assert float(np.median(detail['storm_checking_times_s']))==float(row['storm_checking_time_s'])
        assert abs(float(row['storm_result'])-q['success_cdf'][k])<1e-8
    # Completed runtime timing study. Every CSV timing is checked against raw
    # per-run JSON. Bootstrap condition medians independently; no paired claim.
    tsummary=read(TIMING/'summary.json'); tc=read(TIMING/'completion_audit.json'); rows=csv_rows(TIMING/'runs.csv')
    assert len(rows)==tc['run_count']; timing=[]
    rng=np.random.default_rng(20261006); B=10000
    for row in rows:
        path=TIMING/'runs'/row['phase']/row['condition']/f"n{int(row['evaluations']):03d}"/f"r{int(row['repetition']):03d}"/'run_summary.json'
        raw=read(path); assert float(row['total_seconds'])==raw['total_seconds']
        assert raw['completed_evaluations']==int(row['evaluations'])
    for ev in sorted(set(int(r['evaluations']) for r in rows)):
        item={'evaluations':ev}; bootstrap={}
        for cond in ['baseline','verified']:
            values=np.array([float(r['total_seconds']) for r in rows if r['phase']=='measured' and r['condition']==cond and int(r['evaluations'])==ev])
            assert len(values)==tsummary['measured_repetitions']
            samples=np.median(values[rng.integers(0,len(values),size=(B,len(values)))],axis=1); bootstrap[cond]=samples
            item[cond]={'n':len(values),'median':float(np.median(values)),'p95':float(np.quantile(values,.95)),'median_bootstrap_95':np.quantile(samples,[.025,.975]).tolist()}
        item['added_median']=item['verified']['median']-item['baseline']['median']
        item['added_bootstrap_95']=np.quantile(bootstrap['verified']-bootstrap['baseline'],[.025,.975]).tolist()
        item['relative_increase_percent']=100*item['added_median']/item['baseline']['median']; timing.append(item)
    # Legacy logical model is a separate evaluation, not the final controller.
    lr=WORK/'NuXmv Files/VQE_NuXmv_Refinement/results'
    legacy_specs=re.findall(r'^-- (specification|invariant) (.+?) is (true|false)$',(lr/'refined_verification_results.txt').read_text(),re.M)
    legacy_scales=[]
    for p in sorted(lr.glob('scale_*_time.txt')):
        a,b=map(int,re.search(r'scale_(\d+)_(\d+)',p.name).groups()); spec=re.findall(r'^-- (?:specification|invariant) .+? is (true|false)$',p.with_name(p.name.replace('_time.txt','_result.txt')).read_text(),re.M)
        elapsed=float(re.search(r'real\s+([\d.]+)',p.read_text())[1]); legacy_scales.append({'updates':a,'terms':b,'true':spec.count('true'),'false':spec.count('false'),'seconds':elapsed})
    phase=csv_rows(WORK/'NuXmv Files/VQE_Phase_Reachability/results/reachability.csv')
    # Numeric trace outcomes are newly replayed with the recorded later checker.
    checker=WORK/'Dafny + Python trace checker/python 2.0/trace_checker.py'
    paths=[WORK/'Dafny + Python trace checker/traces/myTests'/p for p in ['h2_ibm_runtime_paper.jsonl','heisenberg14_statevector.jsonl']]
    cmd=[sys.executable,str(checker),'--json',*[str(p) for p in paths]]
    done=subprocess.run(cmd,capture_output=True,text=True); assert done.returncode==0,done.stderr+done.stdout
    nr=json.loads(done.stdout); save(DATA/'numeric_trace_replay.json',{'command':cmd,'report':nr})
    trace_summary=[]
    for p,rep in zip(paths,nr['results']):
        rr=[json.loads(l) for l in p.read_text().splitlines() if l.strip()]
        assert rep['valid'] and rep['records']==len(rr)
        trace_summary.append({'name':'Two-qubit Estimator' if rr[0]['parameter_count']==cfg['parameter_count'] else 'Heisenberg','records':len(rr),'qubits':len(rr[0]['paulis'][0]),'terms':rr[0]['expected_term_count'],'parameters':rr[0]['parameter_count'],'raw_counts_available':all(all(r['counts_available']) for r in rr),'status':'PASS','path':str(p.relative_to(WORK))})
    hwsummary=read(HARDWARE/'artifacts/results/h2_sampler_comparison_20260907/campaign_summary.json'); hw=[]
    for name in ['statevector','hardware']:
        v=hwsummary[name]
        for key,path in v['paths'].items(): assert sha(HARDWARE/path)==v['sha256'][key]
        for typ in ['online_report','replay_report']: assert read(HARDWARE/v['paths'][typ])['status']=='pass'
        hw.append({'condition':v['label'],'evaluations':v['evaluations'],'physical_shots':v['physical_shots'],'pubs':v['pubs'],'online':v['online_status'],'replay':v['replay_status'],'terminal':v['terminal_reason']})
    noisy=[json.loads(l) for l in (OLDPROB/'layer4_empirical/fakebackend_runs.jsonl').read_text().splitlines()]
    noisy_success=sum(r['success_step'] is not None and r['success_step']<=cfg['maximum_updates'] for r in noisy)
    noise_summary={'n':len(noisy),'successes':noisy_success,'probability':noisy_success/len(noisy),'wilson_95':wilson(noisy_success,len(noisy)),'configuration':read(OLDPROB/'layer4_empirical/fakebackend_metadata.json')}
    se=math.sqrt(probs[-1]['model']*(1-probs[-1]['model'])/n)
    result={'run_id':'approved-experiment','configuration_digest':pre['configuration_digest'],'pre_execution_digest':seal,'configuration':cfg,'model':q,'model_cdf_recomputed':cdf,'success_steps_from_raw':T,'probability_comparison':probs,'P2':p2,'P3':p3,'resource':resource,'contracts':contract_rows,'faults':fault_rows,'logical_property_count':len(pre_ltl),'numeric':numeric,'dejavu_baseline_passed':sum(r['dejavu']['passed'] for r in results),'legacy_logical':{'properties':len(legacy_specs),'true':sum(v=='true' for _,_,v in legacy_specs),'phase_queries':len(phase),'phase_true':sum(r['result']=='TRUE' for r in phase),'scales':legacy_scales},'numeric_traces':trace_summary,'hardware_runtime':hw,'noisy_robustness':noise_summary,'scaling':scaling,'timing':timing,'timing_metadata':{'configuration':tsummary['configuration'],'timing_boundary':tsummary['timing_boundary'],'warmups':tsummary['warmups'],'measured_repetitions':tsummary['measured_repetitions'],'bootstrap_seed':20261006,'bootstrap_resamples':B},'resolution':{'score_threshold':stats.norm.ppf(.975)*se,'approximate_80_power_deviation':(stats.norm.ppf(.975)+stats.norm.ppf(.8))*se},'missing_audit_arrays':not (EXP/'audit/_out/mc_T_shots1024_R100000.npy').exists()}
    save(DATA/'derived_results.json',result)
    macro={
      'BaselineRuns':comma(n),'SuccessRuns':comma(len(successful)),'BudgetRuns':comma(n-len(successful)),
      'PrimaryModelPercent':f"{100*probs[-1]['model']:.2f}",'PrimaryEmpiricalPercent':f"{100*probs[-1]['empirical']:.2f}",
      'PrimaryCILower':f"{100*probs[-1]['wilson_95'][0]:.2f}",'PrimaryCIUpper':f"{100*probs[-1]['wilson_95'][1]:.2f}",
      'PrimaryDeviationPP':f"{100*probs[-1]['absolute_difference']:.2f}",
      'TotalUpdates':comma(resource['total_updates']),'TotalEvaluations':comma(evals),'TotalMeasurements':comma(measures),'TotalShots':comma(total_shots),
      'ModelStates':comma(q['dtmc_states']),'ModelTransitions':comma(q['transitions']),'GridPoints':comma(q['grid_states']),'SuccessPoints':comma(int(success.sum())),
      'GroundEnergy':f"{q['ground_energy']:.9f}",'ShotsPerGroup':comma(cfg['shots_per_group']),'ShotsPerUpdate':comma(shots_update),'MaxShotsRun':comma(shots_update*cfg['maximum_updates']),
      'UpdateBound':str(cfg['maximum_updates']),'GridSize':str(cfg['grid_size']),'GapThreshold':str(cfg['success_gap']),
      'QuadraturePoints':str(cfg['gauss_hermite_points']),'BootstrapSamples':comma(cfg['bootstrap_samples']),
      'LogicalProperties':str(len(pre_ltl)),'DafnyChecks':str(sum(v['verified'] for v in numeric)),
      'PModelMean':f'{model_mean:.3f}','PEmpiricalMean':f'{mean:.3f}','PMeanLow':f'{ci[0]:.3f}','PMeanHigh':f'{ci[1]:.3f}',
      'PMeanRawP':f"{p2['p_raw']:.3f}",'PMeanAdjustedP':f"{p2['p_holm']:.3f}",
      'UnconditionalModel':f"{resource['model_mean_updates']:.3f}",'UnconditionalEmpirical':f"{resource['empirical_mean_updates']:.3f}",
      'EnergyError':sci_tex(float(max_error)),'StormDifference':sci_tex(q['storm']['maximum_difference_from_forward_propagation']),
      'QuadratureCorrection':sci_tex(q['maximum_quadrature_row_correction']),
      'DetectablePP':f"{100*result['resolution']['approximate_80_power_deviation']:.2f}",
      'LegacyLogicalProperties':str(len(legacy_specs)),'PhaseQueries':str(len(phase)),
      'TimingMeasured':str(sum(r['phase']=='measured' for r in rows)),'TimingWarmup':str(sum(r['phase']=='warmup' for r in rows)),
      'TimingWarmupsPerCell':str(tsummary['warmups']),'TimingRepetitions':str(tsummary['measured_repetitions']),
      'TimingBaselineFinal':f"{timing[-1]['baseline']['median']:.3f}",'TimingVerifiedFinal':f"{timing[-1]['verified']['median']:.3f}",
      'TimingAddedFinal':f"{timing[-1]['added_median']:.3f}",'TimingRelativeFinal':f"{timing[-1]['relative_increase_percent']:.2f}",
      'NoisyRuns':str(len(noisy)),'NoisySuccess':str(noisy_success),'NoisyPercent':f'{100*noise_summary["probability"]:.2f}',
      'ScaleMaxStates':comma(int(scaling[-1]['reachable_states'])),'ScaleMaxTransitions':comma(int(scaling[-1]['transitions'])),
      'FaultRuns':str(len(faults['results'])),'FaultClasses':str(len(fault_rows)),'FaultRepetitions':str(cfg['fault_runs']),
    }
    # Prose replacements for two small tables retain every measured quantity.
    ordered_scales=sorted(legacy_scales,key=lambda r:r['updates'])
    macro['LogicalScalingPairs']=', '.join(f"$({r['updates']},{r['terms']})$" for r in ordered_scales)
    macro['LogicalScalingTimes']=', '.join(f"{r['seconds']:.2f}" for r in ordered_scales)
    for prefix,r in zip(['Estimator','Heisenberg'],trace_summary):
        for field in ['qubits','terms','records']:
            macro[prefix+field.capitalize()]=comma(r[field])
    save(DATA/'claim_values.json',macro)
    (DATA/'numbers.tex').write_text('% Generated by scripts/extract_results.py; do not hand-edit.\n'+''.join(f'\\newcommand{{\\{k}}}{{{v}\\xspace}}\n' for k,v in macro.items()))
    # Exact measured tables: numbers come only from reconstructed result objects.
    tex_table('probabilities.tex', '\n'.join(f"{r['k']} & {r['successes']}/{n} & {100*r['model']:.2f} & {100*r['empirical']:.2f} & [{100*r['wilson_95'][0]:.2f}, {100*r['wilson_95'][1]:.2f}] & {100*r['absolute_difference']:.2f} & "+(f"{r['p_holm']:.3f}" if 'p_holm' in r else '--')+r' \\' for r in probs))
    tex_table('conditional.tex',f"P2: iterations & {p2['model']:.3f} & {p2['empirical']:.3f} & [{ci[0]:.3f}, {ci[1]:.3f}] & {p2['absolute_difference']:.3f} & {p2['p_holm']:.3f}"+r' \\'+'\n'+f"P3: shots & {p3['model']:,.1f} & {p3['empirical']:,.1f} & [{p3['bootstrap_95'][0]:,.1f}, {p3['bootstrap_95'][1]:,.1f}] & {p3['absolute_difference']:,.1f} & derived"+r' \\')
    scopes={'L1':'Group-completeness counter','L2':'Validation-readiness counter','L3':'Epoch and readiness reset','L4':'Terminal absorption and budget bounds','N1':'Normalization kernel with parity assumed','N2':'Real weighted sum and bound','N3':'List sum with group identity assumed','N4':'Wrap and integer tie-priority selection'}
    tex_table('contracts.tex','\n'.join(f"{r['contract']} & {scopes[r['contract']]} & {r['runtime_counts']['AGREEMENT']}/{n} & "+('Qualified agreement' if r['contract']=='L4' else 'Agreement under mapping')+r' \\' for r in contract_rows))
    short={'AGREEMENT':'A','DISAGREEMENT':'D','ASSUMPTION_MISMATCH':'M','INCONCLUSIVE':'I'}
    fault_label={'missing_evidence':'missing counts','premature_update':'premature commitment'}
    tex_table('faults.tex','\n'.join(fault_label.get(r['fault'],r['fault'].replace('_',' '))+f" & {r['detected']}/{r['n']} & "+' & '.join(short[r['vector'][cid]] for cid in ['L1','L2','L3','L4','N1','N2','N3','N4'])+f" & {r['dejavu_passed']}/{r['n']}"+r' \\' for r in fault_rows))
    tex_table('timing.tex','\n'.join(f"{r['evaluations']} & {r['baseline']['median']:.3f} & {r['verified']['median']:.3f} & {r['added_median']:.3f} & [{r['added_bootstrap_95'][0]:.3f}, {r['added_bootstrap_95'][1]:.3f}]"+r' \\' for r in timing))
    tex_table('logical_scaling.tex','\n'.join(f"{r['updates']} & {r['terms']} & {r['true']} & {r['false']} & {r['seconds']:.2f}"+r' \\' for r in sorted(legacy_scales,key=lambda r:r['updates'])))
    tex_table('numeric_traces.tex','\n'.join(f"{r['name']} & {r['qubits']} & {r['terms']} & {r['records']} & {r['status']}"+r' \\' for r in trace_summary))
    tex_table('hardware.tex','\n'.join(r['condition'].replace('_',r'\_')+f" & {r['evaluations']} & {comma(r['pubs'])} & {comma(r['physical_shots'])} & {r['online']}/{r['replay']}"+r' \\' for r in hw))
    tex_table('storm_timing.tex','\n'.join(f"{int(r['K'])} & {float(r['dtmc_construction_time_s']):.3f} & {float(r['storm_checking_time_s']):.3f}"+r' \\' for r in scaling))
    # Source-of-truth manifest hashes every actual experimental input read.
    sources=[RUN/'stage1/pre_execution.json',RUN/'stage1/pre_execution.seal.json',RUN/'stage1/configuration.json',RUN/'stage1/quantitative.json',RUN/'stage1/gaussian-kernels.npz',RUN/'stage1/gaussian.tra',RUN/'stage1/gaussian.lab',RUN/'stage1/storm.log',RUN/'stage1/nuxmv.log',RUN/'stage2/baseline/results.json',RUN/'stage2/faults/results.json',RUN/'comparison/verdict_agreement.json',RUN/'completion_audit.json',EXP/'AUDIT_REPORT.md',EXP/'config/contracts.json',WORK/'Formal_Verification_in_Hybrid_Quantum_Classical_Computing_Systems/restructured.tex',SCALING/'metadata.json',SCALING/'scalability_results.csv',TIMING/'runs.csv',TIMING/'summary.json',TIMING/'completion_audit.json',HARDWARE/'artifacts/results/h2_sampler_comparison_20260907/campaign_summary.json',OLDPROB/'layer4_empirical/fakebackend_runs.jsonl',OLDPROB/'layer4_empirical/fakebackend_metadata.json',lr/'refined_verification_results.txt',WORK/'NuXmv Files/VQE_Phase_Reachability/results/reachability.csv',checker,*paths]
    sources += list((RUN/'stage1').glob('dafny-*.log'))
    sources += [EXP/p for p in pre['sources']]
    sources += [WORK/'Probabilistic verification - 2 methods comparision/model_checking_scalability.py']
    sources += [RUN/r['trace'] for r in results+faults['results']]
    sources += [RUN/r['control_trace'] for r in faults['results'] if 'control_trace' in r]
    sources += list(lr.glob('scale_*_time.txt'))+list(lr.glob('scale_*_result.txt'))
    physical_runs = resolve_recorded_path(TIMING/'runs')
    sources += [TIMING/'runs'/p.relative_to(physical_runs)
                for p in physical_runs.glob('*/*/n*/r*/run_summary.json')]
    for name in ['baseline','faults']: sources += [RUN/f'stage2/{name}/dejavu.log',RUN/f'stage2/{name}/temporal-input.tsv']
    for name in ['statevector','hardware']: sources += [HARDWARE/p for p in hwsummary[name]['paths'].values()]
    save(DATA/'source_manifest.json',{'experiment':str(RUN.relative_to(WORK)),'configuration_digest':pre['configuration_digest'],'pre_execution_digest':seal,'sources':{str(p.relative_to(WORK)):sha(p) for p in sorted(set(sources))}})
    (PAPER/'SOURCE_OF_TRUTH.md').write_text('# Reconstructed source of truth\n\nFinal run: `approved-experiment`; audit: `AUDIT_REPORT.md` dated 2026-10-06.\n\n'+f"Configuration digest: `{pre['configuration_digest']}`. Stage 1 seal: `{seal}`.\n\n"+'The complete machine-readable result list is `data/derived_results.json`; every quantitative prose value is generated in `data/claim_values.json` and `data/numbers.tex`. All input hashes are in `data/source_manifest.json`.\n\n'+'## Reporting decisions\n\n- Primary: final sealed run only. Earlier same-seed directories are excluded.\n- P2/P3: retain the original marginal intervals; report compatibility after the audit-recommended Holm correction. This is a post-audit reporting correction, not a rerun, reseeding, or a preregistered equivalence test.\n- L4: agreement is restricted to prospectively checked terminal absorption and budget bounds; termination reasons have runtime evidence only.\n- N1/N3: parity mapping and unique physical group identity remain assumptions; Dafny does not establish them.\n- Baseline online/replay uses the same Python class. DejaVu independently checks only its five temporal projections.\n- All five fault rows retain their full vectors, including the L1 missing-evidence reporting artifact.\n- The benchmark is described by its actual two-qubit operator; legacy H2 filenames remain unchanged.\n- Archived time-unrolled scalability and September runtime costs are separate layer-specific evaluations; no pooling or cost claim for the final closed-loop run.\n- Independent audit Monte Carlo arrays are missing; no numerical re-use or plotted supplement.\n- No joint theorem, physical-backend correctness, Gaussian approximation-error certificate, automatic repair loop, or general scalability law is claimed.\n')
    print(json.dumps({'n':n,'successes':len(successful),'P2_raw_p':p2['p_raw'],'P2_Holm_p':p2['p_holm'],'raw_evaluations':evals,'raw_shots':total_shots,'sources_hashed':len(set(sources))},indent=2))

if __name__=='__main__': main()
