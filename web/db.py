#!/usr/bin/env python3
"""SQLite persistence for violation reports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "violations.db"
UPLOAD_DIR = DATA_DIR / "uploads"
ORIGINAL_DIR = UPLOAD_DIR / "original"
BOXED_DIR = UPLOAD_DIR / "boxed"
PROCESSED_DIR = UPLOAD_DIR / "processed"


@dataclass
class Violation:
    id: int
    created_at: str
    latitude: float | None
    longitude: float | None
    original_path: str
    boxed_path: str | None
    processed_path: str | None
    plate_number: str
    reason: str


def ensure_dirs() -> None:
    for path in (DATA_DIR, ORIGINAL_DIR, BOXED_DIR, PROCESSED_DIR):
        path.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def insert_violation(
    *,
    latitude: float | None,
    longitude: float | None,
    original_path: str,
    boxed_path: str | None,
    processed_path: str | None,
    plate_number: str,
    reason: str,
    created_at: str | None = None,
) -> int:
    ts = created_at or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO violations (
                created_at, latitude, longitude,
                original_path, boxed_path, processed_path,
                plate_number, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts,
                latitude,
                longitude,
                original_path,
                boxed_path,
                processed_path,
                plate_number,
                reason,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_violations(limit: int = 200) -> list[Violation]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM violations
            ORDER BY datetime(created_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_violation(row) for row in rows]


def get_violation(violation_id: int) -> Violation | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM violations WHERE id = ?",
            (violation_id,),
        ).fetchone()
    return _row_to_violation(row) if row else None


def _row_to_violation(row: sqlite3.Row) -> Violation:
    return Violation(
        id=row["id"],
        created_at=row["created_at"],
        latitude=row["latitude"],
        longitude=row["longitude"],
        original_path=row["original_path"],
        boxed_path=row["boxed_path"],
        processed_path=row["processed_path"],
        plate_number=row["plate_number"],
        reason=row["reason"],
    )


def init_db() -> None:
    ensure_dirs()
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                original_path TEXT NOT NULL,
                boxed_path TEXT,
                processed_path TEXT,
                plate_number TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.commit()
