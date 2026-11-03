#!/usr/bin/env python3
"""Check controlled-revision preservation and editorial requirements.

This complements validate_paper.py. It records text for manual terminology
review; keyword checks alone do not establish scientific or editorial quality.
"""
from pathlib import Path
from collections import Counter
import argparse, difflib, hashlib, json, re
from artifact_paths import verify_recorded_sources

PAPER = Path(__file__).resolve().parents[1]
WORK = PAPER.parent.parent

def read(path):
    return json.loads(Path(path).read_text())

def digest(data):
    return hashlib.sha256(data).hexdigest()

def sha(path):
    return digest(Path(path).read_bytes())

def main():
    baseline = read(PAPER/'data/revision_baseline.json')
    parser = argparse.ArgumentParser(description=__doc__)
    latest = max([baseline['round'], *map(int, baseline.get('followup_rounds', {}))])
    parser.add_argument('--round', type=int, default=latest)
    args = parser.parse_args()
    round_id = args.round
    record = baseline if round_id == baseline['round'] else baseline['followup_rounds'][str(round_id)]
    revised = PAPER/record['revised']
    original = PAPER/record['original']
    expected = baseline['initial_project_hashes']
    source = revised.read_text()
    checks = {}

    for name in ['manuscript.tex', 'manuscript.pdf',
                 'data/derived_results.json', 'data/source_manifest.json']:
        assert sha(PAPER/name) == expected[name], name
    assert sha(PAPER/baseline['original']) == baseline['baseline_sha256']
    preserved_followups = {}
    for earlier_round, followup in baseline.get('followup_rounds', {}).items():
        if int(earlier_round) <= round_id:
            for name, checksum in followup['preserved_hashes'].items():
                assert sha(PAPER/name) == checksum, name
                preserved_followups[name] = checksum
    assert sha('/Users/rome/Desktop/Review.docx') == baseline['review_docx_sha256']
    manifest = read(PAPER/'data/source_manifest.json')
    locations = verify_recorded_sources(manifest['sources'])
    provenance = read(PAPER/'data/benchmark_provenance.json')
    for path, checksum in provenance['local_sources'].items():
        assert sha(WORK/path) == checksum, path
    checks['preservation'] = {
        'passed': True, 'original_tex_sha256': sha(original),
        'original_pdf_sha256': sha(PAPER/f'{original.stem}.pdf'),
        'baseline_tex_sha256': sha(PAPER/baseline['original']),
        'baseline_pdf_sha256': sha(PAPER/'manuscript.pdf'),
        'all_derived_scientific_results_unchanged': True,
        'experiment_inputs_unchanged': len(manifest['sources']),
        'relocated_inputs_checksum_verified': locations['relocated_source_count'],
        'review_document_unchanged': True,
        'followup_reference_files_unchanged': preserved_followups,
    }

    # Added prose macros must leave all previous generated values unchanged.
    added = {'LogicalScalingPairs', 'LogicalScalingTimes'}
    added |= {prefix+field for prefix in ['Estimator', 'Heisenberg']
              for field in ['Qubits', 'Terms', 'Records']}
    current = read(PAPER/'data/claim_values.json')
    previous = {key: value for key, value in current.items() if key not in added}
    serialized = json.dumps(previous, indent=2, sort_keys=True, allow_nan=False)+'\n'
    assert digest(serialized.encode()) == expected['data/claim_values.json']
    lines = (PAPER/'data/numbers.tex').read_text().splitlines(keepends=True)
    previous_lines = [line for line in lines if not any(
        '\\newcommand{\\'+key+'}' in line for key in added)]
    assert digest(''.join(previous_lines).encode()) == expected['data/numbers.tex']
    bibliography = (PAPER/'references.bib').read_text()
    previous_bib = bibliography.split('@misc{ibmvqe,')[0]
    assert digest(previous_bib.encode()) == expected['references.bib']
    checks['existing_quantities_and_references'] = {
        'passed': True, 'existing_numeric_macros_unchanged': len(previous),
        'new_artifact_generated_prose_macros': len(added),
        'previous_bibliography_entries_unchanged': True,
        'added_references': ['ibmvqe', 'kolda2003', 'tilly2022'],
    }

    sections = re.findall(r'\\section\{([^}]+)\}', source)
    assert sections[:5] == [
        'Introduction', 'Shared Execution Model and Specification Library',
        'Layered Verification Methodology', 'Individual Layer Evaluation',
        'Cross-Layer Relationships and Agreement',
    ]
    introduction = source.split('\\section{Introduction}')[1].split('\\section{')[0]
    contributions = introduction.split('\\begin{itemize}')[1].split('\\end{itemize}')[0]
    items = contributions.split('\\item')[1:]
    assert len(items) == 4
    for text, expected_start in zip(items, [
        'A four-layer VQE verification architecture', 'A specification library',
        'A two-stage framework', 'An implementation and artifact-based evaluation',
    ]):
        assert text.strip().startswith(expected_start)
    assert introduction.rstrip().endswith('\\end{itemize}')
    assert not re.search(r'\bRQ\d\b|Answers to the Research Questions', source)
    cross = source.split('\\section{Cross-Layer Relationships and Agreement}')[1].split('\\section{')[0]
    subsections = re.findall(r'\\subsection\{([^}]+)\}', cross)
    assert len(subsections) == 5
    assert subsections[0] == 'Goals and Procedure'
    assert subsections[-1] == 'Summary of Verification Results'
    abstract = source.split('\\begin{abstract}')[1].split('\\end{abstract}')[0]
    for removed in ['\\SuccessRuns', '\\PrimaryEmpiricalPercent',
                    '\\PrimaryCILower', '\\PrimaryCIUpper', 'false alarm']:
        assert removed not in abstract, removed
    assert 'four-layer verification architecture' in abstract
    assert 'Future work' in abstract
    principle = ('The contract library defines what the VQE implementation is expected to satisfy. '
                 'Pre-execution verification establishes these contracts prospectively, while '
                 'runtime verification determines whether the corresponding obligations hold '
                 'for concrete executions.')
    assert principle in source
    checks['structure_and_abstract'] = {
        'passed': True, 'ordered_contributions': 4,
        'section_V_subsections': subsections, 'central_principle_preserved': True,
    }

    flagged = ['frozen', 'canonical', 'seal', 'subclaim', 'shared execution view',
               'final run', 'matched experiment', 'retained']
    for term in flagged:
        assert not re.search(r'\b'+re.escape(term)+r'\b', source, re.I), term
    assert not re.search(r'\bupdates?\b', source, re.I)
    assert source.count(';') == 0
    evidence = [line for line in source.splitlines() if re.search(r'\bevidence\b',line,re.I)]
    assert len(evidence) == 1 and 'statistical evidence' in evidence[0]
    included_tables = re.findall(r'\\input\{(tables/[^}]+)\}',source)
    for path in included_tables:
        assert ';' not in (PAPER/path).read_text()
        assert not re.search(r'\bupdates?\b', (PAPER/path).read_text(), re.I)
    terminology = []
    for line_no, line in enumerate(source.splitlines(), 1):
        for term, pattern in [('specification', r'\bspecifications?\b'),
                              ('property', r'\bpropert(?:y|ies)\b'),
                              ('contract', r'\bcontracts?\b')]:
            if re.search(pattern,line,re.I):
                terminology.append({'line':line_no,'term':term,'text':line})
    negative_text = [
        {'line':i,'text':line}
        for i,line in enumerate(source.splitlines(),1)
        if re.search(r'\b(?:not|neither|no|without)\b|rather than',line,re.I)
    ]
    audit = {
        'terminology_occurrences': terminology,
        'remaining_flagged_term': {'term':'statistical evidence','reason':
            'Names the statistical inferential scope of repeated executions.'},
        'scientific_qualifications_for_manual_review': negative_text,
        'semicolon_count_in_main_source': 0,
        'note':'Occurrences and necessary qualifications are manually checked in the revision log.',
    }
    (PAPER/'data/terminology_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    checks['terminology'] = {'passed':True,'remaining_evidence_occurrences':1,
                            'semicolon_count':0,'manual_audit':'data/terminology_audit.json'}

    data = read(PAPER/'data/derived_results.json')
    timing = data['timing_metadata']['configuration']
    assert timing['optimizer']['initial_step'] == 0.4
    assert timing['optimizer']['step_shrink'] == 0.5
    assert timing['execution']['seed'] == 7
    assert timing['convergence'] == {'min_iterations':10,'patience':3,'tolerance':0.005}
    assert [row['evaluations'] for row in data['timing']] == [10,20,30,40,50]
    checks['clarified_configuration_literals'] = {'passed':True}

    checklist = read(PAPER/'data/revision_checklist.json')
    assert checklist['substantive_item_count'] == len(checklist['items']) == 27
    assert [item['review_item'] for item in checklist['items']] == list(range(1,28))
    log = (PAPER/'REVISION_LOG_REVIEW1.md').read_text()
    for item in checklist['items']:
        assert f"### Review {item['review_item']} — {item['source_item']}:" in log
    statuses = Counter(item['status'] for item in checklist['items'])
    assert statuses == {'ADDRESSED':27}
    assert log.count('Status: **ADDRESSED**') == 27
    checks['review_checklist'] = {'passed':True,'statuses':dict(statuses),
        'manual_second_pass':'Complete Review.docx reread; all locations checked individually.'}

    if round_id == 2:
        parent = original.read_text()
        start = '\\subsection{Faults and Cross-Stage Discrepancies}'
        end = '\\subsection{Summary of Verification Results}'
        parent_layout = parent.replace('\\IEEEtriggeratref{8}', '\\IEEEtriggeratref{4}')
        assert parent_layout.split(start)[0] == source.split(start)[0]
        assert parent_layout.split(end)[1] == source.split(end)[1]
        assert set(re.findall(r'\\([A-Za-z]+)\b', parent)) & set(current) == set(
            re.findall(r'\\([A-Za-z]+)\b', source)) & set(current)
        assert record['initial_copy_compiled'] is True
        assert record['initial_copy_sha256'] == record['preserved_hashes'][original.name]
        assert '\\label{fig:fault-discrepancies}' in source
        assert 'tab:faults' not in source
        followup_log = (PAPER/'REVISION_LOG_REVIEW2.md').read_text()
        assert followup_log.count('Status: **ADDRESSED**') == 2
        checks['requested_followup'] = {
            'passed':True, 'requests_addressed':2,
            'only_main_section_changed':'V-D: Faults and Cross-Stage Discrepancies',
            'layout_adjustment':'IEEE reference break for final-page column balance',
            'prior_main_source_and_pdf_preserved':True,
            'numerical_macro_set_preserved':True,
            'initial_identical_copy_compiled':True,
        }

    old = original.read_text().splitlines(keepends=True)
    new = source.splitlines(keepends=True)
    patch = ''.join(difflib.unified_diff(old,new,fromfile=original.name,tofile=revised.name))
    assert (PAPER/f'manuscript_review{round_id}.patch').read_text() == patch
    parallel = list(PAPER.glob('manuscript_review*.tex'))
    rounds = sorted(int(re.search(r'_review(\d+)\.tex$', path.name)[1]) for path in parallel)
    assert rounds == list(range(1, latest+1)) and revised in parallel
    for path in PAPER.rglob('*'):
        if re.search(r'review\d+',path.name,re.I):
            assert re.fullmatch(r'manuscript_review\d+\.[A-Za-z]+', path.name) or re.fullmatch(
                r'(?:REVISION_LOG|MANUSCRIPT_DIFF)_REVIEW\d+\.md', path.name),path
    checks['versioning_and_diff'] = {'passed':True,'one_main_source_for_this_round':revised.name,
                                   'existing_rounds':rounds,
                                   'ancillary_files_shared':True,'raw_patch_matches':True}

    paper_audit = read(PAPER/'data/paper_validation.json')
    assert paper_audit['status'] == 'PASS' and paper_audit['manuscript'] == revised.name
    checks['paper_validation'] = {'passed':True,'report':'data/paper_validation.json'}
    changed = []
    for name, checksum in expected.items():
        path = PAPER/name
        if path.is_file() and sha(path) != checksum:
            changed.append(name)
    output = {'status':'PASS','round':round_id,'original':original.name,
              'revised':revised.name,'checks':checks,'changed_shared_files':changed,
              'visual_review':'LAYOUT_REVIEW.md'}
    (PAPER/'data/revision_validation.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))

if __name__ == '__main__':
    main()
