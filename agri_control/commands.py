import click
import frappe
from frappe.commands import get_site, pass_context


@click.command("agri-mqtt")
@pass_context
def agri_mqtt(context):
    """Run the Agri Control MQTT listener (long-running, keep one per site)."""
    site = get_site(context)
    frappe.init(site=site)
    frappe.connect()
    try:
        from agri_control.listener import run

        run()
    finally:
        frappe.destroy()


commands = [agri_mqtt]
