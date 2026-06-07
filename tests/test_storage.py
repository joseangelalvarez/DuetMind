import tempfile
import unittest
from pathlib import Path
import sqlite3

from duetmind.exceptions import IntegrityViolationError
from duetmind.models import ControlSignal
from duetmind.storage import Storage


class TestStorage(unittest.TestCase):
    def test_init_migrates_legacy_schema_before_creating_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                """
                CREATE TABLE ledger (
                    id_bloque TEXT PRIMARY KEY,
                    phase_id INTEGER NOT NULL,
                    hash_manifiesto TEXT NOT NULL,
                    hash_anterior TEXT NOT NULL,
                    tabla_dependencias_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE snapshots (
                    phase_id INTEGER NOT NULL,
                    manifest_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.commit()
            conn.close()

            storage = Storage(db_path, run_id="run-legacy")
            manifest = {"component_a": "value"}
            storage.append_ledger(1, manifest)
            storage.save_snapshot(1, manifest, signal=ControlSignal.FREEZE_ADVANCE.value)

            self.assertIsNotNone(storage.get_snapshot(1))
            storage.close()

    def test_snapshot_versioned_by_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db", run_id="run-1")
            storage.save_snapshot(1, {"v": "one"}, signal=ControlSignal.FREEZE_ADVANCE.value)
            storage.save_snapshot(1, {"v": "two"}, signal=ControlSignal.FREEZE_ADVANCE.value)

            snapshots = [row for row in storage.list_snapshots(phase_id=1) if row["run_id"] == "run-1"]
            attempts = [int(row["attempt"]) for row in snapshots]

            self.assertEqual(attempts, [1, 2])
            storage.close()

    def test_get_snapshot_prefers_go_signal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "test.db", run_id="run-1")
            storage.save_snapshot(1, {"v": "bad"}, signal=ControlSignal.ROLLBACK.value)
            storage.save_snapshot(1, {"v": "good"}, signal=ControlSignal.FREEZE_ADVANCE.value)

            snapshot = storage.get_snapshot(1)

            self.assertEqual(snapshot, {"v": "good"})
            storage.close()

    def test_get_snapshot_fallback_cross_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage_run_1 = Storage(db_path, run_id="run-a")
            storage_run_1.save_snapshot(2, {"v": "from-run-a"}, signal=ControlSignal.FREEZE_ADVANCE.value)

            storage_run_2 = Storage(db_path, run_id="run-b")
            snapshot = storage_run_2.get_snapshot(2)

            self.assertIsNone(snapshot)
            storage_run_1.close()
            storage_run_2.close()

    def test_run_id_isolation_prevents_cross_run_abort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage_run_1 = Storage(db_path, run_id="run-1")
            storage_run_1.append_ledger(1, {"component_a": "value1"})

            storage_run_2 = Storage(db_path, run_id="run-2")
            self.assertTrue(storage_run_2.verify_integrity({"component_a": "value2"}))

            storage_run_1.close()
            storage_run_2.close()

    def test_genesis_block_included_in_all_run_verifications(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage_run_1 = Storage(db_path, run_id="run-1")
            storage_run_2 = Storage(db_path, run_id="run-2")

            self.assertFalse(storage_run_2.verify_integrity({"__schema_version__": "2"}))

            storage_run_1.close()
            storage_run_2.close()

    def test_different_intents_same_schema_no_integrity_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage_run_1 = Storage(db_path, run_id="run-a")
            storage_run_1.append_ledger(1, {"architecture": "intent_alpha"})

            storage_run_2 = Storage(db_path, run_id="run-b")
            self.assertTrue(storage_run_2.verify_integrity({"architecture": "intent_beta"}))

            storage_run_1.close()
            storage_run_2.close()

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

    def test_assert_integrity_raises_typed_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            storage = Storage(db_path)
            storage.append_ledger(1, {"component_a": "value1"})

            with self.assertRaises(IntegrityViolationError) as exc:
                storage.assert_integrity({"component_a": "value2"})

            self.assertEqual(exc.exception.component_id, "component_a")
            storage.close()


if __name__ == "__main__":
    unittest.main()
