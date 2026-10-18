"""SQLite persistence for completed research runs and replayable evidence."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from contextlib import contextmanager

from .models import DiscoveryReport


DEFAULT_DB_PATH = Path("data") / "runs" / "alphatrace.sqlite3"


class ResearchStore:
    """Persist report envelopes and indexed audit objects in SQLite."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("ALPHATRACE_DB_PATH") or DEFAULT_DB_PATH
        self.path = Path(configured)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    company_symbol TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    report_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS evidence_links (
                    run_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    source_document_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    role TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, evidence_id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS claims (
                    run_id TEXT NOT NULL,
                    claim_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    claim_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, claim_id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS conflicts (
                    run_id TEXT NOT NULL,
                    conflict_id TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    resolution_status TEXT NOT NULL,
                    conflict_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, conflict_id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );
                """
            )

    def save_report(self, report: DiscoveryReport) -> None:
        """Save a report atomically, including its indexed audit trail."""

        payload = report.to_dict()
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                """
                INSERT OR REPLACE INTO runs
                    (run_id, mode, company_symbol, status, created_at, report_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    report.run_id,
                    report.mode,
                    report.company.symbol,
                    "complete",
                    created_at,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            connection.execute("DELETE FROM events WHERE run_id = ?", (report.run_id,))
            connection.execute("DELETE FROM evidence_links WHERE run_id = ?", (report.run_id,))
            connection.execute("DELETE FROM claims WHERE run_id = ?", (report.run_id,))
            connection.execute("DELETE FROM conflicts WHERE run_id = ?", (report.run_id,))
            connection.executemany(
                """
                INSERT INTO events (run_id, sequence, stage, action, status, event_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        report.run_id,
                        event.sequence,
                        event.stage,
                        event.action,
                        event.status,
                        json.dumps(asdict(event), ensure_ascii=False),
                    )
                    for event in report.events
                ],
            )
            connection.executemany(
                """
                INSERT INTO evidence_links
                    (run_id, evidence_id, source_document_id, source_url, role, verification_status, evidence_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        report.run_id,
                        evidence.id,
                        evidence.source_document_id,
                        evidence.url,
                        evidence.role,
                        evidence.verification_status,
                        json.dumps(asdict(evidence), ensure_ascii=False),
                    )
                    for evidence in report.evidence
                ],
            )
            connection.executemany(
                "INSERT INTO claims (run_id, claim_id, status, claim_json) VALUES (?, ?, ?, ?)",
                [
                    (report.run_id, claim.id, claim.status, json.dumps(asdict(claim), ensure_ascii=False))
                    for claim in report.claims
                ],
            )
            connection.executemany(
                """
                INSERT INTO conflicts (run_id, conflict_id, severity, resolution_status, conflict_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        report.run_id,
                        conflict.id,
                        conflict.severity,
                        conflict.resolution_status,
                        json.dumps(asdict(conflict), ensure_ascii=False),
                    )
                    for conflict in report.conflicts
                ],
            )

    def get_report(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT report_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return json.loads(row["report_json"]) if row else None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT run_id, mode, company_symbol, status, created_at FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def _get_indexed(self, table: str, column: str, run_id: str, order_by: str = "rowid") -> list[dict[str, Any]]:
        allowed = {
            "events": ("event_json", "sequence"),
            "evidence_links": ("evidence_json", "rowid"),
            "claims": ("claim_json", "rowid"),
            "conflicts": ("conflict_json", "rowid"),
        }
        if table not in allowed or column != allowed[table][0] or order_by != allowed[table][1]:
            raise ValueError("Unsupported research index")
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT {column} FROM {table} WHERE run_id = ? ORDER BY {order_by}",
                (run_id,),
            ).fetchall()
        return [json.loads(row[column]) for row in rows]

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        return self._get_indexed("events", "event_json", run_id, "sequence")

    def get_evidence(self, run_id: str) -> list[dict[str, Any]]:
        return self._get_indexed("evidence_links", "evidence_json", run_id)

    def get_claims(self, run_id: str) -> list[dict[str, Any]]:
        return self._get_indexed("claims", "claim_json", run_id)

    def get_conflicts(self, run_id: str) -> list[dict[str, Any]]:
        return self._get_indexed("conflicts", "conflict_json", run_id)
