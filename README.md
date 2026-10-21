# Agri Control for ERPNext

ERPNext port of the **AgriControl_WebApp** (ASP.NET + SignalR + SQLite) for the 14-relay
ESP32 controller (`relay_scheduler.ino`) on HiveMQ Cloud. It runs inside
`erp.nutrigreenbite.com`, so no Windows server is needed.

| Old (ASP.NET)                          | Here                                                              |
|----------------------------------------|-------------------------------------------------------------------|
| `MqttService.cs`                       | `agri_control/listener.py`, run by supervisor (`bench … agri-mqtt`) |
| SignalR `AgriHub`                      | Frappe realtime (`agri_status`, `agri_heartbeat`, `agri_broker`, `agri_log`) |
| `RelayApiController` / `AgriHub.Send*` | `agri_control/api.py` (role-checked)                              |
| SQLite `agri_log.db`                   | **Agri Event Log** DocType (MariaDB), purged after N days         |
| `Index.cshtml`                         | Desk page **/app/agri-dashboard**                                 |
| Browser localStorage (names, locations, schedules, farm) | **Relay Config** (R1–R14) and **Agri MQTT Settings** — shared by all users |

## Install

```bash
cd /home/frappe/frappe-bench
bench get-app https://github.com/sachinspatilicom/erpnext_agri_control.git
# if the folder is apps/erpnext_agri_control:
#   mv apps/erpnext_agri_control apps/agri_control && bench pip install -e apps/agri_control
bench --site erp.nutrigreenbite.com install-app agri_control   # creates R1–R14 with firmware defaults
bench build --app agri_control && bench restart
```

Update later: `cd apps/agri_control && git pull && cd ../.. && bench --site erp.nutrigreenbite.com migrate && bench build --app agri_control && bench restart && sudo supervisorctl restart agri-mqtt`

## Set up

1. **/app/agri-mqtt-settings**: farm name and location, broker host `xxxx.s1.eu.hivemq.cloud`, port `8883`,
   **Use TLS** ticked, username and password, prefix `agri`. Click **Test Connection**.
2. Start the listener. First run it in the foreground: `bench --site erp.nutrigreenbite.com agri-mqtt`.
   For permanent use:
   ```bash
   sudo cp apps/agri_control/deploy/supervisor-agri-mqtt.conf /etc/supervisor/conf.d/agri-mqtt.conf
   sudo supervisorctl reread && sudo supervisorctl update
   ```
3. Open **/app/agri-dashboard**. Use the page menu, **⋯ → Import from old web app**, to copy names,
   locations and schedules from the browser where you used the old app.
4. Give staff the **Agri Operator** role. Only System Manager can clear the log or change MQTT settings.
5. Turn off the old ASP.NET app so commands and logs aren't duplicated.

Old SQLite log (optional): copy `App_Data/agri_log.db` from the Windows server, then
`bench --site erp.nutrigreenbite.com execute agri_control.migrate.import_sqlite_log --kwargs '{"path":"/home/frappe/agri_log.db"}'`

## Dashboard

Status badges (Device, Broker, Date, Time, Signal, IP), 14 relay cards (ON / OFF / AUTO, click a name or
location to edit it, Edit schedule), and the event log with date filter (defaults to today), search,
Load more and Clear. Everything updates live, without refreshing the page.
**Send all schedules** re-sends R2–R14 so the ESP32 matches ERPNext. The ESP32 never reports its
schedules back, so ERPNext is the master copy.

## MQTT contract (unchanged from the firmware)

| Topic | Direction | Payload |
|---|---|---|
| `agri/relay/cmd/{0-13}` | ERP → ESP | `ON`, `OFF` or `AUTO` (R1 = 0 … R14 = 13) |
| `agri/schedule/set` | ERP → ESP | `{"relay":2,"type":"pulse","entries":[{"h":9,"m":30,"dur":3,"days":127}]}` (max 6 entries) · `{"relay":1,"type":"fogger","startH":9,"endH":21,"pulseS":9}` |
| `agri/status` | ESP → ERP | retained, every 5 s: `{"relays":[{"id":0,"name":"Master","state":false,"manual":false},…],"time":"09:30:05","wifi":"192.168.1.20","rssi":-61}` |
| `agri/heartbeat` | ESP → ERP | retained `online`, MQTT last-will `offline` |
| `agri/log` | ESP → ERP | text, e.g. `R3 (Zone1) ON by schedule` |

Days bitmask: **bit 0 = Sunday … bit 6 = Saturday** (127 every day, 62 weekdays, 65 weekend).
R1 Master has no schedule (it follows the others). R2 Fogger uses a window plus seconds per minute.

## Code map

- `payloads.py`: firmware contract, defaults, validation and summaries (pure Python)
- `listener.py`: MQTT subscriber, reconnects automatically
- `mqtt.py`: settings, one-shot publish and log helper
- `api.py`: dashboard and command API
- `agri_control/page/agri_dashboard/agri_dashboard.js`: the dashboard
- `agri_control/doctype/*`: Relay Config, Relay Schedule Slot, Agri MQTT Settings, Agri Event Log
