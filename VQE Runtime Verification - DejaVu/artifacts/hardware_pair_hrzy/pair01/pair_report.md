# Hardware pair `pair01`: unverified vs verified

- Backend `ibm_marrakesh`, qubits [139, 135], frozen circuits `9b954576c69801ac`.
- Order: unverified then verified.
- Unverified: 50 evaluations, stop `max_iterations`, status `completed`.
- Verified: 50 evaluations, stop `max_iterations`, online `pass`, replay `pass`.
- Charged QPU: 150 s + 150 s.

| N | Fidelity U | Fidelity V | Change (V-U) | Added client time (s) | Elapsed diff (s) | Held |
|---:|---:|---:|---:|---:|---:|---|
| 10 | 0.998788 | 0.998472 | -0.000317 | 0.828 | +60.4 |  |
| 20 | 0.997374 | 0.997899 | +0.000525 | 1.347 | +169.8 |  |
| 30 | 0.996822 | 0.997022 | +0.000200 | 1.848 | +183.3 |  |
| 40 | 0.996520 | 0.996631 | +0.000111 | 2.376 | +189.8 |  |
| 50 | 0.996324 | 0.996507 | +0.000183 | 2.885 | +238.8 |  |

| Run | Client (s) | IBM wait (s) | Total (s) | Best measured | Exact at final | Gap to E_ref |
|---|---:|---:|---:|---:|---:|---:|
| Unverified | 0.264 | 399.7 | 399.9 | -0.6434 | -0.6729 | 0.0300 |
| Verified | 3.158 | 635.6 | 638.8 | -0.6469 | -0.6770 | 0.0259 |
