"""Conservative durable delivery intents; ambiguous sends never retry automatically."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path


class DeliveryIntentStore:
    def __init__(self, root: Path):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.database = root / "delivery-intents.sqlite"
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS intents "
                "(key TEXT PRIMARY KEY, identity TEXT NOT NULL, state TEXT NOT NULL, "
                "message_ids TEXT NOT NULL, evidence TEXT)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS intent_events "
                "(id INTEGER PRIMARY KEY, key TEXT NOT NULL, state TEXT NOT NULL, "
                "recorded_at TEXT NOT NULL, evidence TEXT)"
            )

    def _connect(self):
        return sqlite3.connect(self.database, timeout=30)

    @staticmethod
    def _event(connection, key, state, evidence=None):
        connection.execute(
            "INSERT INTO intent_events(key,state,recorded_at,evidence) VALUES(?,?,?,?)",
            (key, state, datetime.now(UTC).isoformat(), evidence),
        )

    def begin(self, key: str, *, route: str, target_hash: str, artifact_sha256: str) -> bool:
        if (
            not key
            or not route
            or not all(
                re.fullmatch(r"[a-f0-9]{64}", value) for value in (target_hash, artifact_sha256)
            )
        ):
            raise ValueError("invalid intent identity")
        identity = json.dumps([route, target_hash, artifact_sha256])
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT identity,state FROM intents WHERE key=?", (key,)
            ).fetchone()
            if existing and existing[0] != identity:
                raise ValueError("intent identity conflict")
            if existing and existing[1] != "not_sent":
                return False
            connection.execute(
                "INSERT INTO intents VALUES(?,?,?, ?,NULL) "
                "ON CONFLICT(key) DO UPDATE SET state=excluded.state, "
                "message_ids=excluded.message_ids, evidence=NULL",
                (key, identity, "sending", "[]"),
            )
            self._event(connection, key, "sending")
            return True

    def acknowledge(self, key: str, *, message_ids: Sequence[str]) -> None:
        if isinstance(message_ids, str) or any(not isinstance(value, str) for value in message_ids):
            raise ValueError("invalid message IDs")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            changed = connection.execute(
                "UPDATE intents SET state=?,message_ids=? WHERE key=? AND state=?",
                ("confirmed", json.dumps(list(message_ids)), key, "sending"),
            )
            if changed.rowcount != 1:
                raise ValueError("intent acknowledgement state conflict")
            self._event(connection, key, "confirmed")

    def resolve(self, key: str, *, outcome: str, evidence: str) -> None:
        if outcome not in {"sent", "not_sent"} or not evidence.strip():
            raise ValueError("resolution requires outcome and evidence")
        state = "confirmed" if outcome == "sent" else "not_sent"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state,evidence FROM intents WHERE key=?", (key,)
            ).fetchone()
            if row is None:
                raise ValueError("unknown intent")
            if row == (state, evidence):
                return
            if row[0] not in {"sending", "unknown"}:
                raise ValueError("resolution cannot rewrite resolved intent")
            connection.execute(
                "UPDATE intents SET state=?,evidence=? WHERE key=?", (state, evidence, key)
            )
            self._event(connection, key, state, evidence)

    def outcome(self, key: str) -> str:
        with self._connect() as connection:
            row = connection.execute("SELECT state FROM intents WHERE key=?", (key,)).fetchone()
        return "missing" if row is None else "unknown" if row[0] == "sending" else row[0]

    def message_ids(self, key: str) -> list[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT message_ids FROM intents WHERE key=?", (key,)
            ).fetchone()
        return [] if row is None else json.loads(row[0])
