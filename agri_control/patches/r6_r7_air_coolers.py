"""Firmware v6: R6 / R7 (Zone 4 / Zone 5) become Air Cooler 1 / 2, OFF 03:00-07:00 by default."""
import frappe

from agri_control.payloads import COOLERS, DEFAULT_SCHED, label


def execute():
    for k, idx in enumerate(COOLERS, start=1):
        name = label(idx)
        if not frappe.db.exists("Relay Config", name):
            continue  # fresh install: after_migrate creates it
        doc = frappe.get_doc("Relay Config", name)
        if doc.relay_type == "Air Cooler":
            continue
        if (doc.relay_name or "").replace(" ", "").lower() in (f"zone{idx - 1}", name.lower(), ""):
            doc.relay_name = f"Air Cooler {k}"
        doc.slots = []
        doc.relay_type = "Air Cooler"
        doc.set_schedule(DEFAULT_SCHED[idx])
        doc.save(ignore_permissions=True)
