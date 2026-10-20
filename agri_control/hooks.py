app_name = "agri_control"
app_title = "Agri Control"
app_publisher = "NutrigreenBite"
app_description = "Relay control, schedules and live MQTT monitoring for the farm"
app_email = "admin@nutrigreenbite.com"
app_license = "mit"

# Role must exist before DocType / Page JSON (which reference it) are synced.
before_install = "agri_control.install.before_install"
after_install = "agri_control.install.after_install"
after_migrate = "agri_control.install.ensure_role"

scheduler_events = {
    "daily": [
        "agri_control.tasks.purge_old_logs",
    ],
}
