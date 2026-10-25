"""SQLite helpers: connection, explicit transactions, and the two added session tables."""
import sqlite3
from contextlib import contextmanager

from config import get_settings

_EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_sessions (
    session_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    pending_proposal_json TEXT
);
CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    # isolation_level=None -> autocommit; writes use tx() for explicit transactions.
    conn = sqlite3.connect(get_settings().db_path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(_EXTRA_SCHEMA)
    return conn


@contextmanager
def tx(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
