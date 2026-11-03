#!/usr/bin/env python3
"""Generate revised presentation tables from the shared audited result data.

No result values are entered manually. Existing raw and processed inputs remain
unchanged; this revision changes only table organization and the L4 display label.
"""
from pathlib import Path
import hashlib
import json
import re

REVISION = Path(__file__).resolve().parents[1]
PAPER = REVISION.parent

def main():
    source = PAPER / 'data/derived_results.json'
    d = json.loads(source.read_text())
    lines = [r'\textit{P1: bounded success probability (\%)} & & & \\']
    records = []
    for v in d['probability_comparison']:
        lo, hi = v['wilson_95']
        cells = [f"$k={v['k']}$", f"{100*v['model']:.2f}",
                 f"{100*v['empirical']:.2f} ({v['successes']}/{v['n']})",
                 f"[{100*lo:.2f}, {100*hi:.2f}]"]
        lines.append(' & '.join(cells) + r' \\')
        records.append({'kind': 'P1', 'source': v, 'cells': cells})
    lines += [r'\midrule', r'\textit{Resources conditional on bounded success} & & & \\']
    for key, label, places in [('P2', 'P2: iterations', 3), ('P3', 'P3: physical shots', 1)]:
        v = d[key]
        fmt = lambda value: f'{value:,.{places}f}'
        cells = [label, fmt(v['model']), fmt(v['empirical']),
                 f"[{fmt(v['bootstrap_95'][0])}, {fmt(v['bootstrap_95'][1])}]"]
        lines.append(' & '.join(cells) + r' \\')
        records.append({'kind': key, 'source': v, 'cells': cells})
    lines.append(r'\bottomrule')
    (REVISION / 'tables/probabilistic_results.tex').write_text('\n'.join(lines) + '\n')

    # Preserve the existing scope descriptions and formatting; normalize only
    # the presentation label. Raw L4 results already record AGREEMENT.
    existing = (PAPER / 'tables/contracts.tex').read_text()
    row = next(line for line in existing.splitlines() if line.startswith('L4 &'))
    result = next(v for v in d['contracts'] if v['contract'] == 'L4')
    assert result['verdict_agreement'] == 'AGREEMENT'
    assert result['runtime_counts']['AGREEMENT'] == len(d['success_steps_from_raw'])
    assert 'Terminal absorption and budget bounds' in row
    assert 'Qualified agreement' in row
    revised = existing.replace(row, row.replace('Qualified agreement', 'Agreement under mapping'))
    for line, v in zip([s for s in revised.splitlines() if '&' in s], d['contracts']):
        count = re.search(r'(\d+)/(\d+)', line)
        assert count and [int(x) for x in count.groups()] == [v['runtime_counts']['AGREEMENT'], len(d['success_steps_from_raw'])]
    (REVISION / 'tables/contracts.tex').write_text(revised)

    output = {'run_id': d['run_id'], 'configuration_digest': d['configuration_digest'],
              'pre_execution_digest': d['pre_execution_digest'],
              'processed_input': '../data/derived_results.json',
              'processed_input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'raw_source_manifest': '../data/source_manifest.json',
              'statistical_transformation': 'None: format existing estimates and original intervals only',
              'rows': records, 'L4': {'raw_result': result, 'display': 'Agreement under mapping'}}
    (REVISION / 'data/table_traceability.json').write_text(json.dumps(output, indent=2) + '\n')
    print('Generated merged probabilistic table and normalized L4 presentation from audited inputs.')

if __name__ == '__main__':
    main()
