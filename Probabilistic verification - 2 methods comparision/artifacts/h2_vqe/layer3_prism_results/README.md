# Layer 3 — PRISM results

Run the PRISM command in `../layer2_prism/README.md`, then run:

```bash
python h2_prism_fakebackend_workflow.py summarize-prism \
  --success-csv artifacts/h2_vqe/layer3_prism_results/prism_success_curve.csv
```

This creates `prism_properties.csv` and inserts the PRISM values into the
Layer 4 comparison table. The conditional expectations are calculated from
the PRISM first-success distribution, so non-converged paths are not assigned
zero and do not enter the denominator.
