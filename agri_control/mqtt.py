"""Broker settings, shared cache keys and one-shot publishing from web requests.

Web workers don't hold a persistent MQTT connection: each command opens a short TLS
connection, publishes (QoS 1) and disconnects. The long-lived subscriber is
agri_control.listener, run by supervisor.
"""
import frappe
from frappe.utils import cint, now_datetime

from agri_control.payloads import dumps

CACHE_STATUS = "agri_control:status"         # last parsed agri/status
CACHE_HEARTBEAT = "agri_control:heartbeat"   # "online" | "offline"
CACHE_BROKER = "agri_control:broker"         # listener -> broker state, expires if listener dies
BROKER_TTL = 45


def cache():
    c = frappe.cache
    return c if hasattr(c, "set_value") else c()  # v14 function / v15 object


def get_conn_params():
    s = frappe.get_single("Agri MQTT Settings")
    if not s.broker_host:
        frappe.throw("Set the broker host in Agri MQTT Settings first", title="MQTT not configured")
    password = s.get_password("password", raise_exception=False) if s.username else None
    return {
        "host": s.broker_host.strip(),
        "port": cint(s.broker_port) or 8883,
        "auth": {"username": s.username, "password": password} if s.username else None,
        "tls": cint(s.use_tls),
        "prefix": (s.topic_prefix or "agri").strip().strip("/"),
    }


def mqtt_publish(suffix, payload, qos=1, retain=False):
    from paho.mqtt import publish

    p = get_conn_params()
    topic = f"{p['prefix']}/{suffix}"
    if isinstance(payload, (dict, list)):
        payload = dumps(payload)
    try:
        publish.single(
            topic, payload=payload, qos=qos, retain=retain,
            hostname=p["host"], port=p["port"], auth=p["auth"],
            tls={} if p["tls"] else None,
            client_id=f"agri-erp-{frappe.generate_hash(length=8)}",
            keepalive=15,
        )
    except Exception as e:
        frappe.log_error(title="Agri MQTT publish failed", message=frappe.get_traceback())
        frappe.throw(f"Could not reach the MQTT broker ({e})", title="Broker offline?")
    return topic


def add_log(message, source="Device", user=None):
    """Insert an Agri Event Log row and push it to open dashboards after commit."""
    ts = now_datetime()
    frappe.get_doc({"doctype": "Agri Event Log", "event_time": ts, "message": message,
                    "source": source, "user": user}).insert(ignore_permissions=True)
    row = {"event_time": str(ts), "message": message, "source": source, "user": user}
    frappe.publish_realtime("agri_log", row, after_commit=True)
    return row
