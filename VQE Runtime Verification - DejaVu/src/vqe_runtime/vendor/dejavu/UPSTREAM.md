# Bundled DejaVu runtime

- Repository: https://github.com/havelund/dejavu
- Commit: `ffffac2ee04679f09ee11bf6f142d97fd6d39403`
- License: Apache License 2.0; see `LICENSE.txt`
- Bundled Scala runtime: 2.12.21
- `dejavu.jar` SHA-256: `99fbc72ac9ba0dbf8051691f4c15958e1694345a025840acfd344d1eb66d58e1`
- `vqe-three-level-monitor.jar` SHA-256: pinned in `monitor-manifest.json`

The upstream commit is pinned because it restores the intended wide scope of capital `Forall` and `Exists` quantifiers and rebuilds the fat JAR for Scala 2.12.

`vqe-three-level-monitor.jar` contains the generated monitor for
`specs/vqe_runtime.qtl` plus `tools/SynchronousBridge.scala`. Runtime requires
only Java, these two JARs, and `monitor-manifest.json`. Rebuilding requires the
Scala 2.12.21 compiler.

The generated JAR also embeds `VQE_MONITOR_BUILD.json`, containing SHA-256
digests for the QTL specification, Scala bridge, and DejaVu runtime. The test
suite and runtime startup reject a stale monitor whose embedded inputs,
external JAR hash, and available sources do not match.
