import json
import tempfile
import unittest
from pathlib import Path

from duetmind.distribution import DistributionPlatform, build_distribution_manifest, prepare_distribution_staging, write_distribution_manifest


class TestDistribution(unittest.TestCase):
    def test_build_distribution_manifest_defaults_to_windows_layout(self) -> None:
        manifest = build_distribution_manifest()
        self.assertEqual(manifest.platform, DistributionPlatform.WINDOWS)
        self.assertEqual(manifest.launcher.relative_path, "launcher.exe")
        self.assertEqual(manifest.backend.relative_path, "resources/backend_core.exe")
        self.assertEqual(manifest.database.relative_path, "resources/database.sqlite")

    def test_prepare_distribution_staging_creates_expected_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = prepare_distribution_staging(tmp)
            self.assertTrue((root / "resources" / "engines" / "ollama").exists())
            self.assertTrue((root / "resources" / "models" / "llm").exists())
            self.assertTrue((root / "workspace").exists())
            self.assertTrue((root / "distribution-manifest.json").exists())
            self.assertTrue((root / "launcher-config.json").exists())

            manifest = json.loads((root / "distribution-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["platform"], "windows")
            self.assertEqual(manifest["backend"]["relative_path"], "resources/backend_core.exe")

    def test_write_distribution_manifest_serializes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            write_distribution_manifest(path, build_distribution_manifest(DistributionPlatform.LINUX))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["platform"], "linux")
            self.assertEqual(data["launcher"]["relative_path"], "launcher")


if __name__ == "__main__":
    unittest.main()
