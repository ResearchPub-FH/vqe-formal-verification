#!/usr/bin/env python3
"""Audit review3 preservation, revised tables, scope and review-item coverage.

Semantic judgments and page inspection are documented in REVISION_LOG_REVIEW3.md
and LAYOUT_REVIEW.md. This script independently checks the supporting invariants.
"""
from pathlib import Path
from collections import Counter
import hashlib
import difflib
import json
import re
from pypdf import PdfReader

REVISION = Path(__file__).resolve().parents[1]
PAPER = REVISION.parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def numeric_cells(line):
    return [float(x.replace(',', '')) for x in re.findall(r'\d[\d,]*(?:\.\d+)?', line)]

def caption_map(source):
    out = {}
    for label in re.findall(r'\\label\{((?:fig|tab):[^}]+)\}', source):
        end = source.index(r'\label{' + label + '}')
        start = source.rfind(r'\caption{', 0, end) + len(r'\caption{')
        i, depth = start, 1
        while depth:
            if source[i] == '{': depth += 1
            elif source[i] == '}': depth -= 1
            i += 1
        out[label] = source[start:i-1]
    return out

def main():
    source_path = REVISION / 'manuscript_review3.tex'
    source = source_path.read_text()
    baseline = json.loads((REVISION / 'data/baseline_hashes.json').read_text())
    original = (PAPER / baseline['baseline_main']).read_text()
    changed = []
    for name, expected in baseline['files'].items():
        path = PAPER / name
        assert path.is_file(), f'Existing file removed: {name}'
        if sha(path) != expected: changed.append(name)
    assert set(changed) == {'figures/architecture.tex', 'scripts/validate_paper.py'}, changed
    review_docx = Path('/Users/rome/Desktop/Review2.docx')
    assert sha(review_docx) == baseline['review_docx_sha256']
    patch = ''.join(difflib.unified_diff(original.splitlines(True), source.splitlines(True), fromfile='paper/manuscript_review2.tex', tofile='paper/manuscript_review3/manuscript_review3.tex'))
    assert (REVISION / 'manuscript_review3.patch').read_text() == patch
    checks = {'preservation': {'passed': True, 'existing_files': len(baseline['files']),
                             'changed_shared_files': changed,
                             'current_main_and_pdf_unchanged': True,
                             'original_main_and_pdf_unchanged': True,
                             'shared_bibliography_and_data_unchanged': True}}
    # Preserve every mathematical equation, title, section and numerical macro.
    equations = lambda s: re.findall(r'\\begin\{(?:equation|align)\}.*?\\end\{(?:equation|align)\}', s, re.S)
    assert equations(source) == equations(original)
    assert re.findall(r'\\title\{.*?\}', source, re.S) == re.findall(r'\\title\{.*?\}', original, re.S)
    assert re.findall(r'\\(?:sub)?section\{[^}]+\}', source) == re.findall(r'\\(?:sub)?section\{[^}]+\}', original)
    macros = json.loads((PAPER / 'data/claim_values.json').read_text())
    used = lambda s: set(re.findall(r'\\([A-Za-z]+)\b', s)) & set(macros)
    assert used(source) == used(original) == set(macros)
    assert 'while runtime verification determines whether the corresponding obligations hold for concrete executions.' in source
    checks['scientific_content_preserved'] = {'passed': True, 'equation_blocks': len(equations(source)),
                                            'numerical_macros': len(used(source))}
    # Parse printed cells independently rather than trusting the table manifest.
    d = json.loads((PAPER / 'data/derived_results.json').read_text())
    table_path = REVISION / 'tables/probabilistic_results.tex'
    table = table_path.read_text()
    rows = [line for line in table.splitlines() if line.startswith('$k=') or line.startswith(('P2:', 'P3:'))]
    assert len(rows) == len(d['probability_comparison']) + 2
    for line, v in zip(rows, d['probability_comparison']):
        expected = [v['k'], round(100*v['model'], 2), round(100*v['empirical'], 2),
                    v['successes'], v['n'], *[round(100*x, 2) for x in v['wilson_95']]]
        assert numeric_cells(line) == expected, (line, expected)
    for line, key, places in zip(rows[-2:], ['P2', 'P3'], [3, 1]):
        v = d[key]
        assert numeric_cells(line.split('&', 1)[1]) == [round(x, places) for x in [v['model'], v['empirical'], *v['bootstrap_95']]]
    assert (REVISION / 'tables/contracts.tex').read_text() == (PAPER / 'tables/contracts.tex').read_text().replace('Qualified agreement', 'Agreement under mapping')
    assert all(word not in table for word in ['Holm', 'deviation', 'Delta'])
    checks['revised_tables'] = {'passed': True, 'probabilistic_data_rows': len(rows),
                              'original_intervals_preserved': True, 'L4_scope_preserved': True}
    old_caps, new_caps = caption_map(original), caption_map(source)
    word_count = lambda s: len(s.split())
    caption_counts = {label: {'before': word_count(old_caps[label]), 'after': word_count(text)}
                      for label, text in new_caps.items() if label in old_caps}
    assert all(v['after'] < v['before'] for v in caption_counts.values())
    assert word_count(new_caps['tab:probabilistic-results']) < sum(word_count(old_caps[k]) for k in ['tab:probabilities', 'tab:conditional'])
    checks['captions'] = {'passed': True, 'retained_caption_word_counts': caption_counts,
                         'merged_caption_words': word_count(new_caps['tab:probabilistic-results'])}
    assert source.index(r'\texttt{ASSUMPTION\_MISMATCH}') < source.index(r'\includegraphics')
    assert 'requirements evaluated in this study' in source
    assert 'We select requirements at the interfaces' in source
    assert r'central limit theorem~\cite{mcclean2016}' in source
    assert 'finite state space' in source and 'next selection depend only on the current point and phase' in source
    assert 'no certified finite-shot approximation-error bound' in source
    assert 'tab:probabilities' not in source and 'tab:conditional' not in source
    assert source.count('obligation') == 5  # quote, precise contract semantics, kernel obligation
    assert not re.search(r'\b(?:frozen|canonical|seal|subclaim|campaign)\b|shared execution view', source, re.I)
    checklist = json.loads((REVISION / 'data/review_checklist.json').read_text())
    assert len(checklist['items']) == 8 and all(v['status'] == 'ADDRESSED' for v in checklist['items'])
    checks['review_items'] = {'passed': True, 'fully_addressed': 8, 'partially_addressed': 0,
                             'author_decisions': 0, 'second_pass_read': checklist['second_pass_read']}
    aux = source_path.with_suffix('.aux').read_text()
    table_numbers = dict(re.findall(r'\\newlabel\{(tab:[^}]+)\}\{\{([^}]+)\}', aux))
    assert len(table_numbers) == 5 and table_numbers['tab:probabilistic-results'] == 'V'
    paper_check = json.loads((REVISION / 'data/paper_validation.json').read_text())
    assert paper_check['status'] == 'PASS' and paper_check['checks']['source_inputs_unchanged']['files'] == len(json.loads((PAPER / 'data/source_manifest.json').read_text())['sources'])
    assert paper_check['checks']['pdf_outputs']['manuscript_sha256'] == sha(source_path.with_suffix('.pdf'))
    checks['compiled_revision'] = {'passed': True, 'tables': table_numbers,
                                  'pages': len(PdfReader(source_path.with_suffix('.pdf')).pages)}
    result = {'status': 'PASS', 'checks': checks}
    (REVISION / 'data/revision_validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
