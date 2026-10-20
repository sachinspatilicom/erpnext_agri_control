import frappe
from frappe.model.document import Document
from frappe.utils import cint

from agri_control.payloads import build_schedule_payload, day_mask, minutes_of_day

DAY_FIELDS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class RelaySchedule(Document):
    def validate(self):
        days = [cint(self.get(f)) for f in DAY_FIELDS]
        if not any(days):
            frappe.throw("Select at least one day")
        self.day_mask = day_mask(days)

        if self.schedule_type == "Cyclic":
            if cint(self.on_minutes) <= 0 or cint(self.off_minutes) <= 0:
                frappe.throw("ON and OFF minutes must both be greater than 0 for a Cyclic schedule")
        else:
            if not self.entries:
                frappe.throw("Add at least one ON / OFF time window")
            for row in self.entries:
                if minutes_of_day(row.on_time) == minutes_of_day(row.off_time):
                    frappe.throw(f"Row {row.idx}: ON and OFF time cannot be the same")

        if self.enabled:
            clash = frappe.db.get_value(
                "Relay Schedule",
                {"relay": self.relay, "enabled": 1, "name": ["!=", self.name or ""]},
                "name",
            )
            if clash:
                frappe.throw(
                    f"Relay {self.relay} already has an enabled schedule ({clash}). "
                    "The controller keeps one schedule per relay - disable that one first."
                )

    def get_payload(self):
        relay_index = frappe.db.get_value("Relay Config", self.relay, "relay_index")
        return build_schedule_payload(
            relay_index=relay_index,
            enabled=cint(self.enabled),
            schedule_type=self.schedule_type,
            days=[cint(self.get(f)) for f in DAY_FIELDS],
            entries=[(r.on_time, r.off_time) for r in self.entries],
            on_minutes=self.on_minutes,
            off_minutes=self.off_minutes,
        )
