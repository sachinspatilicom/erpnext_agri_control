app_name = "agri_control"
app_title = "Agri Control"
app_publisher = "NutrigreenBite"
app_description = "ESP32 relay control, schedules and live MQTT monitoring for the farm"
app_email = "admin@nutrigreenbite.com"
app_license = "mit"

# Role must exist before DocType / Page JSON (which reference it) are synced.
before_install = "agri_control.install.before_install"
after_install = "agri_control.install.after_install"
after_migrate = "agri_control.install.after_migrate"

# Tile on the /apps screen (Frappe v15+; ignored on v14)
add_to_apps_screen = [
    {
        "name": "agri_control",
        "logo": "/assets/agri_control/agri.svg",
        "title": "Agri Control",
        "route": "/app/agri-dashboard",
    }
]

scheduler_events = {
    "daily": ["agri_control.tasks.purge_old_logs"],
}
