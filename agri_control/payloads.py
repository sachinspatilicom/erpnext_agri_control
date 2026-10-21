"""Firmware contract for relay_scheduler.ino (ESP32, 14 relays) — pure Python, no Frappe imports.

Topics (prefix "agri"):
  <p>/relay/cmd/{0-13}  ERP -> ESP   "ON" | "OFF" | "AUTO"
  <p>/schedule/set      ERP -> ESP   {"relay":2,"type":"pulse","entries":[{"h":9,"m":30,"dur":3,"days":127}]}
                                     {"relay":1,"type":"fogger","startH":9,"endH":21,"pulseS":9}    Fogger 1 (R2)
                                     {"relay":13,"type":"fogger","startH":9,"endH":21,"pulseS":9}   Fogger 2 (R14, fw >= 2)
  <p>/status            ESP -> ERP   {"relays":[{"id":0,"name":"Master","state":false,"manual":false},...],
                                      "time":"09:30:05","wifi":"192.168.1.20","rssi":-61,"fw":2}   (retained, every 5 s)
  <p>/heartbeat         ESP -> ERP   "online" | "offline"   (retained, offline = MQTT last will)
  <p>/log               ESP -> ERP   plain text, e.g. "R3 (Zone1) ON by schedule"

Foggers: R2 runs seconds [0, P1) of every minute, R14 runs [P1, P1+P2) right after it; P1 + P2 <= 60.
Day mask: bit 0 = Sunday ... bit 6 = Saturday (tm_wday / DS3231). 127 = every day.
"""
import json
from datetime import timedelta

NUM_RELAYS = 14
MAX_SLOTS = 6                      # MAX_SCHED_PER_RELAY in firmware
ACTIONS = ("ON", "OFF", "AUTO")
FOG1, FOG2 = 1, 13                 # R2, R14
FOGGERS = (FOG1, FOG2)
FOG2_MIN_FW = 2                    # firmware version that knows R14 is Fogger 2

DAY_EVERY, DAY_WEEKDAYS, DAY_WEEKEND = 127, 62, 65
DAY_KEYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")   # bit order
PRESETS = {"Every day": DAY_EVERY, "Weekdays": DAY_WEEKDAYS, "Weekend": DAY_WEEKEND}

DEFAULT_NAMES = ["Master", "Fogger", "Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5",
                 "Zone 6", "Zone 7", "Zone 8", "Zone 9", "Zone 10", "Zone 11", "Fogger 2"]


def _twice(h, m, dur):
    return [{"h": h, "m": m, "dur": dur, "days": DAY_EVERY},
            {"h": h + 12, "m": m, "dur": dur, "days": DAY_EVERY}]


# Same as initDefaultSchedules() in the firmware and DEFAULT_SCHED in the old web app
DEFAULT_SCHED = (
    [{"type": "none"}, {"type": "fogger", "startH": 9, "endH": 21, "pulseS": 9}]
    + [{"type": "pulse", "entries": _twice(9, 30, 3)} for _ in range(2, 9)]
    + [{"type": "pulse", "entries": [{"h": 8, "m": m, "dur": 5, "days": DAY_EVERY}]}
       for m in (30, 35, 40, 45)]
    + [{"type": "fogger", "startH": 9, "endH": 21, "pulseS": 9}]          # R14 Fogger 2 (fw v2)
)


def relay_type(index):
    return "Master" if int(index) == 0 else "Fogger" if int(index) in FOGGERS else "Pulse"


def label(index):
    return f"R{int(index) + 1}"


# ------------------------------------------------------------------ days
def mask_from_days(preset, checks=None):
    """preset = Every day/Weekdays/Weekend/Custom; checks = dict sun..sat -> truthy."""
    if preset in PRESETS:
        return PRESETS[preset]
    mask = 0
    for bit, key in enumerate(DAY_KEYS):
        if (checks or {}).get(key):
            mask |= 1 << bit
    return mask or DAY_EVERY


def days_from_mask(mask):
    """-> (preset, {sun: 0/1 ...})"""
    mask = int(mask if mask not in (None, "") else DAY_EVERY) & 127 or DAY_EVERY
    checks = {k: (mask >> b) & 1 for b, k in enumerate(DAY_KEYS)}
    for name, val in PRESETS.items():
        if mask == val:
            return name, checks
    return "Custom", checks


# ------------------------------------------------------------------ times
def hm(value):
    """Frappe Time (timedelta or 'HH:MM[:SS]') -> (h, m)."""
    if isinstance(value, timedelta):
        total = int(value.total_seconds()) % 86400
        return total // 3600, (total % 3600) // 60
    parts = str(value).split(":")
    return int(parts[0]) % 24, int(parts[1]) % 60


def clamp(value, lo, hi, default):
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


