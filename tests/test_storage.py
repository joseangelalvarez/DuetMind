import tempfile
import unittest
from pathlib import Path

from duetmind.storage import Storage


class TestStorage(unittest.TestCase):
    def test_snapshot_and_ledger_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)

            manifest = {"component_a": "value1", "component_b": "value2"}
            storage.save_snapshot(1, manifest)
            self.assertEqual(storage.get_snapshot(1), manifest)

            block = storage.append_ledger(1, manifest)
            self.assertTrue(block.hash_manifiesto)
            self.assertTrue(storage.verify_integrity(manifest))

    def test_integrity_rejects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            manifest = {"component_a": "value1"}
            storage.append_ledger(1, manifest)

            mutated = {"component_a": "value2"}
            self.assertFalse(storage.verify_integrity(mutated))


if __name__ == "__main__":
    unittest.main()
