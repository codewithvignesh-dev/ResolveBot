"""Session ownership, message history and the single pending proposal per session."""
import json
from datetime import datetime, timezone

from database import tx


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def bind(conn, session_id: str, customer_id: str) -> bool:
    """Bind session to the first customer that uses it. True if `customer_id` owns it."""
    conn.execute(
        "INSERT OR IGNORE INTO conversation_sessions(session_id, customer_id, created_at, updated_at) "
        "VALUES (?,?,?,?)",
        (session_id, customer_id, _now(), _now()),
    )
    row = conn.execute(
        "SELECT customer_id FROM conversation_sessions WHERE session_id=?", (session_id,)
    ).fetchone()
    return row["customer_id"] == customer_id


def history(conn, session_id: str, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT role, content FROM conversation_messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def add_messages(conn, session_id: str, pairs: list[tuple[str, str]]) -> None:
    with tx(conn):
        for role, content in pairs:
            conn.execute(
                "INSERT INTO conversation_messages(session_id, role, content, created_at) VALUES (?,?,?,?)",
                (session_id, role, content, _now()),
            )


def set_pending(conn, session_id: str, proposal: dict | None) -> None:
    conn.execute(
        "UPDATE conversation_sessions SET pending_proposal_json=?, updated_at=? WHERE session_id=?",
        (json.dumps(proposal) if proposal else None, _now(), session_id),
    )


def take_pending(conn, session_id: str) -> dict | None:
    """Atomically read and clear the pending proposal (so a proposal can be used only once)."""
    with tx(conn):
        row = conn.execute(
            "SELECT pending_proposal_json FROM conversation_sessions WHERE session_id=?", (session_id,)
        ).fetchone()
        if not row or not row["pending_proposal_json"]:
            return None
        conn.execute(
            "UPDATE conversation_sessions SET pending_proposal_json=NULL WHERE session_id=?", (session_id,)
        )
        return json.loads(row["pending_proposal_json"])
