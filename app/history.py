"""Run history stored in SQLite, kept separate from the portable config."""

import sqlite3
import time

from . import config

DB_PATH = config.DATA_DIR / "history.db"
MAX_OUTPUT = 200_000  # characters kept per run


def _conn() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _conn() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started REAL NOT NULL,
                finished REAL,
                script_name TEXT NOT NULL,
                server_name TEXT NOT NULL,
                host TEXT NOT NULL,
                exit_code INTEGER,
                output TEXT
            )"""
        )


def start(script_name: str, server_name: str, host: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO runs (started, script_name, server_name, host) VALUES (?, ?, ?, ?)",
            (time.time(), script_name, server_name, host),
        )
        return cur.lastrowid


def finish(run_id: int, exit_code: int | None, output: str) -> None:
    if len(output) > MAX_OUTPUT:
        output = "[...truncated...]\n" + output[-MAX_OUTPUT:]
    with _conn() as c:
        c.execute(
            "UPDATE runs SET finished = ?, exit_code = ?, output = ? WHERE id = ?",
            (time.time(), exit_code, output, run_id),
        )


def list_runs(limit: int = 100) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, started, finished, script_name, server_name, host, exit_code "
            "FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_run(run_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def clear() -> None:
    with _conn() as c:
        c.execute("DELETE FROM runs")
