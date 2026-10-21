"""One-off import of the old ASP.NET app's SQLite event log (App_Data/agri_log.db).

Copy agri_log.db to the server, then:
    bench --site erp.nutrigreenbite.com execute agri_control.migrate.import_sqlite_log \
        --kwargs '{"path": "/home/frappe/agri_log.db"}'
"""
import sqlite3

import frappe
from frappe.utils import get_datetime


def import_sqlite_log(path):
    con = sqlite3.connect(path)
    rows = con.execute("SELECT CreatedAt, Message FROM EventLog ORDER BY Id").fetchall()
    con.close()
    count = 0
    for created_at, message in rows:
        if not message:
            continue
        frappe.get_doc({
            "doctype": "Agri Event Log",
            "event_time": get_datetime(created_at),
            "message": message[:500],
            "source": "Device",
        }).insert(ignore_permissions=True)
        count += 1
    frappe.db.commit()
    print(f"Imported {count} log entries from {path}")
    return count
