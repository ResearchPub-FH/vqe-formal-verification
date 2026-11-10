#!/usr/bin/env python3
"""Audit generated numerical prose, tables, plots, references and input preservation.

This is a consistency audit, not a substitute for scientific/visual review.
Checks use artifact data and independent parsing of the generated outputs.
"""
from pathlib import Path
from collections import Counter
from statistics import NormalDist
import argparse, csv, hashlib, json, math, re, sys
import numpy as np
from pypdf import PdfReader
from artifact_paths import verify_recorded_sources

PAPER=Path(__file__).resolve().parents[1]; WORK=PAPER.parent.parent
def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p): return list(csv.DictReader(Path(p).open()))
def numbers(s): return [float(v.replace(',','')) for v in re.findall(r'(?<![A-Za-z])\d[\d,]*(?:\.\d+)?',s)]
def near(actual,expected,tol=5.01e-4):
    assert len(actual)==len(expected),(actual,expected)
    for a,b in zip(actual,expected): assert abs(a-b)<=tol,(a,b,tol)
def table(name):
    return [r.split('&') for r in (PAPER/'tables'/name).read_text().splitlines() if '&' in r]
def wilson(s,n):
    z=NormalDist().inv_cdf(.975);p=s/n;den=1+z*z/n
    c=(p+z*z/(2*n))/den;rad=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return (0 if s==0 else max(0,c-rad),1 if s==n else min(1,c+rad))

