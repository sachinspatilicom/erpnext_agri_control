import frappe
from frappe.utils import cint, getdate, now_datetime

from agri_control.mqtt import (CACHE_HEARTBEAT, CACHE_STATUS, add_log, cache,
                               get_conn_params, mqtt_publish)

ROLES = ("System Manager", "Agri Operator")
ACTIONS = ("ON", "OFF")


def _check():
    frappe.only_for(ROLES)


@frappe.whitelist()
def get_dashboard_data():
    _check()
    p = get_conn_params()
    return {
        "relays": frappe.get_all(
            "Relay Config",
            fields=["name", "relay_name", "relay_index", "location", "enabled"],
            order_by="relay_index asc",
        ),
        "status": cache().get_value(CACHE_STATUS),
        "heartbeat": cache().get_value(CACHE_HEARTBEAT),
        "heartbeat_timeout": p["heartbeat_timeout"],
        "server_time": str(now_datetime()),
    }


@frappe.whitelist(methods=["POST"])
def send_command(relay, action):
    _check()
    action = (action or "").strip().upper()
    if action not in ACTIONS:
        frappe.throw(f"Action must be one of {', '.join(ACTIONS)}")
    rc = frappe.get_doc("Relay Config", relay)
    if not rc.enabled:
        frappe.throw(f"{rc.relay_name} is disabled in Relay Config")
    mqtt_publish(f"relay/cmd/{rc.relay_index}", action, qos=1)
    add_log(f"{action} sent to {rc.relay_name} (relay {rc.relay_index})",
            source="User", user=frappe.session.user)
    return {"ok": True}


def _push(doc):
    mqtt_publish("schedule/set", doc.get_payload(), qos=1)
    doc.db_set("last_sent", now_datetime(), update_modified=False)


@frappe.whitelist(methods=["POST"])
def push_schedule(name):
    _check()
    doc = frappe.get_doc("Relay Schedule", name)
    doc.check_permission("read")
    _push(doc)
    add_log(f"Schedule {doc.name} sent for {doc.relay}", source="User", user=frappe.session.user)
    return {"ok": True}


@frappe.whitelist(methods=["POST"])
def push_all_schedules():
    """Re-sends every schedule (enabled and disabled) so the controller matches ERPNext."""
    _check()
    names = frappe.get_all("Relay Schedule", pluck="name")
    for name in names:
        _push(frappe.get_doc("Relay Schedule", name))
    add_log(f"All schedules sent to controller ({len(names)})", source="User",
            user=frappe.session.user)
    return {"count": len(names)}


@frappe.whitelist()
def get_log(limit=50, offset=0, search=None, date=None):
    _check()
    limit = min(max(cint(limit) or 50, 1), 500)
    offset = max(cint(offset), 0)
    filters = {}
    if date:
        d = getdate(date)
        filters["event_time"] = ["between", [f"{d} 00:00:00", f"{d} 23:59:59.999999"]]
    if search:
        filters["message"] = ["like", f"%{search.strip()}%"]
    rows = frappe.get_all(
        "Agri Event Log",
        filters=filters,
        fields=["name", "event_time", "level", "source", "message", "user"],
        order_by="event_time desc",
        limit_start=offset,
        limit_page_length=limit,
    )
    return {"rows": rows, "total": frappe.db.count("Agri Event Log", filters)}


@frappe.whitelist(methods=["POST"])
def test_connection():
    frappe.only_for("System Manager")
    t = mqtt_publish("ping", f"ping from ERPNext by {frappe.session.user}", qos=0)
    return f"Connected and published to <b>{t}</b>."
