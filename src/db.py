from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_PATH


class Database:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    applicant_code TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def get_code(self, telegram_id: int) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT applicant_code FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ).fetchone()
        return str(row["applicant_code"]) if row else None

    def upsert_code(self, telegram_id: int, code: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (telegram_id, applicant_code, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    applicant_code = excluded.applicant_code,
                    updated_at = excluded.updated_at
                """,
                (telegram_id, code, now, now),
            )
