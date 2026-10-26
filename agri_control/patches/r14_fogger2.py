"""Firmware v2: R14 (index 13) is Fogger 2 instead of Zone 12."""
import frappe

from agri_control.payloads import DEFAULT_SCHED, FOG1, FOG2, fog_cycle, label


def execute():
    name = label(FOG2)
    if not frappe.db.exists("Relay Config", name):
        return  # fresh install: after_migrate creates it as Fogger 2
    doc = frappe.get_doc("Relay Config", name)
    if doc.relay_type == "Fogger":
        return
    if (doc.relay_name or "").replace(" ", "").lower() in ("zone12", "r14", ""):
        doc.relay_name = "Fogger 2"
    doc.slots = []
    doc.relay_type = "Fogger"
    sched = dict(DEFAULT_SCHED[FOG2])
    p1 = frappe.db.get_value("Relay Config", label(FOG1), "fog_pulse_sec") or 9
    sched["pulseS"] = max(1, min(sched["pulseS"], 60 - fog_cycle(min(int(p1), 11))))  # must fit after the valve cycle
    doc.set_schedule(sched)
    doc.save(ignore_permissions=True)
