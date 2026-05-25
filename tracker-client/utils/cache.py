from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class LocalEventCache:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tracker_event_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()

    def enqueue(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO tracker_event_queue (event_type, payload_json) VALUES (?, ?)",
                (event_type, json.dumps(payload)),
            )
            connection.commit()

    def fetch_batch(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, event_type, payload_json FROM tracker_event_queue ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": row[0],
                "event_type": row[1],
                "payload": json.loads(row[2]),
            }
            for row in rows
        ]

    def delete(self, event_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM tracker_event_queue WHERE id = ?", (event_id,))
            connection.commit()
