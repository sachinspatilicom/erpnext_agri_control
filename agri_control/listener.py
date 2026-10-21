"""Long-running MQTT subscriber — replaces MqttService.cs.

Run:   bench --site erp.nutrigreenbite.com agri-mqtt
Production: supervisor (deploy/supervisor-agri-mqtt.conf). Run exactly ONE per site.

<p>/status     retained JSON every 5 s -> cached + pushed live (agri_status)
<p>/heartbeat  retained online/offline -> cached + pushed live (agri_heartbeat)
<p>/log        text                   -> Agri Event Log + pushed live (agri_log)

Single-threaded on purpose (frappe.local is per thread): a manual loop drives paho,
handles reconnects, and refreshes a "broker" cache key that expires if this process dies,
so the dashboard can show Broker: Connected / Disconnected / Listener not running.
"""
import time

import frappe
import paho.mqtt.client as mqtt
from frappe.utils import now_datetime

from agri_control.mqtt import (BROKER_TTL, CACHE_BROKER, CACHE_HEARTBEAT, CACHE_STATUS, add_log,
                               cache, get_conn_params)
from agri_control.payloads import parse_heartbeat, parse_status

state = {"connected": False, "error": None, "host": None}


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


def broker_info():
    return {"connected": state["connected"], "error": None if state["connected"] else state["error"],
            "host": state["host"], "ts": str(now_datetime())}


def set_broker(connected, push=True, error=None):
    state["connected"] = connected
    if error:
        state["error"] = error
    info = broker_info()
    cache().set_value(CACHE_BROKER, info, expires_in_sec=BROKER_TTL)
    if push:
        frappe.publish_realtime("agri_broker", info)


# ---------------------------------------------------------------- handlers
def handle_status(payload):
    status = parse_status(payload)
    if status is None:
        _say(f"ignored status payload: {payload[:120]}")
        return
    status["received_at"] = str(now_datetime())
    cache().set_value(CACHE_STATUS, status)
    frappe.publish_realtime("agri_status", status)


def handle_heartbeat(payload):
    hb = parse_heartbeat(payload)
    previous = cache().get_value(CACHE_HEARTBEAT)
    cache().set_value(CACHE_HEARTBEAT, hb)
    frappe.publish_realtime("agri_heartbeat", hb)
    if previous and previous != hb:
        add_log(f"Device went {hb}", source="System")


def handle_log(payload):
    add_log(payload.strip()[:500], source="Device")


# ---------------------------------------------------------------- paho callbacks
def on_connect(client, userdata, flags, reason_code, properties=None):
    try:
        if reason_code.is_failure:
            _say(f"broker refused connection: {reason_code}")
            set_broker(False, error=f"Broker refused login: {reason_code} (check username / password)")
            return
        p = userdata["prefix"]
        client.subscribe([(f"{p}/status", 0), (f"{p}/heartbeat", 1), (f"{p}/log", 1)])
        _say(f"connected, subscribed to {p}/status, {p}/heartbeat, {p}/log")
        _ensure_db()
        state["error"] = None
        set_broker(True)
    except Exception as e:
        _say(f"on_connect error: {e}")


def on_disconnect(client, userdata, flags, reason_code, properties=None):
    _say(f"disconnected ({reason_code})")
    try:
        set_broker(False)
    except Exception:
        pass


def on_message(client, userdata, msg):
    prefix = userdata["prefix"]
    sub = msg.topic[len(prefix) + 1:] if msg.topic.startswith(prefix + "/") else msg.topic
    payload = msg.payload.decode("utf-8", "replace")
    try:
        _ensure_db()
        if sub == "status":
            handle_status(payload)
        elif sub == "heartbeat":
            handle_heartbeat(payload)
        elif sub == "log":
            handle_log(payload)
        frappe.db.commit()  # also fires publish_realtime(after_commit=True)
    except Exception as e:
        frappe.db.rollback()
        _say(f"error handling {msg.topic}: {e}")
        try:
            frappe.log_error(title=f"Agri MQTT: failed on {msg.topic}",
                             message=f"Payload:\n{payload}\n\n{frappe.get_traceback()}")
            frappe.db.commit()
        except Exception:
            pass


# ---------------------------------------------------------------- entry point
def build_client(p):
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"agri-erp-listener-{frappe.generate_hash(length=6)}",
        clean_session=True,
    )
    client.user_data_set({"prefix": p["prefix"]})
    if p["auth"]:
        client.username_pw_set(p["auth"]["username"], p["auth"]["password"])
    if p["tls"]:
        client.tls_set()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    return client


def run(stop_after=None):
    """stop_after: seconds, for tests only."""
    p = get_conn_params()
    client = build_client(p)
    state["host"] = f"{p['host']}:{p['port']}{' TLS' if p['tls'] else ''} prefix={p['prefix']}"
    _say(f"starting for site {frappe.local.site} -> {p['host']}:{p['port']} (prefix {p['prefix']})")
    client.connect_async(p["host"], p["port"], keepalive=30)

    started = time.monotonic()
    delay, next_try, connecting_since = 1, 0.0, None
    last_beat = 0.0
    set_broker(False, push=False)

    while stop_after is None or time.monotonic() - started < stop_after:
        now = time.monotonic()

        if client.is_connected() or connecting_since is not None:
            rc = client.loop(timeout=1.0)
            if client.is_connected():
                connecting_since, delay = None, 1
            elif rc != mqtt.MQTT_ERR_SUCCESS or (connecting_since and now - connecting_since > 30):
                connecting_since, next_try = None, now + delay
                state["error"] = state["error"] or f"Connection lost: {mqtt.error_string(rc)}"
                _say(f"connection lost/failed ({mqtt.error_string(rc)}); retrying in {delay}s")
                delay = min(delay * 2, 60)
                if state["connected"]:
                    try:
                        set_broker(False)
                    except Exception:
                        pass
        elif now >= next_try:
            try:
                client.reconnect()
                connecting_since = now
            except Exception as e:
                state["error"] = f"Cannot reach {p['host']}:{p['port']}: {e}"
                _say(f"connect failed: {e}; retrying in {delay}s")
                try:
                    set_broker(False, push=False)
                except Exception:
                    pass
                next_try = now + delay
                delay = min(delay * 2, 60)
        else:
            time.sleep(0.5)

        if now - last_beat > 15:
            last_beat = now
            try:
                state["connected"] = client.is_connected()
                cache().set_value(CACHE_BROKER, broker_info(), expires_in_sec=BROKER_TTL)
            except Exception:
                pass

    client.disconnect()
