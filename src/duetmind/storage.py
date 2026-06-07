from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
import weakref
from dataclasses import dataclass
from pathlib import Path
from threading import RLock, local
from typing import Dict

from duetmind.exceptions import IntegrityViolationError
from duetmind.models import ControlSignal


@dataclass
class LedgerBlock:
    id_bloque: str
    timestamp: float
    fase_id: int
    run_id: str
    hash_manifiesto: str
    hash_anterior: str
    tabla_dependencias: Dict[str, str]


class Storage:
    _VOLATILE_COMPONENT_KEYS = {"intent_anchor"}

    def __init__(self, db_path: str | Path = "duetmind.db", run_id: str = "") -> None:
        self.db_path = str(db_path)
        self.run_id = run_id or str(uuid.uuid4())
        self._thread_local = local()
        self._lock = RLock()
        self._ledger_cache: Dict[str, str] = {}
        self._ledger_cache_run_id = ""
        self._finalizer = weakref.finalize(self, Storage._finalize_connection, self._thread_local)
        self._init_db()
        self._init_genesis_block()

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._thread_local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._thread_local.conn = conn
        return conn

    @staticmethod
    def _finalize_connection(thread_local: local) -> None:
        conn = getattr(thread_local, "conn", None)
        if conn is not None:
            conn.close()
            thread_local.conn = None

    def close(self) -> None:
        with self._lock:
            Storage._finalize_connection(self._thread_local)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _execute(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Cursor:
        with self._lock:
            conn = self._connect()
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor

    def _fetchall(self, sql: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
        conn = self._connect()
        return conn.execute(sql, params).fetchall()

    def _fetchone(self, sql: str, params: tuple[object, ...] = ()) -> tuple[object, ...] | None:
        conn = self._connect()
        return conn.execute(sql, params).fetchone()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    phase_id INTEGER NOT NULL,
                    run_id TEXT NOT NULL DEFAULT '',
                    attempt INTEGER NOT NULL DEFAULT 1,
                    signal TEXT NOT NULL DEFAULT '',
                    manifest_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (phase_id, run_id, attempt)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phase_id INTEGER NOT NULL,
                    iteration INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    score REAL,
                    reason TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ledger (
                    id_bloque TEXT PRIMARY KEY,
                    phase_id INTEGER NOT NULL,
                    run_id TEXT NOT NULL DEFAULT '',
                    hash_manifiesto TEXT NOT NULL,
                    hash_anterior TEXT NOT NULL,
                    tabla_dependencias_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS phase_results (
                    phase_id INTEGER PRIMARY KEY,
                    phase_name TEXT NOT NULL,
                    environment TEXT NOT NULL,
                    model_tier TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    score REAL NOT NULL,
                    reason TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_phase_id ON telemetry(phase_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_created_at ON telemetry(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_phase_id ON ledger(phase_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_created_at ON ledger(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phase_results_environment ON phase_results(environment)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phase_results_created_at ON phase_results(created_at)")
            conn.commit()

        self._ensure_ledger_run_id_column()
        self._ensure_snapshot_columns()

    def _ensure_ledger_run_id_column(self) -> None:
        row = self._fetchone("SELECT COUNT(*) FROM pragma_table_info('ledger') WHERE name = 'run_id'")
        has_run_id = int(row[0]) > 0 if row else False
        if not has_run_id:
            self._execute("ALTER TABLE ledger ADD COLUMN run_id TEXT NOT NULL DEFAULT ''")
        self._execute("CREATE INDEX IF NOT EXISTS idx_ledger_run_id ON ledger(run_id)")

    def _ensure_snapshot_columns(self) -> None:
        columns = {
            str(row[1])
            for row in self._fetchall("PRAGMA table_info('snapshots')")
            if len(row) > 1
        }

        if "run_id" not in columns:
            self._execute("ALTER TABLE snapshots ADD COLUMN run_id TEXT NOT NULL DEFAULT ''")
        if "attempt" not in columns:
            self._execute("ALTER TABLE snapshots ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1")
        if "signal" not in columns:
            self._execute("ALTER TABLE snapshots ADD COLUMN signal TEXT NOT NULL DEFAULT ''")

        self._execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_phase_run_attempt
            ON snapshots(phase_id, run_id, attempt)
            """
        )
        self._execute("CREATE INDEX IF NOT EXISTS idx_snapshots_phase_run ON snapshots(phase_id, run_id)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_snapshots_signal ON snapshots(signal)")
        self._execute("CREATE INDEX IF NOT EXISTS idx_snapshots_created_at ON snapshots(created_at)")

    def _init_genesis_block(self) -> None:
        existing = self._fetchone("SELECT 1 FROM ledger WHERE phase_id = 0 AND run_id = '' LIMIT 1")
        if existing is None:
            genesis_manifest = {
                "__genesis__": "duetmind_v0",
                "__schema_version__": "1",
            }
            self.append_ledger(0, genesis_manifest)
            return

        if not self._ledger_cache:
            rows = self._fetchall("SELECT tabla_dependencias_json FROM ledger WHERE phase_id = 0 AND run_id = ''")
            cache: Dict[str, str] = {}
            for row in rows:
                cache.update(json.loads(row[0]))
            self._ledger_cache = cache
            self._ledger_cache_run_id = self.run_id

    def has_go_snapshot(self, phase_id: int, run_id: str | None = None) -> bool:
        effective_run = self.run_id if run_id is None else run_id
        row = self._fetchone(
            """
            SELECT 1
            FROM snapshots
            WHERE phase_id = ? AND run_id = ? AND signal IN (?, ?)
            LIMIT 1
            """,
            (
                phase_id,
                effective_run,
                ControlSignal.FREEZE_ADVANCE.value,
                ControlSignal.CONVERGE_CONDITIONAL.value,
            ),
        )
        return row is not None

    def get_snapshot(self, phase_id: int, run_id: str | None = None) -> dict[str, str] | None:
        effective_run = self.run_id if run_id is None else run_id
        go_signals = (ControlSignal.FREEZE_ADVANCE.value, ControlSignal.CONVERGE_CONDITIONAL.value)

        row = self._fetchone(
            """
            SELECT manifest_json
            FROM snapshots
            WHERE phase_id = ? AND run_id = ? AND signal IN (?, ?)
            ORDER BY attempt DESC
            LIMIT 1
            """,
            (phase_id, effective_run, go_signals[0], go_signals[1]),
        )
        if row is None:
            row = self._fetchone(
                """
                SELECT manifest_json
                FROM snapshots
                WHERE phase_id = ? AND run_id = ?
                ORDER BY attempt DESC
                LIMIT 1
                """,
                (phase_id, effective_run),
            )
        return json.loads(row[0]) if row else None

    def save_snapshot(
        self,
        phase_id: int,
        manifest: dict[str, str],
        signal: str = "",
        run_id: str | None = None,
    ) -> None:
        effective_run = self.run_id if run_id is None else run_id
        row = self._fetchone(
            "SELECT COALESCE(MAX(attempt), 0) FROM snapshots WHERE phase_id = ? AND run_id = ?",
            (phase_id, effective_run),
        )
        next_attempt = int(row[0]) + 1 if row and row[0] is not None else 1
        self._execute(
            """
            INSERT INTO snapshots(phase_id, run_id, attempt, signal, manifest_json, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                phase_id,
                effective_run,
                next_attempt,
                signal,
                json.dumps(manifest, sort_keys=True),
                time.time(),
            ),
        )

    def append_telemetry(
        self,
        phase_id: int,
        iteration: int,
        state: str,
        score: float | None,
        reason: str,
    ) -> None:
        self._execute(
            """
            INSERT INTO telemetry(phase_id, iteration, state, score, reason, created_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (phase_id, iteration, state, score, reason, time.time()),
        )

    def save_phase_result(
        self,
        phase_id: int,
        phase_name: str,
        environment: str,
        model_tier: str,
        signal: str,
        score: float,
        reason: str,
    ) -> None:
        self._execute(
            """
            INSERT INTO phase_results(
                phase_id, phase_name, environment, model_tier,
                signal, score, reason, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(phase_id) DO UPDATE SET
                phase_name = excluded.phase_name,
                environment = excluded.environment,
                model_tier = excluded.model_tier,
                signal = excluded.signal,
                score = excluded.score,
                reason = excluded.reason,
                created_at = excluded.created_at
            """,
            (
                phase_id,
                phase_name,
                environment,
                model_tier,
                signal,
                score,
                reason,
                time.time(),
            ),
        )

    def list_phase_results(
        self,
        phase_id: int | None = None,
        environment: str | None = None,
    ) -> list[dict[str, str | float | int]]:
        clauses = []
        params: list[str | int] = []
        if phase_id is not None:
            clauses.append("phase_id = ?")
            params.append(phase_id)
        if environment is not None:
            clauses.append("environment = ?")
            params.append(environment)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._fetchall(
            f"""
            SELECT phase_id, phase_name, environment, model_tier, signal, score, reason
            FROM phase_results
            {where_sql}
            ORDER BY phase_id
            """,
            tuple(params),
        )
        return [
            {
                "phase_id": row[0],
                "phase_name": row[1],
                "environment": row[2],
                "model_tier": row[3],
                "signal": row[4],
                "score": row[5],
                "reason": row[6],
            }
            for row in rows
        ]

    def export_phase_results_json(
        self,
        path: str | Path,
        phase_id: int | None = None,
        environment: str | None = None,
    ) -> None:
        rows = self.list_phase_results(phase_id=phase_id, environment=environment)
        with Path(path).open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, indent=2, sort_keys=True)

    def list_snapshots(self, phase_id: int | None = None) -> list[dict[str, str | float | int]]:
        clauses = []
        params: list[int] = []
        if phase_id is not None:
            clauses.append("phase_id = ?")
            params.append(phase_id)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._fetchall(
            f"""
            SELECT phase_id, run_id, attempt, signal, manifest_json, created_at
            FROM snapshots
            {where_sql}
            ORDER BY phase_id, run_id, attempt
            """,
            tuple(params),
        )
        return [
            {
                "phase_id": row[0],
                "run_id": row[1],
                "attempt": row[2],
                "signal": row[3],
                "manifest": json.loads(row[4]),
                "created_at": row[5],
            }
            for row in rows
        ]

    def telemetry_summary(
        self,
        phase_id: int | None = None,
    ) -> list[dict[str, float | int | str]]:
        clauses = []
        params: list[int] = []
        if phase_id is not None:
            clauses.append("phase_id = ?")
            params.append(phase_id)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._fetchall(
            f"""
            SELECT phase_id, state, COUNT(*) AS event_count, AVG(score) AS avg_score
            FROM telemetry
            {where_sql}
            GROUP BY phase_id, state
            ORDER BY phase_id, state
            """,
            tuple(params),
        )
        return [
            {
                "phase_id": row[0],
                "state": row[1],
                "event_count": row[2],
                "avg_score": row[3] if row[3] is not None else 0.0,
            }
            for row in rows
        ]

    def list_ledger_blocks(self, phase_id: int | None = None) -> list[dict[str, str | float | int | dict[str, str]]]:
        clauses = []
        params: list[int] = []
        if phase_id is not None:
            clauses.append("phase_id = ?")
            params.append(phase_id)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._fetchall(
            f"""
            SELECT id_bloque, phase_id, hash_manifiesto, hash_anterior, tabla_dependencias_json, created_at
            FROM ledger
            {where_sql}
            ORDER BY created_at
            """,
            tuple(params),
        )
        return [
            {
                "id_bloque": row[0],
                "phase_id": row[1],
                "hash_manifiesto": row[2],
                "hash_anterior": row[3],
                "tabla_dependencias": json.loads(row[4]),
                "created_at": row[5],
            }
            for row in rows
        ]

    def export_audit_bundle_json(
        self,
        path: str | Path,
        phase_id: int | None = None,
        environment: str | None = None,
    ) -> None:
        bundle = {
            "phase_results": self.list_phase_results(phase_id=phase_id, environment=environment),
            "telemetry": self.telemetry_summary(phase_id=phase_id),
            "snapshots": self.list_snapshots(phase_id=phase_id),
            "ledger": self.list_ledger_blocks(phase_id=phase_id),
        }
        with Path(path).open("w", encoding="utf-8") as handle:
            json.dump(bundle, handle, indent=2, sort_keys=True)

    def _get_last_ledger_hash(self) -> str:
        row = self._fetchone(
            """
            SELECT hash_manifiesto
            FROM ledger
            WHERE run_id IN ('', ?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (self.run_id,),
        )
        return row[0] if row else "0" * 64

    def append_ledger(self, phase_id: int, manifest: dict[str, str]) -> LedgerBlock:
        raw = json.dumps(manifest, sort_keys=True)
        hash_actual = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        with self._lock:
            hash_anterior = self._get_last_ledger_hash()
        effective_run_id = "" if phase_id == 0 else self.run_id

        deps: Dict[str, str] = {
            comp_id: hashlib.sha256(str(comp_data).encode("utf-8")).hexdigest()
            for comp_id, comp_data in manifest.items()
            if comp_id not in self._VOLATILE_COMPONENT_KEYS
        }

        block = LedgerBlock(
            id_bloque=str(uuid.uuid4()),
            timestamp=time.time(),
            fase_id=phase_id,
            run_id=effective_run_id,
            hash_manifiesto=hash_actual,
            hash_anterior=hash_anterior,
            tabla_dependencias=deps,
        )

        self._execute(
            """
            INSERT INTO ledger(
                id_bloque, phase_id, run_id, hash_manifiesto, hash_anterior,
                tabla_dependencias_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                block.id_bloque,
                block.fase_id,
                block.run_id,
                block.hash_manifiesto,
                block.hash_anterior,
                json.dumps(block.tabla_dependencias, sort_keys=True),
                block.timestamp,
            ),
        )
        if effective_run_id in {"", self.run_id}:
            self._ledger_cache.update(block.tabla_dependencias)
            self._ledger_cache_run_id = self.run_id
        return block

    def assert_integrity(self, manifest_propuesto: dict[str, str]) -> None:
        consolidado = dict(self._ledger_cache) if self._ledger_cache_run_id == self.run_id else {}
        if not consolidado:
            rows = self._fetchall(
                "SELECT tabla_dependencias_json FROM ledger WHERE run_id IN ('', ?)",
                (self.run_id,),
            )
            for row in rows:
                consolidado.update(json.loads(row[0]))
            self._ledger_cache = consolidado
            self._ledger_cache_run_id = self.run_id

        for comp_id, comp_data in manifest_propuesto.items():
            if comp_id in self._VOLATILE_COMPONENT_KEYS:
                continue
            if comp_id in consolidado:
                proposed_hash = hashlib.sha256(str(comp_data).encode("utf-8")).hexdigest()
                if consolidado[comp_id] != proposed_hash:
                    raise IntegrityViolationError(comp_id, consolidado[comp_id], proposed_hash)

    def verify_integrity(self, manifest_propuesto: dict[str, str]) -> bool:
        try:
            self.assert_integrity(manifest_propuesto)
        except IntegrityViolationError:
            return False
        return True
