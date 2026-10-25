"""All business decisions live here (pure Python, numbers read from policy_parameters)."""
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

REASONS = ("changed_mind", "defective")
ORDER_NOT_FOUND_MSG = "I couldn't find that order on your account."


def err(code: str, message: str) -> dict:
    return {"error_code": code, "message": message}


def parse_date(value) -> date | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value)[:19]).date()


def fmt_date(d: date | None) -> str | None:
    return f"{d.day} {d.strftime('%B %Y')}" if d else None


def load_params(conn) -> dict:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM policy_parameters")}


def param_int(params: dict, key: str) -> int:
    return int(params[key])


def get_owned_order(conn, customer_id: str, order_id) -> dict | None:
    """Single ownership guard: missing and foreign orders are indistinguishable."""
    if not isinstance(order_id, str) or not order_id.strip():
        return None
    row = conn.execute(
        "SELECT * FROM orders WHERE order_id=? AND customer_id=?",
        (order_id.strip().upper(), customer_id),
    ).fetchone()
    return dict(row) if row else None


def order_not_found() -> dict:
    return err("ORDER_NOT_FOUND", ORDER_NOT_FOUND_MSG)


def _shipment(conn, order_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM shipments WHERE order_id=?", (order_id,)).fetchone()
    return dict(row) if row else None


def _items(conn, order_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT oi.*, p.name, p.returnable, p.warranty_class FROM order_items oi "
        "JOIN products p ON p.product_id = oi.product_id WHERE oi.order_id=? ORDER BY oi.item_id",
        (order_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delivered_date(order: dict, shipment: dict | None) -> date | None:
    if order["status"] != "delivered" or not shipment:
        return None
    return parse_date(shipment.get("delivered_at"))


def warranty_end(delivered: date | None, warranty_class: str, params: dict) -> date | None:
    key = {"standard": "standard_warranty_months", "extended": "extended_warranty_months"}.get(warranty_class)
    if not key or not delivered:
        return None
    return delivered + relativedelta(months=param_int(params, key))


def order_view(conn, order: dict, params: dict, today: date) -> dict:
    ship = _shipment(conn, order["order_id"])
    delivered = delivered_date(order, ship)
    items = []
    for it in _items(conn, order["order_id"]):
        end = warranty_end(delivered, it["warranty_class"], params)
        items.append({
            "item_id": it["item_id"], "product_name": it["name"], "qty": it["qty"],
            "unit_price": it["unit_price"], "opened": bool(it["opened"]),
            "defect_reported": bool(it["defect_reported"]), "returnable": it["returnable"],
            "warranty_class": it["warranty_class"],
            "warranty_end_date": fmt_date(end),
            "warranty_active": (today <= end) if end else (False if delivered else None),
        })
    view = {
        "order_id": order["order_id"], "order_date": fmt_date(parse_date(order["order_date"])),
        "status": order["status"], "total": order["total"], "items": items,
        "delivered_date": fmt_date(delivered),
        "days_since_delivery": (today - delivered).days if delivered else None,
    }
    if ship:
        view["shipment"] = {
            "carrier": ship["carrier"], "tracking_no": ship["tracking_no"], "status": ship["status"],
            "shipped_at": fmt_date(parse_date(ship["shipped_at"])),
            "eta": fmt_date(parse_date(ship["eta"])),
            "original_eta": fmt_date(parse_date(ship["original_eta"])),
        }
    return view


def check_return(conn, customer_id, order_id, item_ids, reason, today: date) -> dict:
    order = get_owned_order(conn, customer_id, order_id)
    if not order:
        return order_not_found()
    if reason not in REASONS:
        return err("INVALID_REASON", "Reason must be 'changed_mind' or 'defective'")
    by_id = {i["item_id"]: i for i in _items(conn, order["order_id"])}
    if not isinstance(item_ids, list) or not item_ids:
        return err("INVALID_ITEM", "At least one item_id from the order is required")
    chosen = []
    for iid in item_ids:
        if not isinstance(iid, str) or iid.strip().upper() not in by_id:
            return err("INVALID_ITEM", f"Item {iid} is not in this order")
        if iid.strip().upper() not in [c["item_id"] for c in chosen]:
            chosen.append(by_id[iid.strip().upper()])
    ship = _shipment(conn, order["order_id"])
    delivered = delivered_date(order, ship)
    if not delivered:
        return err("NOT_DELIVERED", "This order has not been delivered yet")
    for it in chosen:
        if it["returnable"] == "no":
            return err("NON_RETURNABLE", f"{it['name']} cannot be returned")
    params = load_params(conn)
    window = param_int(params, "return_window_days")
    days = (today - delivered).days
    if days > window:
        return err("RETURN_WINDOW_EXPIRED",
                   f"Delivered {fmt_date(delivered)} ({days} days ago); the return window is {window} days")
    if reason == "changed_mind":
        for it in chosen:
            if it["opened"] and it["returnable"] == "unopened_only":
                return err("OPENED_NOT_RETURNABLE", f"{it['name']} is opened and can only be returned unopened")
    return {
        "eligible": True, "order_id": order["order_id"], "reason": reason,
        "item_ids": [c["item_id"] for c in chosen], "item_names": [c["name"] for c in chosen],
        "days_since_delivery": days, "return_window_days": window,
    }


def check_warranty_ticket(conn, customer_id, order_id, today: date) -> dict:
    order = get_owned_order(conn, customer_id, order_id)
    if not order:
        return order_not_found()
    delivered = delivered_date(order, _shipment(conn, order["order_id"]))
    if not delivered:
        return err("NOT_DELIVERED", "This order has not been delivered yet")
    params = load_params(conn)
    items = _items(conn, order["order_id"])
    covered = []
    for it in items:
        end = warranty_end(delivered, it["warranty_class"], params)
        if end and today <= end:
            covered.append(it["name"])
    if covered:
        return {"eligible": True, "order_id": order["order_id"], "covered_items": covered}
    if all(i["warranty_class"] == "none" for i in items):
        return err("NO_WARRANTY", "None of the items in this order have a warranty")
    return err("WARRANTY_EXPIRED", "The warranty has expired for all items in this order")


def check_cancellation(conn, customer_id, order_id) -> dict:
    order = get_owned_order(conn, customer_id, order_id)
    if not order:
        return order_not_found()
    if order["status"] == "processing":
        return {"eligible": True, "order_id": order["order_id"]}
    if order["status"] in ("shipped", "delivered"):
        return err("ORDER_ALREADY_SHIPPED", "This order has already shipped and can no longer be cancelled")
    return err("ALREADY_CANCELLED", "This order is already cancelled")
