"""Replaces RelayApiController.cs + AgriHub.cs. All methods require System Manager or Agri Operator."""
import json

import frappe
from frappe.utils import cint, getdate, now_datetime

from agri_control.mqtt import (CACHE_BROKER, CACHE_HEARTBEAT, CACHE_STATUS, add_log, cache,
                               mqtt_publish)
from agri_control.payloads import NUM_RELAYS, label, normalize_schedule, valid_command

ROLES = ("System Manager", "Agri Operator")


def _check():
    frappe.only_for(ROLES)


def _relay(relay_index):
    idx = cint(relay_index)
    if not 0 <= idx < NUM_RELAYS:
        frappe.throw(f"Relay index must be 0 to {NUM_RELAYS - 1}")
    return frappe.get_doc("Relay Config", label(idx))


def _relay_row(doc):
    return {"index": doc.relay_index, "label": doc.name, "name": doc.relay_name,
            "location": doc.location or "", "type": doc.relay_type,
            "schedule": doc.get_schedule(), "summary": doc.get_summary(),
            "last_sent": doc.last_sent}


def _loads(value):
    return json.loads(value) if isinstance(value, str) else value


# ---------------------------------------------------------------- dashboard
@frappe.whitelist()
def get_dashboard_data():
    _check()
    s = frappe.get_single("Agri MQTT Settings")
    docs = [frappe.get_doc("Relay Config", n) for n in
            frappe.get_all("Relay Config", order_by="relay_index asc", pluck="name")]
    return {
        "farm_name": s.farm_name or "Agri Controller",
        "farm_location": s.farm_location or "",
        "relays": [_relay_row(d) for d in docs],
        "status": cache().get_value(CACHE_STATUS),
        "heartbeat": cache().get_value(CACHE_HEARTBEAT) or "offline",
        "broker": cache().get_value(CACHE_BROKER),   # None => listener not running
        "configured": bool(s.broker_host),
        "is_manager": "System Manager" in frappe.get_roles(),
    }


@frappe.whitelist()
def get_live_state():
    """Polled every 30 s by the dashboard to detect a stopped listener."""
    _check()
    return {"status": cache().get_value(CACHE_STATUS),
            "heartbeat": cache().get_value(CACHE_HEARTBEAT) or "offline",
            "broker": cache().get_value(CACHE_BROKER)}


# ---------------------------------------------------------------- commands
@frappe.whitelist(methods=["POST"])
def send_command(relay_index, action):
    """ON | OFF | AUTO -> <prefix>/relay/cmd/<index>   (same as AgriHub.SendCommand)."""
    _check()
    action = (action or "").strip().upper()
    if not valid_command(relay_index, action):
        frappe.throw("Relay must be 0-13 and action ON, OFF or AUTO")
    doc = _relay(relay_index)
    mqtt_publish(f"relay/cmd/{cint(relay_index)}", action, qos=1)
    add_log(f"{action} sent to {doc.name} {doc.relay_name}", source="User", user=frappe.session.user)
    return {"success": True, "id": cint(relay_index), "action": action}


# ---------------------------------------------------------------- names / farm
@frappe.whitelist(methods=["POST"])
def update_relay(relay_index, relay_name=None, location=None):
    _check()
    doc = _relay(relay_index)
    if relay_name is not None:
        doc.relay_name = relay_name.strip() or doc.relay_name
    if location is not None:
        doc.location = location.strip()[:50]
    doc.save(ignore_permissions=True)
    return _relay_row(doc)


@frappe.whitelist(methods=["POST"])
def save_farm_info(farm_name=None, farm_location=None):
    _check()
    s = frappe.get_single("Agri MQTT Settings")
    s.farm_name = (farm_name or "").strip()[:60] or "Agri Controller"
    s.farm_location = (farm_location or "").strip()[:100]
    s.flags.ignore_mandatory = True
    s.save(ignore_permissions=True)
    return {"farm_name": s.farm_name, "farm_location": s.farm_location}


# ---------------------------------------------------------------- schedules
def _push(doc):
    payload = doc.get_payload()
    if payload is None:
        return False
    mqtt_publish("schedule/set", payload, qos=1)
    doc.db_set("last_sent", now_datetime(), update_modified=False)
    return True


