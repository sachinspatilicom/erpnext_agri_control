# Agri Control (Frappe app)

Relay control, schedules and live MQTT monitoring for the NutrigreenBite farm, running inside
ERPNext at `erp.nutrigreenbite.com`. Replaces the ASP.NET + SignalR + SQLite app.

| Old (ASP.NET)             | Here                                                         |
|---------------------------|--------------------------------------------------------------|
| `MqttService.cs`          | `agri_control/listener.py`, run by supervisor (`bench ... agri-mqtt`) |
| SignalR                   | `frappe.publish_realtime` → `frappe.realtime.on` (Socket.IO) |
| SQLite log                | **Agri Event Log** DocType (MariaDB), auto-purged daily      |
| `RelayApiController`      | `agri_control/api.py` (whitelisted, role-checked)            |
| `Index.cshtml`            | Desk page **/app/agri-dashboard**                            |
| Schedule editor JS        | **Relay Schedule** DocType form + "Send to Controller" button |

## Install

```bash
cd /home/frappe/frappe-bench
# copy the agri_control folder into apps/  (or: bench get-app <git-url>)
bench pip install -e apps/agri_control          # also installs paho-mqtt
grep -qx agri_control sites/apps.txt || echo agri_control >> sites/apps.txt
bench --site erp.nutrigreenbite.com install-app agri_control
bench build --app agri_control
bench restart

# start the listener (one per site)
sudo cp apps/agri_control/deploy/supervisor-agri-mqtt.conf /etc/supervisor/conf.d/agri-mqtt.conf
sudo supervisorctl reread && sudo supervisorctl update
tail -f logs/agri-mqtt.log
```

For a quick foreground test instead of supervisor: `bench --site erp.nutrigreenbite.com agri-mqtt`.

## First-time setup in ERPNext

1. **Agri MQTT Settings** — broker host/port, username/password, topic prefix (`agri`). Click **Test Connection**.
   Restart the listener after changing broker settings: `sudo supervisorctl restart agri-mqtt`.
2. **Relay Config** — one row per relay: name, *Relay Index* (the number the controller uses), location.
3. **Relay Schedule** — one enabled schedule per relay, Fixed Times or Cyclic, with days. Save → **Send to Controller**.
4. Give staff the **Agri Operator** role (dashboard, ON/OFF, edit schedules). System Manager has everything.
5. Open **/app/agri-dashboard**.

## MQTT topic contract (firmware must match)

Prefix `agri` shown; it is configurable.

| Topic                    | Direction        | Payload |
|--------------------------|------------------|---------|
| `agri/status`            | controller → ERP | JSON relay states, any of: `{"relays":[1,0,1]}`, `{"relays":[{"id":1,"state":"ON"}]}`, `{"r1":1,"r2":0,"temp":24.5,"hum":81}`. Extra scalar keys (temp, hum, rssi…) show as readings. |
| `agri/log`               | controller → ERP | Plain text. Contains `ERR`/`FAIL` → Error, `WARN` → Warning. |
| `agri/heartbeat`         | controller → ERP | Anything (text or JSON). Controller shows Offline after *Heartbeat Timeout* seconds of silence. |
| `agri/relay/cmd/<index>` | ERP → controller | `ON` or `OFF` (QoS 1) |
| `agri/schedule/set`      | ERP → controller | One message **per relay** (small, fits ESP buffers):<br>`{"relay":3,"en":1,"type":"fixed","days":127,"win":[["06:00","06:15"],["18:00","18:10"]]}`<br>`{"relay":3,"en":1,"type":"cyclic","days":127,"on":5,"off":25}` |
| `agri/ping`              | ERP → controller | Sent by Test Connection; controller may ignore it. |

`days` is a bit mask: bit 0 = Mon … bit 6 = Sun (127 = every day). A window whose OFF time is earlier
than its ON time runs past midnight. If your firmware expects a different shape, change only
`agri_control/payloads.py` (`normalize_status`, `build_schedule_payload`).

## Notes

- Relay ON/OFF changes are logged only when the state actually changes in `agri/status`, so frequent
  status messages don't flood the database. Every command sent from the dashboard is logged with the user.
- Live updates go to logged-in desk users; the API itself only answers System Manager / Agri Operator.
- Run only **one** listener per site, otherwise every log line is stored twice.
