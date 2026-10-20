"""Pure helpers for MQTT payloads (no Frappe imports, so they can be unit-tested anywhere).

If the controller firmware uses a different JSON shape, this is the one file to adapt.
"""
import json
import re
from datetime import timedelta

_TRUE = {"1", "on", "true", "yes", "high"}
_FALSE = {"0", "off", "false", "no", "low"}
_RELAY_KEY = re.compile(r"^(?:relay|r|ch)?[_\-]?(\d{1,3})$", re.IGNORECASE)


def parse_json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def to_bool(value):
    """Map 1/0, true/false, "ON"/"OFF" ... to True/False. Unknown -> None."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in _TRUE:
            return True
        if v in _FALSE:
            return False
    return None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_status(text):
    """Turn whatever the controller publishes on <prefix>/status into
    {"relays": {"1": True, "2": False, ...}, "extra": {...scalar readings...}}.

    Accepted shapes (examples):
      {"relays":[1,0,1,0]}                      -> index = position (1-based)
      {"relays":[{"id":1,"state":"ON"}, ...]}
      {"r1":1,"r2":0,"temp":24.5,"hum":81}
      {"relay1":"ON","relay2":"OFF"}
      [1,0,1,0]
    Non-relay scalar keys (temperature, humidity, uptime, rssi ...) go to "extra".
    """
    data = parse_json(text)
    relays, extra = {}, {}

    if isinstance(data, dict) and ("relays" in data or "relay" in data):
        src = data.get("relays", data.get("relay"))
        extra = {k: v for k, v in data.items()
                 if k not in ("relays", "relay") and not isinstance(v, (dict, list))}
    else:
        src = data

    if isinstance(src, list):
        for pos, item in enumerate(src, start=1):
            if isinstance(item, dict):
                idx = _int(item.get("id", item.get("index", item.get("relay", pos))))
                state = item.get("state", item.get("on", item.get("status")))
            else:
                idx, state = pos, item
            if idx is not None:
                relays[str(idx)] = to_bool(state)
    elif isinstance(src, dict):
        for key, value in src.items():
            if isinstance(value, (dict, list)):
                continue
            m = _RELAY_KEY.match(str(key))
            if m:
                relays[str(int(m.group(1)))] = to_bool(value)
            elif src is data:
                extra[key] = value

    return {"relays": relays, "extra": extra}


def detect_level(message):
    m = (message or "").upper()
    if "ERR" in m or "FAIL" in m:
        return "Error"
    if "WARN" in m:
        return "Warning"
    return "Info"


def day_mask(days):
    """days = 7 truthy values, Mon..Sun. Bit 0 = Mon ... bit 6 = Sun."""
    mask = 0
    for bit, on in enumerate(days):
        if on:
            mask |= 1 << bit
    return mask


def hhmm(value):
    """Frappe Time values arrive as timedelta or 'HH:MM[:SS[.ffffff]]' strings."""
    if isinstance(value, timedelta):
        total = int(value.total_seconds()) % 86400
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
    parts = str(value).split(":")
    return f"{int(parts[0]):02d}:{int(parts[1]):02d}"


def minutes_of_day(value):
    h, m = hhmm(value).split(":")
    return int(h) * 60 + int(m)


def build_schedule_payload(relay_index, enabled, schedule_type, days,
                           entries=None, on_minutes=None, off_minutes=None):
    """One message per relay on <prefix>/schedule/set, kept small for ESP buffers.

    Fixed:  {"relay":3,"en":1,"type":"fixed","days":127,"win":[["06:00","06:15"],["18:00","18:10"]]}
    Cyclic: {"relay":3,"en":1,"type":"cyclic","days":127,"on":5,"off":25}
    """
    payload = {
        "relay": int(relay_index),
        "en": 1 if enabled else 0,
        "type": "cyclic" if schedule_type == "Cyclic" else "fixed",
        "days": day_mask(days),
    }
    if payload["type"] == "cyclic":
        payload["on"] = int(on_minutes or 0)
        payload["off"] = int(off_minutes or 0)
    else:
        payload["win"] = [[hhmm(on), hhmm(off)] for on, off in (entries or [])]
    return payload


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), default=str)