@frappe.whitelist(methods=["POST"])
def save_schedule(relay_index, schedule):
    """Save in ERPNext, then send to the device (same as saveAndSendSchedule in the old page).
    Saving succeeds even if the broker is unreachable."""
    _check()
    doc = _relay(relay_index)
    doc.set_schedule(_loads(schedule))
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    sent, error = False, None
    try:
        sent = _push(doc)
        if sent:
            add_log(f"Schedule sent to {doc.name} {doc.relay_name}: {doc.get_summary()}",
                    source="User", user=frappe.session.user)
    except Exception as e:
        frappe.clear_messages()
        error = str(e)
    return {"relay": _relay_row(doc), "sent": sent, "error": error}


@frappe.whitelist(methods=["POST"])
def push_schedule(relay_index):
    _check()
    doc = _relay(relay_index)
    if not _push(doc):
        frappe.throw("R1 Master has no schedule")
    add_log(f"Schedule sent to {doc.name} {doc.relay_name}: {doc.get_summary()}",
            source="User", user=frappe.session.user)
    return {"success": True}


@frappe.whitelist(methods=["POST"])
def push_all_schedules():
    """Re-send R2..R14 so the device matches ERPNext exactly."""
    _check()
    count = 0
    for name in frappe.get_all("Relay Config", order_by="relay_index asc", pluck="name"):
        if _push(frappe.get_doc("Relay Config", name)):
            count += 1
    add_log(f"All schedules sent to device ({count} relays)", source="User", user=frappe.session.user)
    return {"count": count}


# ---------------------------------------------------------------- event log
@frappe.whitelist()
def get_log(limit=50, offset=0, search=None, date=None):
    """Same contract as GET /api/relay/log: items, total, limit, offset, hasMore."""
    _check()
    limit = min(max(cint(limit) or 50, 1), 500)
    offset = max(cint(offset), 0)
    filters = {}
    if date:
        d = getdate(date)
        filters["event_time"] = ["between", [f"{d} 00:00:00", f"{d} 23:59:59.999999"]]
    if search and search.strip():
        filters["message"] = ["like", f"%{search.strip()}%"]
    items = frappe.get_all("Agri Event Log", filters=filters,
                           fields=["event_time", "message", "source", "user"],
                           order_by="event_time desc, creation desc",
                           limit_start=offset, limit_page_length=limit)
    total = frappe.db.count("Agri Event Log", filters)
    return {"items": items, "total": total, "limit": limit, "offset": offset,
            "hasMore": offset + len(items) < total}


@frappe.whitelist(methods=["POST"])
def clear_log():
    frappe.only_for("System Manager")
    frappe.db.delete("Agri Event Log")
    return {"success": True}


# ---------------------------------------------------------------- migration from old web app
@frappe.whitelist(methods=["POST"])
def import_old_app(data):
    """data = JSON copied from the old app's browser localStorage:
    {"rn": [14 names], "rl": [14 locations], "sd": [14 schedules], "agri_name": "...", "agri_loc": "..."}
    Only saves to ERPNext; the device already has these schedules."""
    _check()
    data = _loads(data) or {}

    def arr(key):
        v = data.get(key)
        v = _loads(v) if isinstance(v, str) else v
        return v if isinstance(v, list) else []

    names, locs, scheds = arr("rn"), arr("rl"), arr("sd")
    updated = 0
    for idx in range(NUM_RELAYS):
        doc = _relay(idx)
        if idx < len(names) and names[idx]:
            doc.relay_name = str(names[idx])
        if idx < len(locs) and locs[idx] is not None:
            doc.location = str(locs[idx])
        if idx < len(scheds) and isinstance(scheds[idx], dict):
            doc.set_schedule(normalize_schedule(idx, scheds[idx]))
        doc.save(ignore_permissions=True)
        updated += 1
    if data.get("agri_name") or data.get("agri_loc"):
        save_farm_info(data.get("agri_name"), data.get("agri_loc"))
    return {"updated": updated}


@frappe.whitelist(methods=["POST"])
def test_connection():
    frappe.only_for("System Manager")
    t = mqtt_publish("ping", f"ping from ERPNext by {frappe.session.user}", qos=0)
    return f"Connected and published to <b>{t}</b>. The ESP32 ignores this topic."
