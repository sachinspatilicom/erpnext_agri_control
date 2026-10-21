import frappe
from frappe.model.document import Document
from frappe.utils import cint

from agri_control.payloads import (DAY_KEYS, MAX_SLOTS, NUM_RELAYS, clamp, days_from_mask, hm,
                                   label, mask_from_days, normalize_schedule, relay_type,
                                   schedule_payload, summary)


class RelayConfig(Document):
    def autoname(self):
        self.name = label(self.relay_index)  # R1 ... R14

    def validate(self):
        idx = cint(self.relay_index)
        if not 0 <= idx < NUM_RELAYS:
            frappe.throw(f"Relay Index must be 0 to {NUM_RELAYS - 1} (R1 = 0)")
        if not self.is_new() and self.name != label(idx):
            frappe.throw("Relay Index cannot be changed once created")
        self.relay_type = relay_type(idx)
        self.relay_name = (self.relay_name or label(idx)).strip()[:30]

        self.fog_start_hour = clamp(self.fog_start_hour, 0, 23, 9)
        self.fog_end_hour = clamp(self.fog_end_hour, 0, 23, 21)
        self.fog_pulse_sec = clamp(self.fog_pulse_sec, 1, 55, 9)

        if self.relay_type != "Pulse":
            self.slots = []
        if len(self.slots) > MAX_SLOTS:
            frappe.throw(f"The controller holds at most {MAX_SLOTS} time slots per relay")
        for row in self.slots:
            row.duration_min = clamp(row.duration_min, 1, 180, 5)
            row.day_mask = mask_from_days(row.days, {k: row.get(k) for k in DAY_KEYS})
            row.days, checks = days_from_mask(row.day_mask)
            for k, v in checks.items():
                row.set(k, v)

    # ---- old web-app schedule format <-> fields
    def get_schedule(self):
        if self.relay_type == "Master":
            return {"type": "none"}
        if self.relay_type == "Fogger":
            return {"type": "fogger", "startH": cint(self.fog_start_hour),
                    "endH": cint(self.fog_end_hour), "pulseS": cint(self.fog_pulse_sec)}
        entries = []
        for row in self.slots:
            h, m = hm(row.on_time)
            entries.append({"h": h, "m": m, "dur": cint(row.duration_min), "days": cint(row.day_mask) or 127})
        return {"type": "pulse", "entries": entries}

    def set_schedule(self, sched):
        s = normalize_schedule(self.relay_index, sched)
        if s["type"] == "fogger":
            self.fog_start_hour, self.fog_end_hour, self.fog_pulse_sec = s["startH"], s["endH"], s["pulseS"]
        elif s["type"] == "pulse":
            self.slots = []
            for e in s["entries"]:
                preset, checks = days_from_mask(e["days"])
                self.append("slots", {"on_time": f"{e['h']:02d}:{e['m']:02d}:00",
                                      "duration_min": e["dur"], "days": preset, **checks})

    def get_payload(self):
        return schedule_payload(self.relay_index, self.get_schedule())

    def get_summary(self):
        return summary(self.get_schedule())
