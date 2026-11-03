from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MonitorBuildDependencyTests(unittest.TestCase):
    def test_manifest_pins_exact_scala_jars_and_bundled_dejavu(self):
        manifest = json.loads(
            (ROOT / "tools" / "monitor_build_dependencies.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["scala_version"], "2.12.21")
        self.assertEqual(
            set(manifest["artifacts"]),
            {"scala-compiler", "scala-library", "scala-reflect"},
        )
        for record in manifest["artifacts"].values():
            self.assertTrue(
                record["url"].startswith(
                    "https://repo.maven.apache.org/maven2/org/scala-lang/"
                )
            )
            self.assertEqual(len(record["sha256"]), 64)
            self.assertIn("2.12.21", record["filename"])
        self.assertEqual(
            manifest["bundled_dejavu"]["sha256"],
            "99fbc72ac9ba0dbf8051691f4c15958e1694345a025840acfd344d1eb66d58e1",
        )


if __name__ == "__main__":
    unittest.main()
