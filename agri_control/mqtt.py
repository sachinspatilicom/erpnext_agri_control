"""Broker settings, shared cache keys and one-shot publishing from web requests.

Web workers do NOT keep a persistent MQTT connection: each command opens a short
connection, publishes and disconnects (paho.mqtt.publish.single). The long-lived
subscriber lives in agri_control.listener and runs as its own supervisor process.
"""
import frappe
from frappe.utils import cint, now_datetime

from agri_control.payloads import dumps

CACHE_STATUS = "agri_control:last_status"
CACHE_HEARTBEAT = "agri_control:last_heartbeat"


def cache():
    c = frappe.cache
    # frappe.cache is a function in v14 and an object (also callable) in v15+
    return c if hasattr(c, "set_value") else c()


def get_conn_params():
    s = frappe.get_single("Agri MQTT Settings")
    password = s.get_password("password", raise_exception=False) if s.username else None
    return {
        "host": (s.broker_host or "localhost").strip(),
        "port": cint(s.broker_port) or 1883,
        "auth": {"username": s.username, "password": password} if s.username else None,
        "tls": cint(s.use_tls),
        "prefix": (s.topic_prefix or "agri").strip().strip("/"),
        "heartbeat_timeout": cint(s.heartbeat_timeout_sec) or 90,
        "retention_days": cint(s.log_retention_days),
    }


def topic(prefix, suffix):
    return f"{prefix}/{suffix}"


def mqtt_publish(suffix, payload, qos=1, retain=False):
    from paho.mqtt import publish

    p = get_conn_params()
    if isinstance(payload, (dict, list)):
        payload = dumps(payload)
    try:
        publish.single(
            topic(p["prefix"], suffix),
            payload=payload,
            qos=qos,
            retain=retain,
            hostname=p["host"],
            port=p["port"],
            auth=p["auth"],
            tls={} if p["tls"] else None,
            client_id=f"{p['prefix']}-web-{frappe.generate_hash(length=8)}",
            keepalive=15,
        )
    except Exception as e:
        frappe.log_error(title="Agri MQTT publish failed", message=frappe.get_traceback())
        frappe.throw(f"Could not reach MQTT broker at {p['host']}:{p['port']} ({e})",
                     title="MQTT error")
    return topic(p["prefix"], suffix)


def add_log(message, source="System", level="Info", topic_name=None, user=None, publish=True):
    """Insert an Agri Event Log row and push it to open dashboards after commit."""
    ts = now_datetime()
    frappe.get_doc({
        "doctype": "Agri Event Log",
        "event_time": ts,
        "message": message,
        "source": source,
        "level": level,
        "topic": topic_name,
        "user": user,
    }).insert(ignore_permissions=True)
    row = {"event_time": str(ts), "message": message, "source": source, "level": level}
    if publish:
        frappe.publish_realtime("agri_log", row, after_commit=True)
    return row
