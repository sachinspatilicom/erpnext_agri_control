"""Firmware v4: R9-R13 (Zone 7-11) become fogger valves 1-5 fed by the R2 pump."""
import frappe

from agri_control.payloads import FOG1, FOG1_MAX, FOG2, FOGV, fog_cycle, label


def execute():
    # keep the minute budget valid first: R2 <= 11 s per valve, R14 fits after the cycle
    if frappe.db.exists("Relay Config", label(FOG1)):
        p1 = min(int(frappe.db.get_value("Relay Config", label(FOG1), "fog_pulse_sec") or 9), FOG1_MAX)
        frappe.db.set_value("Relay Config", label(FOG1), "fog_pulse_sec", p1)
        if frappe.db.get_value("Relay Config", label(FOG1), "relay_name") in ("Fogger", "Fogger 1"):
            frappe.db.set_value("Relay Config", label(FOG1), "relay_name", "Fogger pump")
        if frappe.db.exists("Relay Config", label(FOG2)):
            p2 = int(frappe.db.get_value("Relay Config", label(FOG2), "fog_pulse_sec") or 9)
            frappe.db.set_value("Relay Config", label(FOG2), "fog_pulse_sec", max(1, min(p2, 60 - fog_cycle(p1))))

    for k, idx in enumerate(FOGV, start=1):
        name = label(idx)
        if not frappe.db.exists("Relay Config", name):
            continue
        doc = frappe.get_doc("Relay Config", name)
        if doc.relay_type == "Fogger Valve":
            continue
        if (doc.relay_name or "").replace(" ", "").lower() in (f"zone{idx - 1}", name.lower(), ""):
            doc.relay_name = f"Fogger valve {k}"
        doc.slots = []
        doc.relay_type = "Fogger Valve"
        doc.save(ignore_permissions=True)