def main():
    versions=list(PAPER.glob('manuscript_review*.tex'))
    default=max(versions,key=lambda p:int(re.search(r'_review(\d+)\.tex$',p.name)[1])).name if versions else 'manuscript.tex'
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manuscript',default=default,help='Main source to audit (default: latest existing revision).')
    args=parser.parse_args(); main_source=(PAPER/args.manuscript).resolve(); stem=main_source.stem
    assert main_source.is_file() and main_source.is_relative_to(PAPER)
    output_root=main_source.parent
    (output_root/'data').mkdir(exist_ok=True)
    checks={}; d=read(PAPER/'data/derived_results.json');cfg=d['configuration']
    manifest=read(PAPER/'data/source_manifest.json')
    source_locations=verify_recorded_sources(manifest['sources'])
    (output_root/'data/source_location_resolution.json').write_text(json.dumps(source_locations,indent=2)+'\n')
    checks['source_inputs_unchanged']={'passed':True,'files':len(manifest['sources']),
                                      'relocated_paths':source_locations['relocated_source_count']}
    cm=read(PAPER/'data/claim_values.json'); tex=(PAPER/'data/numbers.tex').read_text()
    parsed=dict(re.findall(r'\\newcommand\{\\([A-Za-z]+)\}\{(.+)\\xspace\}',tex))
    assert parsed==cm
    source=main_source.read_text()
    macro_calls=set(re.findall(r'\\([A-Za-z]+)\b',source)) & set(cm)
    checks['numerical_prose_macros']={'passed':True,'defined':len(cm),'used':len(macro_calls)}
    # Configuration literals in mathematics/text are permitted fixed parameters,
    # and checked against the actual frozen record where consequential.
    assert cfg['initial_index']==[3,11,6,14] and cfg['coordinate_schedule']==[0,1,2,3]
    assert cfg['measurement_groups']==[['ZI','ZZ'],['YZ'],['XX']]
    assert cfg['hamiltonian']['terms']=={'YZ':3980,'ZI':-3980,'ZZ':-113,'XX':1810}
    assert cfg['energy_tolerance']==cfg['expectation_tolerance']==1e-12
    checks['fixed_parameters_match']={'passed':True}
    # Every probability point, not just the published checkpoints.
    T=np.array([t if t is not None else -1 for t in d['success_steps_from_raw']]);n=len(T)
    pc=rows(PAPER/'data/probability_figure_points.csv')
    assert len(pc)==cfg['maximum_updates']+1
    for r in pc:
        k=int(r['k']);s=int(((T>=0)&(T<=k)).sum());lo,hi=wilson(s,n)
        assert int(r['successes'])==s and int(r['n'])==n
        near([float(r[c]) for c in ['model_probability','empirical_probability','wilson_low','wilson_high']],[d['model_cdf_recomputed'][k],s/n,lo,hi],1e-14)
    sc=rows(PAPER/'data/scalability_figure_points.csv')
    for r,v in zip(sc,d['scaling']):
        assert int(r['K'])==int(v['K'])
        assert int(r['reachable_states'])==int(v['reachable_states']) and int(r['transitions'])==int(v['transitions'])
        near([float(r[c]) for c in ['construction_seconds','checking_median_seconds']],
             [float(v['dtmc_construction_time_s']),float(v['storm_checking_time_s'])],1e-14)
    rc=rows(PAPER/'data/runtime_figure_points.csv')
    assert len(rc)==len(d['timing'])
    for r,v in zip(rc,d['timing']):
        assert int(r['evaluations'])==v['evaluations']
        near([float(r[x]) for x in ['baseline_median','baseline_low','baseline_high','verified_median','verified_low','verified_high','added_median','added_low','added_high']],
             [v['baseline']['median'],*v['baseline']['median_bootstrap_95'],v['verified']['median'],*v['verified']['median_bootstrap_95'],v['added_median'],*v['added_bootstrap_95']],1e-14)
    checks['all_plotted_points']={'passed':True,'probability_points':len(pc),'model_size_pairs':len(sc),'timing_groups':len(rc)}
    if (PAPER/'data/fault_figure_points.csv').is_file():
        fc=rows(PAPER/'data/fault_figure_points.csv')
        library=read(PAPER.parent/'config/contracts.json')
        ids=[cid for cid,spec in library.items() if spec['family'] in ('logical','numeric')]
        # The fault figure plots the reference run (artifacts/experiment); d['faults'] still describes
        # approved-experiment, so its cells are reconstructed here from that run's raw fault records.
        frun=PAPER.parent/'artifacts/experiment'
        assert sha(frun/'stage2/faults/results.json')==read(frun/'comparison/verdict_agreement.json')['result_files']['faults']
        fr=read(frun/'stage2/faults/results.json')['results']
        expected_cells={}
        for name in sorted({r['fault'] for r in fr}):
            rr=[r for r in fr if r['fault']==name]
            vectors=[{cid:r['contracts'][cid]['runtime_verdict'] for cid in ids} for r in rr]
            assert all(x==vectors[0] for x in vectors)
            v={'expected_contract':rr[0]['expected_contract'],'expected_verdict':rr[0]['expected_verdict'],'n':len(rr),
               'detected':sum(r['detected_as_expected'] for r in rr),'dejavu_passed':sum(r['dejavu']['passed'] for r in rr),'vector':vectors[0]}
            expected_cells.update({(name,cid):v for cid in ids})
        assert len(fc)==len(expected_cells)
        assert {(r['fault'],r['contract']) for r in fc}==set(expected_cells)
        for r in fc:
            v=expected_cells[r['fault'],r['contract']]
            assert r['verdict']==v['vector'][r['contract']]
            assert r['expected_contract']==v['expected_contract'] and r['expected_verdict']==v['expected_verdict']
            assert [int(r[key]) for key in ['n','detected','dejavu_passed']]==[v[key] for key in ['n','detected','dejavu_passed']]
        checks['all_plotted_points']['fault_matrix_cells']=len(fc)
    # Validate each numerical cell after LaTeX formatting/rounding.
    expected_rows={'probabilities.tex':len(d['probability_comparison']),'conditional.tex':2,
                   'timing.tex':len(d['timing']),'logical_scaling.tex':len(d['legacy_logical']['scales']),
                   'numeric_traces.tex':len(d['numeric_traces']),'hardware.tex':len(d['hardware_runtime']),
                   'storm_timing.tex':len(d['scaling']),'contracts.tex':len(d['contracts']),'faults.tex':len(d['faults'])}
    for filename,count in expected_rows.items(): assert len(table(filename))==count,filename
    for r,v in zip(table('probabilities.tex'),d['probability_comparison']):
        near(numbers('&'.join(r)),[v['k'],v['successes'],n,100*v['model'],100*v['empirical'],100*v['wilson_95'][0],100*v['wilson_95'][1],100*v['absolute_difference'],*([v['p_holm']] if 'p_holm' in v else [])],.00501)
    for r,v in zip(table('conditional.tex'),[d['P2'],d['P3']]):
        vals=numbers('&'.join(r[1:]));expected=[v['model'],v['empirical'],*v['bootstrap_95'],v['absolute_difference']]
        if 'p_holm' in v: expected.append(v['p_holm'])
        near(vals,expected,.05001 if 'derived_from' in v else .000501)
    for r,v in zip(table('timing.tex'),d['timing']): near(numbers('&'.join(r)),[v['evaluations'],v['baseline']['median'],v['verified']['median'],v['added_median'],*v['added_bootstrap_95']])
    for r,v in zip(table('logical_scaling.tex'),sorted(d['legacy_logical']['scales'],key=lambda x:x['updates'])): near(numbers('&'.join(r)),[v['updates'],v['terms'],v['true'],v['false'],v['seconds']],.00501)
    for r,v in zip(table('numeric_traces.tex'),d['numeric_traces']):
        near(numbers('&'.join(r[1:])),[v['qubits'],v['terms'],v['records']],0);assert 'PASS' in r[-1]
    for r,v in zip(table('hardware.tex'),d['hardware_runtime']): near(numbers('&'.join(r[1:])),[v['evaluations'],v['pubs'],v['physical_shots']],0)
    for r,v in zip(table('storm_timing.tex'),d['scaling']): near(numbers('&'.join(r)),[int(v['K']),float(v['dtmc_construction_time_s']),float(v['storm_checking_time_s'])])
    for r,v in zip(table('contracts.tex'),d['contracts']): assert numbers(r[2])==[v['runtime_counts']['AGREEMENT'],n]
    short={'AGREEMENT':'A','DISAGREEMENT':'D','ASSUMPTION_MISMATCH':'M','INCONCLUSIVE':'I'}
    for r,v in zip(table('faults.tex'),d['faults']):
        assert numbers(r[1])==[v['detected'],v['n']]
        assert [x.strip() for x in r[2:10]]==[short[v['vector'][cid]] for cid in ['L1','L2','L3','L4','N1','N2','N3','N4']]
        assert numbers(r[-1])==[v['dejavu_passed'],v['n']]
    checks['generated_tables']={'passed':True,'tables':len(list((PAPER/'tables').glob('*.tex')))}
    # A correction cannot silently substitute a new confidence interval.
    original=read(PAPER.parent/'artifacts/approved-experiment/comparison/verdict_agreement.json')
    assert d['P2']['bootstrap_95']==original['conditional_means'][0]['bootstrap_95']
    assert d['P2']['empirical']==original['conditional_means'][0]['runtime_mean']
    assert d['P2']['p_holm']>.05 and d['P3']['derived_from']=='P2'
    assert all(v.get('p_holm',1)>.05 for v in d['probability_comparison'])
    assert 'post-audit' in source and 'does not contain the model mean' in source
    checks['P2_P3_reporting_correction']={'passed':True,'original_observations_and_intervals_preserved':True,'method':'post-audit Holm adjustment; P3 derived','holm_p':d['P2']['p_holm']}
    labels=re.findall(r'\\label\{([^}]+)\}',source);references=re.findall(r'\\(?:ref|eqref)\{([^}]+)\}',source)
    assert len(labels)==len(set(labels)) and set(references)<=set(labels)
    figures=re.findall(r'\\begin\{figure\*?\}.*?\\end\{figure\*?\}',source,re.S)
    tables=re.findall(r'\\begin\{table\*?\}.*?\\end\{table\*?\}',source,re.S)
    for block in figures+tables:
        label=re.search(r'\\label\{([^}]+)\}',block)[1]
        assert label in references,label
    for block in figures:
        filename=re.search(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}',block)[1]
        assert (output_root/filename).is_file()
    assert d['timing_metadata']['bootstrap_resamples']==10000
    assert '10,000 independent-condition resamples' in source
    aux=main_source.with_suffix('.aux').read_text()
    flabels=dict(re.findall(r'\\newlabel\{(fig:[^}]+)\}\{\{([^}]+)\}',aux))
    expected_flabels={re.search(r'\\label\{([^}]+)\}',block)[1]:str(i)
                      for i,block in enumerate(figures,1)}
    assert flabels==expected_flabels
    bib=(PAPER/'references.bib').read_text(); keys=set(re.findall(r'@\w+\{([^,]+)',bib))
    assert set(k for c in re.findall(r'\\cite\{([^}]+)\}',source) for k in c.split(','))<=keys
    checks['figure_table_and_citation_references']={'passed':True,'figures':len(figures),'tables':len(tables),'labels':len(labels)}
    log=main_source.with_suffix('.log').read_text()
    assert 'Overfull' not in log
    assert not re.search(r'LaTeX Warning: (?:Reference|Citation) .+undefined',log)
    assert 'Misplaced' not in log and '! ' not in log
    checks['latex_compilation']={'passed':True,'overfull_boxes':0,'undefined_references':0,'underfull_notes':log.count('Underfull')}
    # Vector check: all figure PDFs retain text and no raster image XObjects.
    pdfs={}
    figure_paths=[output_root/re.search(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}',block)[1]
                  for block in figures]
    for p in sorted(figure_paths):
        reader=PdfReader(p);text=''.join(page.extract_text() for page in reader.pages); images=0
        for page in reader.pages:
            res=page.get('/Resources');res=res.get_object() if res else {}
            xo=res.get('/XObject',{});xo=xo.get_object() if hasattr(xo,'get_object') else xo
            images+=sum(obj.get_object().get('/Subtype')=='/Image' for obj in xo.values())
        assert len(reader.pages)==1 and len(text)>40 and images==0,p
        pdfs[p.name]={'pages':len(reader.pages),'retained_text_characters':len(text),'raster_images':images,'sha256':sha(p)}
    assert len(pdfs)==len(figures)
    paper=PdfReader(main_source.with_suffix('.pdf')); text='\n'.join(p.extract_text() for p in paper.pages)
    assert 'CROSSLAYERRELATIONSHIPSANDAGREEMENT' in re.sub(r'[^A-Z]','',text.upper())
    assert all(cm[k] in text for k in ['PrimaryEmpiricalPercent','PrimaryModelPercent','PMeanAdjustedP','TotalShots'])
    checks['pdf_outputs']={'passed':True,'manuscript_pages':len(paper.pages),'manuscript_sha256':sha(main_source.with_suffix('.pdf')),'vector_figures':pdfs}
    # Record all literal numerals for manual audit: IDs, fixed mathematics,
    # methodological counts and bibliography years are distinguished from
    # measured quantities (which must come through generated macros/tables).
    literals=[{'line':i,'text':line} for i,line in enumerate(source.splitlines(),1) if re.search(r'\d',line) and not line.lstrip().startswith('%')]
    (output_root/'data/literal_numeric_lines.json').write_text(json.dumps(literals,indent=2)+'\n')
    output={'status':'PASS','manuscript':str(main_source.relative_to(PAPER)),'scope':'numerical/artifact/reference/vector consistency; manual layout review recorded separately','checks':checks}
    (output_root/'data/paper_validation.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))

if __name__=='__main__': main()
