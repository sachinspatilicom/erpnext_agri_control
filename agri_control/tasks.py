import frappe
from frappe.utils import add_days, cint, now_datetime


def purge_old_logs():
    days = cint(frappe.db.get_single_value("Agri MQTT Settings", "log_retention_days"))
    if days > 0:
        frappe.db.delete("Agri Event Log", {"event_time": ["<", add_days(now_datetime(), -days)]})
    cdays = cint(frappe.db.get_single_value("Agri MQTT Settings", "climate_retention_days"))
    if cdays > 0:
        frappe.db.delete("Agri Climate Reading", {"reading_time": ["<", add_days(now_datetime(), -cdays)]})
    frappe.db.commit()
