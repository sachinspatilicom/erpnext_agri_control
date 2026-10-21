import time

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


@click.command("agri-mqtt-check")
@pass_context
def agri_mqtt_check(context):
    """Test the broker connection once and show what the ESP32 is publishing."""
    import paho.mqtt.client as mqtt

    site = get_site(context)
    frappe.init(site=site)
    frappe.connect()
    try:
        from agri_control.listener import build_client
        from agri_control.mqtt import get_conn_params

        p = get_conn_params()
        auth = p["auth"] or {}
        click.echo(f"Broker   : {p['host']}:{p['port']}  TLS={'on' if p['tls'] else 'OFF'}")
        click.echo(f"User     : {auth.get('username') or '(none)'}  password={'set' if auth.get('password') else 'NOT SET'}")
        click.echo(f"Prefix   : {p['prefix']}   (ESP32 firmware uses 'agri')")

        got, result = {}, {}
        client = build_client(p)

        def on_connect(c, u, f, rc, props=None):
            result["rc"] = rc
            if not rc.is_failure:
                c.subscribe([(f"{p['prefix']}/heartbeat", 0), (f"{p['prefix']}/status", 0)])

        def on_message(c, u, m):
            got[m.topic] = m.payload.decode("utf-8", "replace")

        client.on_connect, client.on_message, client.on_disconnect = on_connect, on_message, None
        try:
            client.connect(p["host"], p["port"], keepalive=20)
        except Exception as e:
            click.secho(f"FAIL: cannot open connection: {e}", fg="red")
            click.echo("  -> check host spelling, Use TLS + port 8883, and that the server allows outbound port 8883")
            return
        end = time.time() + 10
        while time.time() < end and "rc" not in result:
            client.loop(0.5)
        rc = result.get("rc")
        if rc is None:
            click.secho("FAIL: no answer from broker (TLS handshake / firewall?)", fg="red")
            return
        if rc.is_failure:
            click.secho(f"FAIL: broker refused login: {rc}  -> check username / password", fg="red")
            return
        click.secho("OK: connected and logged in", fg="green")
        end = time.time() + 7
        while time.time() < end and len(got) < 2:
            client.loop(0.5)
        hb = got.get(f"{p['prefix']}/heartbeat")
        st = got.get(f"{p['prefix']}/status")
        click.echo(f"Heartbeat: {hb if hb is not None else 'nothing received'}")
        click.echo(f"Status   : {(st[:160] + '...') if st else 'nothing received'}")
        if hb is None and st is None:
            click.secho("No ESP32 messages on this prefix. Is the prefix 'agri' and is the ESP32 powered and online?", fg="yellow")
        client.disconnect()
    finally:
        frappe.destroy()


commands = [agri_mqtt, agri_mqtt_check]
