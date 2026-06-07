import json
import tempfile
import unittest
from pathlib import Path

from duetmind.packaging import PackagingPlatform, build_backend_packaging_plan, prepare_backend_packaging_staging, write_backend_spec


class TestPackaging(unittest.TestCase):
    def test_build_backend_packaging_plan_defaults_to_windows(self) -> None:
        plan = build_backend_packaging_plan()
        self.assertEqual(plan.platform, PackagingPlatform.WINDOWS)
        self.assertEqual(plan.app_name, "backend_core.exe")
        self.assertEqual(plan.spec_name, "backend_core.spec")
        self.assertIn("duetmind.orchestrator", plan.hidden_imports)

    def test_write_backend_spec_contains_pyinstaller_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backend.spec"
            write_backend_spec(path, build_backend_packaging_plan(PackagingPlatform.LINUX))
            content = path.read_text(encoding="utf-8")
            self.assertIn("Analysis(", content)
            self.assertIn("backend_core", content)
            self.assertIn("duetmind.storage", content)

    def test_prepare_backend_packaging_staging_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = prepare_backend_packaging_staging(tmp)
            self.assertTrue((root / "backend_core.spec").exists())
            self.assertTrue((root / "backend-packaging-manifest.json").exists())
            self.assertTrue((root / "build-backend.ps1").exists())

            manifest = json.loads((root / "backend-packaging-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["app_name"], "backend_core.exe")
            self.assertEqual(manifest["platform"], "windows")


if __name__ == "__main__":
    unittest.main()
