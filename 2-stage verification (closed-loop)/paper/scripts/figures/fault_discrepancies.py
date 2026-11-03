#!/usr/bin/env python3
"""Categorical fault-verdict matrix read directly from audited fault results.

Every repeated vector must agree before it can be shown as one categorical row.
Python results report overall conformance: PASS requires every recorded logical
and numeric verdict to be AGREEMENT. FAIL includes violations, invalid assumptions,
and inconclusive checks; the matrix retains these distinct per-requirement verdicts.
DejaVu results are categorical; repeated-test counts are omitted from the graphic.
Colors are nominal categories, not magnitudes; letters preserve grayscale meaning.
The layout is single column (3.5 in); fault names wrap onto two lines.
"""
import csv
import hashlib
import json
from collections import defaultdict
from style import *
from matplotlib.patches import Patch, Rectangle

# The delivered closed-loop run. Its fault-result checksum is recorded in
# comparison/verdict_agreement.json; this run has no completion_audit.json.
RUN = EXP/'artifacts/merged-model-01'

SHORT = {'AGREEMENT': 'A', 'DISAGREEMENT': 'D',
         'ASSUMPTION_MISMATCH': 'M', 'INCONCLUSIVE': 'I'}
COLORS = {'AGREEMENT': '#E9F6ED', 'DISAGREEMENT': '#D83E68',
          'ASSUMPTION_MISMATCH': '#F2A900', 'INCONCLUSIVE': '#C9D2DB'}
LABELS = {'coefficient_swap': 'Coefficient\nswap', 'corrupt_energy': 'Corrupt\nenergy',
          'missing_evidence': 'Missing\ncounts', 'premature_update': 'Premature\ncommitment',
          'shot_mismatch': 'Shot\nmismatch'}

def main(write_points=True):
    result_path = RUN/'stage2/faults/results.json'
    raw = json.loads(result_path.read_text())
    agreement = json.loads((RUN/'comparison/verdict_agreement.json').read_text())
    assert hashlib.sha256(result_path.read_bytes()).hexdigest() == agreement['result_files']['faults']
    pre = json.loads((RUN/'stage1/pre_execution.json').read_text())
    assert raw['configuration_digest'] == pre['configuration_digest']
    library = json.loads((EXP/'config/contracts.json').read_text())
    ids = [cid for cid, spec in library.items() if spec['family'] in ('logical', 'numeric')]
    grouped = defaultdict(list)
    for result in raw['results']:
        trace = RUN/result['trace']
        assert hashlib.sha256(trace.read_bytes()).hexdigest() == result['trace_sha256']
        grouped[result['fault']].append(result)

    rows = []
    cells = []
    for fault in sorted(grouped):
        results = grouped[fault]
        vector = {cid: results[0]['contracts'][cid]['runtime_verdict'] for cid in ids}
        assert all({cid: r['contracts'][cid]['runtime_verdict'] for cid in ids} == vector for r in results)
        assert len({(r['expected_contract'], r['expected_verdict']) for r in results}) == 1
        row = {'fault': fault, 'n': len(results),
               'detected': sum(r['detected_as_expected'] for r in results),
               'dejavu_passed': sum(r['dejavu']['passed'] for r in results),
               'expected_contract': results[0]['expected_contract'],
               'expected_verdict': results[0]['expected_verdict'], 'vector': vector}
        rows.append(row)
        for cid in ids:
            cells.append({key: row[key] for key in ['fault', 'n', 'detected', 'dejavu_passed',
                                                  'expected_contract', 'expected_verdict']} |
                         {'contract': cid, 'verdict': vector[cid]})
    if write_points:
        with (PAPER/'data/fault_figure_points.csv').open('w') as f:
            writer = csv.DictWriter(f, fieldnames=list(cells[0]))
            writer.writeheader()
            writer.writerows(cells)

    # Axes span the figure; coordinates are inches from the top-left corner.
    width, height = 3.5, 2.2
    fig = plt.figure(figsize=(width, height))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set(xlim=(0, width), ylim=(height, 0))
    ax.axis('off')
    pitch, cell_w, cell_h, family_gap = .225, .195, .19, .05
    first_row, row_pitch = .6, .27
    def cx(j):
        return .84 + j*pitch + (family_gap if library[ids[j]]['family'] == 'numeric' else 0)
    def cy(i):
        return first_row + i*row_pitch
    dejavu_x = cx(len(ids)-1) + .33
    python_x = dejavu_x + .385
    for i, row in enumerate(rows):
        ax.text(.03, cy(i), LABELS.get(row['fault'], row['fault'].replace('_', '\n')),
                ha='left', va='center', fontsize=7, linespacing=1.0)
        for j, cid in enumerate(ids):
            verdict = row['vector'][cid]
            ax.add_patch(Rectangle((cx(j)-cell_w/2, cy(i)-cell_h/2), cell_w, cell_h,
                                   facecolor=COLORS[verdict], edgecolor='#9099A2', lw=.35))
            ax.text(cx(j), cy(i), SHORT[verdict], ha='center', va='center', fontsize=7,
                    weight='bold' if verdict != 'AGREEMENT' else 'normal',
                    color='white' if verdict == 'DISAGREEMENT' else '#202020')
        assert row['dejavu_passed'] in (0, row['n']), 'Mixed DejaVu outcomes need a distinct display'
        python_text = 'PASS' if all(v == 'AGREEMENT' for v in row['vector'].values()) else 'FAIL'
        status = 'PASS' if row['dejavu_passed'] == row['n'] else 'FAIL'
        ax.text(dejavu_x, cy(i), status, ha='center', va='center', fontsize=6.8)
        ax.text(python_x, cy(i), python_text, ha='center', va='center', fontsize=6.8)
    for j, cid in enumerate(ids):
        ax.text(cx(j), .355, cid, ha='center', va='center', fontsize=7)
    for family in ['logical', 'numeric']:
        positions = [j for j, cid in enumerate(ids) if library[cid]['family'] == family]
        left, right = cx(min(positions))-cell_w/2, cx(max(positions))+cell_w/2
        ax.plot([left, right], [.235, .235], color='#333333', lw=.6)
        ax.text((left+right)/2, .125, family.capitalize(), ha='center', va='center', fontsize=7.2)
    ax.text(.03, .355, 'Fault', ha='left', va='center', fontsize=7)
    ax.text(dejavu_x, .28, 'DejaVu\nresult', ha='center', va='center', fontsize=6.8, linespacing=1.05)
    ax.text(python_x, .28, 'Python\nresult', ha='center', va='center', fontsize=6.8, linespacing=1.05)
    labels = {'AGREEMENT': 'Agreement (A)', 'DISAGREEMENT': 'Disagreement (D)',
              'ASSUMPTION_MISMATCH': 'Assumption mismatch (M)', 'INCONCLUSIVE': 'Inconclusive (I)'}
    handles = {v: Patch(facecolor=COLORS[v], edgecolor='#9099A2', lw=.35, label=labels[v]) for v in SHORT}
    # Two columns fill column-wise; this order reads A, D / M, I across the rows.
    order = ['AGREEMENT', 'ASSUMPTION_MISMATCH', 'DISAGREEMENT', 'INCONCLUSIVE']
    fig.legend(handles=[handles[v] for v in order], loc='lower center', bbox_to_anchor=(.5, .005), ncol=2,
               frameon=False, fontsize=6.8, handlelength=1.2, handletextpad=.5, columnspacing=1.6,
               labelspacing=.35)
    export(fig, 'fault-discrepancies.pdf')

if __name__ == '__main__':
    main()
