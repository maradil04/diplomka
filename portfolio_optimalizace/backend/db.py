import os
import sqlite3
from pathlib import Path

from flask import g

from backend.models import SCHEMA_SQL


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "app.db"


def get_database_path() -> str:
    return os.getenv("APP_DATABASE_PATH", str(DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(get_database_path())


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(get_database_path())
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    db_path = Path(get_database_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
