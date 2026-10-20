import frappe

ROLE = "Agri Operator"


def ensure_role():
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc({
            "doctype": "Role",
            "role_name": ROLE,
            "desk_access": 1,
        }).insert(ignore_permissions=True)


def before_install():
    ensure_role()


def after_install():
    ensure_role()
    settings = frappe.get_single("Agri MQTT Settings")
    if not settings.broker_host:
        settings.broker_host = "localhost"
        settings.broker_port = 1883
        settings.topic_prefix = "agri"
        settings.heartbeat_timeout_sec = 90
        settings.log_retention_days = 90
        settings.flags.ignore_mandatory = True
        settings.save(ignore_permissions=True)
    frappe.db.commit()
