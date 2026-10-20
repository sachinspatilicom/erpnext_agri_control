"""Long-running MQTT subscriber.

Run with:   bench --site erp.nutrigreenbite.com agri-mqtt
In production it is kept alive by supervisor (see deploy/supervisor-agri-mqtt.conf).
Exactly ONE listener should run per site.

Subscribes to:
  <prefix>/status     -> cached + pushed live to dashboards; relay ON/OFF changes logged
  <prefix>/log        -> stored in Agri Event Log + pushed live
  <prefix>/heartbeat  -> cached + pushed live (drives Online/Offline indicator)
"""
import sys

import frappe
import paho.mqtt.client as mqtt
from frappe.utils import now_datetime

from agri_control.mqtt import (CACHE_HEARTBEAT, CACHE_STATUS, add_log, cache,
                               get_conn_params, topic)
from agri_control.payloads import detect_level, normalize_status, parse_json


def _say(msg):
    print(f"[agri-mqtt {now_datetime():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def _ensure_db():
    """MariaDB drops idle connections (wait_timeout); reconnect transparently."""
    try:
        frappe.db.sql("select 1")
    except Exception:
        try:
            frappe.db.close()
        except Exception:
            pass
        try:
            frappe.db.connect()
        except Exception:
            frappe.connect()
        _say("database reconnected")


def _relay_names():
    return {str(r.relay_index): r.relay_name
            for r in frappe.get_all("Relay Config", fields=["relay_index", "relay_name"])}


# ---------------------------------------------------------------- handlers
def handle_status(payload):
    status = normalize_status(payload)
    status["received_at"] = str(now_datetime())

    previous = cache().get_value(CACHE_STATUS) or {}
    old = previous.get("relays") or {}
    # Readings (temp/humidity) may come in some status messages but not others: keep the last ones.
    status["extra"] = {**(previous.get("extra") or {}), **status["extra"]}
    cache().set_value(CACHE_STATUS, status)

    changed = [k for k, v in status["relays"].items() if k in old and old[k] != v]
    if changed:
        names = _relay_names()
        for idx in changed:
            state = "ON" if status["relays"][idx] else "OFF"
            add_log(f"{names.get(idx, 'Relay ' + idx)} switched {state}",
                    source="Device", topic_name="status")
    frappe.publish_realtime("agri_status", status, after_commit=True)


def handle_log(payload, topic_name):
    add_log(payload, source="Device", level=detect_level(payload), topic_name=topic_name)


def handle_heartbeat(payload):
    hb = {"ts": str(now_datetime()), "data": parse_json(payload) or payload}
    cache().set_value(CACHE_HEARTBEAT, hb)
    frappe.publish_realtime("agri_heartbeat", hb)


# ---------------------------------------------------------------- paho callbacks
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code.is_failure:
        _say(f"connect refused: {reason_code}")
        return
    p = userdata["prefix"]
    client.subscribe([(topic(p, "status"), 1), (topic(p, "log"), 1), (topic(p, "heartbeat"), 0)])
    _say(f"connected, subscribed to {p}/status, {p}/log, {p}/heartbeat")
    try:
        _ensure_db()
        add_log("MQTT listener connected to broker", source="System")
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()


def on_disconnect(client, userdata, flags, reason_code, properties=None):
    _say(f"disconnected ({reason_code}); paho will reconnect automatically")


def on_message(client, userdata, msg):
    prefix = userdata["prefix"]
    sub = msg.topic[len(prefix) + 1:] if msg.topic.startswith(prefix + "/") else msg.topic
    payload = msg.payload.decode("utf-8", "replace")
    try:
        _ensure_db()
        if sub == "status":
            handle_status(payload)
        elif sub == "log":
            handle_log(payload, msg.topic)
        elif sub == "heartbeat":
            handle_heartbeat(payload)
        frappe.db.commit()  # also fires publish_realtime(after_commit=True)
    except Exception:
        frappe.db.rollback()
        _say(f"error handling {msg.topic}: {sys.exc_info()[1]}")
        try:
            frappe.log_error(title=f"Agri MQTT: failed on {msg.topic}",
                             message=f"Payload:\n{payload}\n\n{frappe.get_traceback()}")
            frappe.db.commit()
        except Exception:
            pass


# ---------------------------------------------------------------- entry point
def run():
    p = get_conn_params()
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"{p['prefix']}-listener-{frappe.generate_hash(length=6)}",
        clean_session=True,
    )
    client.user_data_set({"prefix": p["prefix"]})
    if p["auth"]:
        client.username_pw_set(p["auth"]["username"], p["auth"]["password"])
    if p["tls"]:
        client.tls_set()
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    _say(f"starting for site {frappe.local.site} -> {p['host']}:{p['port']}")
    client.connect_async(p["host"], p["port"], keepalive=30)
    client.loop_forever(retry_first_connection=True)
