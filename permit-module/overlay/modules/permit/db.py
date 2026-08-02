#!/usr/bin/env python3
"""SQLite persistence for vehicle permits (permit module)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent
OPENSOURCE_ROOT = MODULE_ROOT.parent.parent
DATA_DIR = OPENSOURCE_ROOT / "data"
DB_PATH = DATA_DIR / "permits.db"


@dataclass
class Permit:
    id: int
    plate_number: str
    name: str
    campus: str
    department: str
    student_id: str | None
    note: str | None
    created_at: str
    updated_at: str


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_plate(plate: str) -> str:
    return plate.strip().upper().replace(" ", "")


def init_db() -> None:
    ensure_dirs()
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS permits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                campus TEXT NOT NULL,
                department TEXT NOT NULL,
                student_id TEXT,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_permit(row: sqlite3.Row) -> Permit:
    return Permit(
        id=row["id"],
        plate_number=row["plate_number"],
        name=row["name"],
        campus=row["campus"],
        department=row["department"],
        student_id=row["student_id"],
        note=row["note"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_permits(limit: int = 500) -> list[Permit]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM permits
            ORDER BY datetime(updated_at) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_permit(row) for row in rows]


def get_permit_by_id(permit_id: int) -> Permit | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM permits WHERE id = ?",
            (permit_id,),
        ).fetchone()
    return _row_to_permit(row) if row else None


def get_permit_by_plate(plate: str) -> Permit | None:
    plate = normalize_plate(plate)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM permits WHERE plate_number = ?",
            (plate,),
        ).fetchone()
    return _row_to_permit(row) if row else None


def insert_permit(
    *,
    plate_number: str,
    name: str,
    campus: str,
    department: str,
    student_id: str | None = None,
    note: str | None = None,
) -> int:
    ts = _now()
    plate = normalize_plate(plate_number)
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO permits (
                plate_number, name, campus, department,
                student_id, note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plate,
                name.strip(),
                campus.strip(),
                department.strip(),
                (student_id or "").strip() or None,
                (note or "").strip() or None,
                ts,
                ts,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_permit(
    permit_id: int,
    *,
    plate_number: str,
    name: str,
    campus: str,
    department: str,
    student_id: str | None = None,
    note: str | None = None,
) -> bool:
    plate = normalize_plate(plate_number)
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE permits SET
                plate_number = ?,
                name = ?,
                campus = ?,
                department = ?,
                student_id = ?,
                note = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                plate,
                name.strip(),
                campus.strip(),
                department.strip(),
                (student_id or "").strip() or None,
                (note or "").strip() or None,
                _now(),
                permit_id,
            ),
        )
        conn.commit()
        return cur.rowcount > 0


def delete_permit(permit_id: int) -> bool:
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM permits WHERE id = ?", (permit_id,))
        conn.commit()
        return cur.rowcount > 0
