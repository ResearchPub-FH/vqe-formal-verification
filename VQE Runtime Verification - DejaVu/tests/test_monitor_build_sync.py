from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MonitorBuildSyncTests(unittest.TestCase):
    def test_bundled_monitor_matches_current_qtl_bridge_and_runtime(self):
        vendor = ROOT / "src/vqe_runtime/vendor/dejavu"
        with zipfile.ZipFile(vendor / "vqe-three-level-monitor.jar") as archive:
            metadata = json.loads(archive.read("VQE_MONITOR_BUILD.json"))
        runtime_manifest = json.loads(
            (vendor / "monitor-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["schema"], 1)
        self.assertEqual(
            metadata["property_levels"],
            ["intra_iteration", "inter_iteration", "run_level"],
        )
        self.assertEqual(
            metadata["spec_sha256"], sha256(ROOT / "specs/vqe_runtime.qtl")
        )
        self.assertEqual(
            metadata["bridge_sha256"],
            sha256(ROOT / "tools/SynchronousBridge.scala"),
        )
        self.assertEqual(metadata["dejavu_sha256"], sha256(vendor / "dejavu.jar"))
        self.assertEqual(
            runtime_manifest["monitor_sha256"],
            sha256(vendor / "vqe-three-level-monitor.jar"),
        )
        self.assertEqual(
            {key: value for key, value in runtime_manifest.items() if key != "monitor_sha256"},
            metadata,
        )


if __name__ == "__main__":
    unittest.main()
