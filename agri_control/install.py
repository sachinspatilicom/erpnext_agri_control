import frappe

from agri_control.payloads import DEFAULT_NAMES, DEFAULT_SCHED, NUM_RELAYS, label

ROLE = "Agri Operator"


def ensure_role():
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(
            ignore_permissions=True)


def ensure_relays():
    """Create R1..R14 with the firmware's default names and schedules (only missing ones)."""
    for idx in range(NUM_RELAYS):
        if frappe.db.exists("Relay Config", label(idx)):
            continue
        doc = frappe.new_doc("Relay Config")
        doc.relay_index = idx
        doc.relay_name = DEFAULT_NAMES[idx]
        doc.set_schedule(DEFAULT_SCHED[idx])
        doc.insert(ignore_permissions=True)


def before_install():
    ensure_role()


def after_install():
    ensure_role()
    s = frappe.get_single("Agri MQTT Settings")
    if not s.topic_prefix:
        s.update({"farm_name": "Agri Controller", "broker_port": 8883, "use_tls": 1,
                  "topic_prefix": "agri", "log_retention_days": 90})
        s.flags.ignore_mandatory = True
        s.save(ignore_permissions=True)
    ensure_relays()
    frappe.db.commit()


def after_migrate():
    ensure_role()
    ensure_relays()