# ------------------------------------------------------------------ schedules
def normalize_schedule(index, sched):
    """Validate/clamp a schedule dict in the old web-app format. Same limits as Index.cshtml."""
    index = int(index)
    kind = relay_type(index)
    sched = sched or {}
    if kind == "Master":
        return {"type": "none"}
    if kind == "Fogger":
        return {
            "type": "fogger",
            "startH": clamp(sched.get("startH"), 0, 23, 9),
            "endH": clamp(sched.get("endH"), 0, 23, 21),
            "pulseS": clamp(sched.get("pulseS"), 1, 55 if index == FOG1 else 59, 9),
        }
    entries = []
    for e in (sched.get("entries") or [])[:MAX_SLOTS]:
        days = clamp(e.get("days", DAY_EVERY), 0, 127, DAY_EVERY) or DAY_EVERY
        entries.append({
            "h": clamp(e.get("h"), 0, 23, 6),
            "m": clamp(e.get("m"), 0, 59, 0),
            "dur": clamp(e.get("dur"), 1, 180, 5),
            "days": days,
        })
    return {"type": "pulse", "entries": entries}


def schedule_payload(index, sched):
    """Exact JSON the firmware's handleScheduleUpdate() expects. None for Master."""
    s = normalize_schedule(index, sched)
    if s["type"] == "none":
        return None
    return {"relay": int(index), **s}


def summary(sched, index=None):
    """Same wording as schedSummary() in the old web app."""
    if not sched or sched.get("type") == "none":
        return "Auto-controlled"

    def h12(h):
        return f"{h % 12 or 12}{'PM' if h >= 12 else 'AM'}"

    if sched["type"] == "fogger":
        after = " after R2" if index == FOG2 else ""
        return f"{h12(sched['startH'])} – {h12(sched['endH'])}  |  {sched['pulseS']}s ON/min{after}"
    if not sched.get("entries"):
        return "No schedule"
    out = []
    for e in sched["entries"]:
        d = e.get("days", DAY_EVERY)
        tag = "" if d == DAY_EVERY else "(wkdays)" if d == DAY_WEEKDAYS else "(wkend)" if d == DAY_WEEKEND \
            else "(" + "".join("SMTWTFS"[b] for b in range(7) if (d >> b) & 1) + ")"
        out.append(f"{e['h'] % 12 or 12}:{e['m']:02d} {'PM' if e['h'] >= 12 else 'AM'} {e['dur']}min {tag}".rstrip())
    return "  |  ".join(out)


# ------------------------------------------------------------------ incoming
def parse_json(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def parse_status(text):
    """Firmware publishStatus() JSON -> {"relays":[{id,state,manual}], time, wifi, rssi} or None."""
    data = parse_json(text)
    if not isinstance(data, dict) or not isinstance(data.get("relays"), list):
        return None
    relays = []
    for r in data["relays"]:
        if isinstance(r, dict) and isinstance(r.get("id"), int):
            relays.append({"id": r["id"], "state": bool(r.get("state")), "manual": bool(r.get("manual"))})
    def num(v):
        return round(float(v), 1) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    sensor = data.get("sensor")  # firmware v3+: 1 ok / 0 not responding; missing = no sensor support
    return {"relays": relays, "time": data.get("time"), "wifi": data.get("wifi"), "rssi": data.get("rssi"),
            "fw": data.get("fw") if isinstance(data.get("fw"), int) else 1,
            "sensor": int(sensor) if isinstance(sensor, (int, bool)) else None,
            "temp": num(data.get("temp")) if sensor else None,
            "hum": num(data.get("hum")) if sensor else None}


class ClimateAverager:
    """Collects temp/hum samples and returns one averaged row per fixed window (aligned to the clock)."""

    def __init__(self, minutes):
        self.window = max(int(minutes or 0), 0) * 60
        self.key, self.t, self.h = None, [], []

    def add(self, ts_epoch, temp, hum):
        """Returns a finished row dict when a window closes, else None."""
        if not self.window or temp is None or hum is None:
            return None
        key = int(ts_epoch // self.window)
        done = None
        if self.key is not None and key != self.key and self.t:
            done = self.flush()
        self.key = key
        self.t.append(temp)
        self.h.append(hum)
        return done

    def flush(self):
        if not self.t:
            return None
        row = {"window_start": self.key * self.window, "window_end": (self.key + 1) * self.window,
               "temperature": round(sum(self.t) / len(self.t), 1), "humidity": round(sum(self.h) / len(self.h), 1),
               "temp_min": round(min(self.t), 1), "temp_max": round(max(self.t), 1),
               "hum_min": round(min(self.h), 1), "hum_max": round(max(self.h), 1),
               "samples": len(self.t)}
        self.t, self.h = [], []
        return row


def fogger_conflict(index, pulse_s, other_pulse_s):
    """Error text if R2 + R14 seconds don't fit in one minute, else None."""
    if int(pulse_s) + int(other_pulse_s or 0) <= 60:
        return None
    other = "R14 Fogger 2" if int(index) == FOG1 else "R2 Fogger"
    return (f"Fogger 1 and Fogger 2 run one after the other inside each minute, so their seconds must add up "
            f"to 60 or less. {other} uses {other_pulse_s}s, so this one can be at most {60 - int(other_pulse_s)}s.")


def parse_heartbeat(text):
    return "online" if (text or "").strip().lower() == "online" else "offline"


def valid_command(index, action):
    try:
        i = int(index)
    except (TypeError, ValueError):
        return False
    return 0 <= i < NUM_RELAYS and str(action) in ACTIONS


def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), default=str)
