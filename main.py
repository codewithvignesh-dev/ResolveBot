"""HTTP layer only: POST /chat. Maps errors to 400/401/403; everything else is a 200 reply."""
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import agent
import sessions
from database import connect

app = FastAPI(title="ResolveBot")


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


@app.post("/chat")
async def chat(request: Request):
    try:
        body = json.loads(await request.body())
    except ValueError:
        return _err(400, "Body must be valid JSON")
    sid = body.get("session_id") if isinstance(body, dict) else None
    msg = body.get("message") if isinstance(body, dict) else None
    if not isinstance(sid, str) or not sid.strip() or not isinstance(msg, str) or not msg.strip():
        return _err(400, "session_id and message are required non-empty strings")
    customer_id = (request.headers.get("X-Customer-Id") or "").strip()
    conn = connect()
    try:
        if not customer_id or not conn.execute(
                "SELECT 1 FROM customers WHERE customer_id=?", (customer_id,)).fetchone():
            return _err(401, "Missing or unknown X-Customer-Id")
        if not sessions.bind(conn, sid, customer_id):
            return _err(403, "This session belongs to another customer")
        return agent.chat(conn, customer_id, sid, msg)
    finally:
        conn.close()
