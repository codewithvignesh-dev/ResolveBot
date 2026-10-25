"""The five tools. Customer id always comes from the request context, never from the LLM."""
import json
import uuid
from datetime import date, datetime, timezone

import business_rules as br
import policy_search
from config import get_settings
from database import tx

ORDER_STATUSES = ("processing", "shipped", "delivered", "cancelled")

TOOL_SPECS = [
    {"name": "get_orders",
     "description": "Read-only. Get the logged-in customer's orders with items, shipment/ETA, delivery date, days since "
                    "delivery, and each item's warranty end date and whether it is active. Call with no arguments to "
                    "list all orders (use this to find which order contains an item). Optionally filter by order_id "
                    "or status.",
     "parameters": {"type": "object", "properties": {
         "order_id": {"type": "string", "description": "e.g. SS-10458"},
         "status": {"type": "string", "enum": list(ORDER_STATUSES)}}}},
    {"name": "search_policy",
     "description": "Read-only. Search ShopSphere policy documents. Returns the best matching paragraphs with doc_id "
                    "and section. Use for any policy/FAQ question; never answer policy facts from memory.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "check_return_eligibility",
     "description": "Read-only. Check if items of an order can be returned. Returns eligible or an error code.",
     "parameters": {"type": "object", "properties": {
         "order_id": {"type": "string"}, "item_ids": {"type": "array", "items": {"type": "string"}},
         "reason": {"type": "string", "enum": ["changed_mind", "defective"]}},
         "required": ["order_id", "item_ids", "reason"]}},
    {"name": "create_return_request",
     "description": "Propose creating a return request. Call ONLY when the customer explicitly asks to return "
                    "(not for questions like 'can I return?'). Nothing is saved until the customer confirms in their "
                    "next message; the system handles that.",
     "parameters": {"type": "object", "properties": {
         "order_id": {"type": "string"}, "item_ids": {"type": "array", "items": {"type": "string"}},
         "reason": {"type": "string", "enum": ["changed_mind", "defective"]}},
         "required": ["order_id", "item_ids", "reason"]}},
    {"name": "create_support_ticket",
     "description": "Propose a warranty or cancellation ticket. Call ONLY when the customer explicitly asks for it. "
                    "Nothing is saved until the customer confirms in their next message.",
     "parameters": {"type": "object", "properties": {
         "order_id": {"type": "string"}, "ticket_type": {"type": "string", "enum": ["warranty", "cancellation"]},
         "summary": {"type": "string", "description": "One-sentence description of the issue/request"}},
         "required": ["order_id", "ticket_type", "summary"]}},
]
WRITE_TOOLS = ("create_return_request", "create_support_ticket")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_orders(conn, customer_id: str, today: date, order_id=None, status=None) -> dict:
    params = br.load_params(conn)
    if order_id:
        order = br.get_owned_order(conn, customer_id, order_id)
        if not order:
            return br.order_not_found()
        return {"orders": [br.order_view(conn, order, params, today)]}
    if status and status not in ORDER_STATUSES:
        return br.err("INVALID_STATUS", f"status must be one of {', '.join(ORDER_STATUSES)}")
    sql, args = "SELECT * FROM orders WHERE customer_id=?", [customer_id]
    if status:
        sql, args = sql + " AND status=?", args + [status]
    rows = conn.execute(sql + " ORDER BY order_date DESC", args).fetchall()
    return {"orders": [br.order_view(conn, dict(r), params, today) for r in rows]}


def search_policy(query: str, today: date) -> dict:
    s = get_settings()
    results = policy_search.search(s.policies_path, s.manifest_path, str(query), today)
    if not results:
        return {"results": [], "note": "No applicable policy paragraph found."}
    return {"results": results}


def check_return_eligibility(conn, customer_id: str, today: date, order_id, item_ids, reason) -> dict:
    return br.check_return(conn, customer_id, order_id, item_ids, reason, today)


def create_return_request(conn, customer_id: str, today: date, order_id, item_ids, reason) -> dict:
    """Actual write. Only the confirmation path in agent.py calls this; it re-checks first."""
    with tx(conn):
        check = br.check_return(conn, customer_id, order_id, item_ids, reason, today)
        if "error_code" in check:
            return check
        rid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO return_requests(request_id, order_id, customer_id, item_ids, reason, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (rid, check["order_id"], customer_id, json.dumps(check["item_ids"]), reason, "requested", _now()),
        )
    return {"request_id": rid, "status": "requested", "order_id": check["order_id"], "item_ids": check["item_ids"]}


def check_ticket(conn, customer_id: str, today: date, order_id, ticket_type) -> dict:
    if ticket_type == "warranty":
        return br.check_warranty_ticket(conn, customer_id, order_id, today)
    if ticket_type == "cancellation":
        return br.check_cancellation(conn, customer_id, order_id)
    return br.err("INVALID_TICKET_TYPE", "ticket_type must be 'warranty' or 'cancellation'")


def create_support_ticket(conn, customer_id: str, today: date, order_id, ticket_type, summary) -> dict:
    """Actual write. Only the confirmation path in agent.py calls this; it re-checks first."""
    with tx(conn):
        check = check_ticket(conn, customer_id, today, order_id, ticket_type)
        if "error_code" in check:
            return check
        tid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO support_tickets(ticket_id, order_id, customer_id, ticket_type, summary, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (tid, check["order_id"], customer_id, ticket_type, str(summary)[:500], "open", _now()),
        )
    return {"ticket_id": tid, "status": "open", "order_id": check["order_id"], "ticket_type": ticket_type}
