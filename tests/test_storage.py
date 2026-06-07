import tempfile
import unittest
from pathlib import Path

from duetmind.storage import Storage


class TestStorage(unittest.TestCase):
    def test_genesis_block_inserted_on_init(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            genesis_blocks = storage.list_ledger_blocks(phase_id=0)
            self.assertGreaterEqual(len(genesis_blocks), 1)
            self.assertGreaterEqual(len(storage._ledger_cache), 1)
            storage.close()

    def test_verify_integrity_phase1_not_trivially_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            self.assertFalse(storage.verify_integrity({"__schema_version__": "2"}))
            storage.close()

    def test_integrity_violation_detected_after_genesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db")
            self.assertFalse(storage.verify_integrity({"__genesis__": "tampered"}))
            storage.close()

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
            storage.close()

    def test_integrity_rejects_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            manifest = {"component_a": "value1"}
            storage.append_ledger(1, manifest)

            mutated = {"component_a": "value2"}
            self.assertFalse(storage.verify_integrity(mutated))
            storage.close()


if __name__ == "__main__":
    unittest.main()
