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
| `agri/schedule/set` | ERP → ESP | `{"relay":2,"type":"pulse","entries":[{"h":9,"m":30,"dur":3,"days":127}]}` (max 6 entries) · `{"relay":1,"type":"fogger","startH":9,"endH":21,"pulseS":9}` · `{"relay":13,"type":"fogger",…}` (R14, fw v2) |
| `agri/status` | ESP → ERP | retained, every 5 s: `{"relays":[{"id":0,"name":"Master","state":false,"manual":false},…],"time":"09:30:05","wifi":"192.168.1.20","rssi":-61}` |
| `agri/heartbeat` | ESP → ERP | retained `online`, MQTT last-will `offline` |
| `agri/log` | ESP → ERP | text, e.g. `R3 (Zone1) ON by schedule` |

Days bitmask: **bit 0 = Sunday … bit 6 = Saturday** (127 every day, 62 weekdays, 65 weekend).
R1 Master has no schedule (it follows the others). **Firmware v4:** R2 is the fogger **pump** feeding five
fogger valves R9–R13. Every minute in R2's hours the valves open one after another for R2's seconds each
(valve k: `k·P … (k+1)·P + 1` s — the next opens 1 s before the previous closes) and the pump runs
`1 … 5·P` s, so it never pushes against closed valves (with every valve closed by hand it won't start).
R14 Fogger 2 runs right after the cycle (`5·P + 1 … + P2`). Limits: P ≤ 11 and 5·P + 1 + P2 ≤ 60.
A fogger valve switched ON or OFF by hand (firmware v5) is skipped: the remaining AUTO valves close up,
the pump runs n·P seconds without a gap and R14 starts right after. AUTO puts the valve back in its turn.
R9–R13 have no schedule of their own.
**Firmware v6:** R6 / R7 are **Air Cooler 1 / 2** (230V). They run all the time except their OFF hours
(default 03:00–07:00, set per cooler, may cross midnight; same hour twice = always ON). Payload
`{"relay":5,"type":"cooler","offStartH":3,"offEndH":7}`. Coolers do not switch on the R1 Master 24V adapter. The firmware reports `"fw"`; R14 fogger settings need fw ≥ 2.

## Temperature / humidity sensor (firmware v3)

Renke **RS-WS-N01** (RS485 Modbus-RTU, address 1, 4800 baud 8N1) on the ESP32 through a TTL↔RS485 adapter:

| From | To |
|---|---|
| Sensor brown (+) | +24V on the **always-on** side (not after the R1 Master relay) |
| Sensor black (−) | 24V − (same GND as the ESP32) |
| Sensor yellow (A) | adapter A+ |
| Sensor blue (B) | adapter B− |
| Adapter TXD / RO | ESP32 GPIO34 |
| Adapter RXD / DI | ESP32 GPIO5 |
| Adapter VCC / GND | ESP32 3V3 / GND |

MAX485 module: also wire DE+RE together to GPIO2 and set `RS485_DE_PIN 2` in the sketch.
The ESP32 reads every 5 s and adds `"sensor":1,"temp":24.5,"hum":81.2` to `agri/status`
(`"sensor":0` when it stops answering, logged once). ERPNext shows live badges, saves the
5-minute average (with min/max) in **Agri Climate Reading**, and draws 24 h / 7 day / 30 day charts.
Settings: *Save a reading every (minutes)* and *Keep readings (days)* in Agri MQTT Settings.

## Code map

- `payloads.py`: firmware contract, defaults, validation and summaries (pure Python)
- `listener.py`: MQTT subscriber, reconnects automatically
- `mqtt.py`: settings, one-shot publish and log helper
- `api.py`: dashboard and command API
- `agri_control/page/agri_dashboard/agri_dashboard.js`: the dashboard
- `agri_control/doctype/*`: Relay Config, Relay Schedule Slot, Agri MQTT Settings, Agri Event Log
