# Shot-count sensitivity of P(50)

`P(50)` denotes `P(F<=50 "success")`.  Each shot count is the number of
shots allocated to each of the three commuting measurement groups for every
candidate evaluation.  The Gaussian series uses ideal Born moments and a
finite-shot Gaussian approximation.  The empirical series uses 400 direct
adaptive executions on the noisy FakeJakarta snapshot.  The 1024-shot point reuses the existing 400-run baseline trace.

| Shots/group | Gaussian P(50) | Empirical P(50) | 95% Wilson CI |
|---:|---:|---:|---:|
| 256 | 0.540106 | 0.447500 (179/400) | [0.399500, 0.496499] |
| 512 | 0.760711 | 0.607500 (243/400) | [0.558840, 0.654114] |
| 1024 | 0.928027 | 0.867500 (347/400) | [0.830753, 0.897255] |
| 2048 | 0.989743 | 0.977500 (391/400) | [0.957797, 0.988119] |

The empirical intervals are two-sided 95% Wilson binomial intervals.  Compact
per-run traces are stored in `empirical_<shots>_runs.jsonl`; they contain the
terminal step and final parameter index but omit the large per-update histories.
`shot_sensitivity.csv` is the source for the PNG and SVG line charts.
