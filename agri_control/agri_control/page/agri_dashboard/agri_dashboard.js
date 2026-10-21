// Agri Control dashboard — port of AgriControl_WebApp/Views/Home/Index.cshtml to a Frappe desk page.
// SignalR -> frappe.realtime ; localStorage -> Relay Config / Agri MQTT Settings in ERPNext.

frappe.pages["agri-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Agri Control"), single_column: true });
	wrapper.agri = new AgriDashboard(page);
};
frappe.pages["agri-dashboard"].on_page_show = function (wrapper) {
	wrapper.agri && wrapper.agri.refresh();
};

// Day-of-week bitmask: bit 0 = Sunday ... bit 6 = Saturday (matches the ESP32 firmware)
const AG_DAY_EVERY = 127, AG_DAY_WEEKDAYS = 62, AG_DAY_WEEKEND = 65;
const AG_DAY_SHORT = ["S", "M", "T", "W", "T", "F", "S"];
const AG_DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const AGRI_CSS = `
.agri { --ag-on:#27ae60; --ag-off-btn:#c0392b; --ag-auto:#2980b9; --ag-manual:#e67e22;
	--ag-master:#e94560; --ag-fogger:#3498db; --ag-sched:#8e44ad; padding-bottom:32px; }
.agri-farm { display:flex; align-items:baseline; flex-wrap:wrap; gap:4px 14px; margin:4px 0 12px; }
.agri-farm-name { font-size:var(--text-xl); font-weight:700; }
.agri-farm-loc { color:var(--text-muted); }
.agri-farm-edit { margin-left:auto; }
.agri-warn { padding:10px 14px; border-radius:8px; margin-bottom:12px;
	background:var(--bg-yellow); color:var(--text-on-yellow); }
.agri-status { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:14px; }
.agri-sb { padding:3px 11px; border-radius:12px; font-size:var(--text-sm); background:var(--control-bg);
	color:var(--text-muted); transition:background .4s,color .4s; }
.agri-sb.ok { background:var(--bg-green); color:var(--text-on-green); }
.agri-sb.warn { background:var(--bg-orange); color:var(--text-on-orange); }
.agri-sb.fail { background:var(--bg-red); color:var(--text-on-red); }

.agri-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(178px,1fr)); gap:10px; margin-bottom:22px; }
.agri-card { background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:11px 12px;
	display:flex; flex-direction:column; transition:box-shadow .3s; }
.agri-card.active { box-shadow:0 0 0 2px var(--ag-on), 0 0 12px rgba(39,174,96,.35); }
.agri-card.master { border-color:var(--ag-master); }
.agri-card.fogger { border-color:var(--ag-fogger); }
.agri-top { display:flex; align-items:baseline; gap:6px; }
.agri-rnum { font-size:var(--text-xs); font-weight:700; color:var(--ag-master); flex:none; }
.agri-rname { font-weight:600; flex:1; min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
	cursor:text; border-bottom:1px dashed transparent; }
.agri-rname:hover, .agri-rloc:hover { border-bottom-color:var(--gray-400); }
.agri-rloc { font-size:var(--text-xs); color:var(--text-muted); min-height:17px; margin:1px 0 7px; cursor:text;
	white-space:nowrap; overflow:hidden; text-overflow:ellipsis; border-bottom:1px dashed transparent; }
.agri-rloc .ph { opacity:.5; }
.agri-inline { width:100%; margin:0 0 4px; height:26px; padding:2px 6px; font-size:var(--text-sm); }
.agri-badge { align-self:center; padding:2px 11px; border-radius:10px; font-size:var(--text-xs); font-weight:700;
	color:#fff; background:var(--gray-500); margin-bottom:8px; letter-spacing:.02em; }
.agri-badge.s-on { background:var(--ag-on); }
.agri-badge.s-manual { background:var(--ag-manual); }
.agri-badge.s-unknown { background:var(--gray-400); }
.agri-btns { display:grid; grid-template-columns:repeat(3,1fr); gap:4px; margin-bottom:5px; }
.agri-btns button { border:0; border-radius:6px; color:#fff; font-size:var(--text-xs); font-weight:700; padding:6px 0; }
.agri-btns button:hover { filter:brightness(1.1); }
.agri-btns button:disabled { opacity:.5; }
.agri-btns button:focus-visible, .agri-sched:focus-visible { outline:2px solid var(--text-color); outline-offset:1px; }
.ab-on { background:var(--ag-on); } .ab-off { background:var(--ag-off-btn); } .ab-auto { background:var(--ag-auto); }
.agri-sched { border:0; border-radius:6px; padding:5px; font-size:var(--text-xs); color:var(--ag-sched);
	background:rgba(142,68,173,.12); }
.agri-sched:hover { background:rgba(142,68,173,.22); }
.agri-sum { font-size:11px; color:var(--text-muted); margin-top:5px; line-height:1.45; }

.agri-h { font-size:var(--text-lg); font-weight:600; margin-bottom:8px; }
.agri-logtools { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-bottom:8px; }
.agri-logtools .agri-date { width:170px; }
.agri-logtools .agri-search { flex:1 1 200px; max-width:340px; }
.agri-count { margin-left:auto; color:var(--text-muted); font-size:var(--text-sm); }
.agri-log { display:flex; flex-direction:column; gap:3px; }
.agri-le { display:flex; gap:12px; padding:6px 10px; background:var(--card-bg); border:1px solid var(--border-color);
	border-radius:6px; font-size:var(--text-sm); }
.agri-le.user { border-left:3px solid var(--ag-auto); }
.agri-le.system { border-left:3px solid var(--gray-400); }
.agri-le.fresh { animation:agri-fresh 1.6s ease-out; }
@keyframes agri-fresh { from { background:rgba(39,174,96,.18); } }
.agri-lt { color:var(--text-muted); white-space:nowrap; min-width:104px; font-variant-numeric:tabular-nums; }
.agri-lm { word-break:break-word; }
.agri-lu { margin-left:auto; color:var(--text-muted); white-space:nowrap; }
.agri-more { width:100%; margin-top:6px; border-style:dashed; }
.agri-empty { padding:22px; text-align:center; color:var(--text-muted); border:1px dashed var(--border-color); border-radius:8px; }

/* schedule dialog */
.ag-se { border:1px solid var(--border-color); border-radius:8px; padding:10px 12px; margin-bottom:8px; }
.ag-r { display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.ag-r + .ag-r { margin-top:8px; }
.ag-in { width:58px; text-align:center; height:30px; padding:2px 4px; }
.ag-ap, .ag-freq { width:auto; height:30px; padding:2px 6px; }
.ag-lbl { color:var(--text-muted); font-size:var(--text-sm); }
.ag-del { margin-left:auto; }
.ag-days { display:flex; gap:3px; }
.ag-dt { width:28px; height:28px; padding:0; border-radius:5px; border:1px solid var(--border-color);
	background:var(--control-bg); color:var(--text-muted); font-size:var(--text-xs); }
.ag-dt.active { background:var(--ag-auto); border-color:var(--ag-auto); color:#fff; }
.ag-add { width:100%; border-style:dashed; }
.ag-note { color:var(--text-muted); font-size:var(--text-sm); margin-top:8px; }
@media (max-width:600px) { .agri-grid { grid-template-columns:1fr 1fr; } .agri-lu { display:none; } }
@media (prefers-reduced-motion:reduce) { .agri-le.fresh { animation:none; } .agri-card, .agri-sb { transition:none; } }`;

class AgriDashboard {
	constructor(page) {
		this.page = page;
		this.relays = [];
		this.log = { offset: 0, limit: 50, total: 0, search: "", date: frappe.datetime.get_today() };
		frappe.dom.set_style(AGRI_CSS, "agri-dashboard-css");

		page.set_primary_action(__("Send all schedules"), () => this.pushAll(), "upload");
		page.add_menu_item(__("Import from old web app"), () => this.importOld());
		page.add_menu_item(__("MQTT settings"), () => frappe.set_route("Form", "Agri MQTT Settings"));
		page.add_menu_item(__("Relay list"), () => frappe.set_route("List", "Relay Config"));
		page.add_menu_item(__("Event log report"), () => frappe.set_route("List", "Agri Event Log", "Report"));

		this.$root = $(`
		<div class="agri">
			<div class="agri-farm">
				<span class="agri-farm-name"></span><span class="agri-farm-loc"></span>
				<button class="btn btn-default btn-xs agri-farm-edit">${__("Edit farm")}</button>
			</div>
			<div class="agri-warn" style="display:none"></div>
			<div class="agri-status">
				<span class="agri-sb fail" data-b="hb">${__("Device: Offline")}</span>
				<span class="agri-sb warn" data-b="broker">${__("Broker: Checking…")}</span>
				<span class="agri-sb ok" data-b="date">${__("Date")}: --</span>
				<span class="agri-sb" data-b="time">${__("Time")}: --:--:--</span>
				<span class="agri-sb" data-b="rssi">${__("Signal")}: --</span>
				<span class="agri-sb" data-b="wifi">IP: --</span>
			</div>
			<div class="agri-grid"></div>
			<div class="agri-h">${__("Event Log")}</div>
			<div class="agri-logtools">
				<input type="date" class="form-control agri-date" aria-label="${__("Filter by date")}">
				<input type="search" class="form-control agri-search" placeholder="${__("Search log…")}" maxlength="80">
				<button class="btn btn-default btn-sm agri-clear" style="display:none">${__("Clear")}</button>
				<span class="agri-count"></span>
			</div>
			<div class="agri-log"></div>
			<button class="btn btn-default btn-sm agri-more" style="display:none">${__("Load more…")}</button>
		</div>`).appendTo(page.main);

		this.bind();
		this.tickDate();
		setInterval(() => this.tickDate(), 60000);
		setInterval(() => this.pollLive(), 30000);
		this.refresh();
	}

	// ------------------------------------------------------------ helpers
	esc(s) { return frappe.utils.escape_html(s == null ? "" : String(s)); }
	badge(key, text, cls) {
		this.$root.find(`[data-b="${key}"]`).text(text).attr("class", "agri-sb " + (cls || ""));
	}
	fmtTime(dt) { // "HH:mm:ss dd/MM" like the old app
		const d = frappe.datetime.str_to_obj(dt);
		const p = (n) => String(n).padStart(2, "0");
		return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())} ${p(d.getDate())}/${p(d.getMonth() + 1)}`;
	}
	tickDate() {
		const n = new Date();
		const mons = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
		this.badge("date", `${__("Date")}: ${AG_DAY_NAMES[n.getDay()]}, ${String(n.getDate()).padStart(2, "0")} ${mons[n.getMonth()]} ${n.getFullYear()}`, "ok");
	}

	// ------------------------------------------------------------ load
	bind() {
		const $r = this.$root;
		$r.find(".agri-farm-edit").on("click", () => this.editFarm());
		$r.find(".agri-date").val(this.log.date).on("change", (e) => { this.log.date = e.target.value || ""; this.loadLog(true); });
		let t;
		$r.find(".agri-search").on("input", (e) => {
			clearTimeout(t);
			t = setTimeout(() => { this.log.search = e.target.value.trim(); this.loadLog(true); }, 400);
		});
		$r.find(".agri-more").on("click", () => this.loadLog(false));
		$r.find(".agri-clear").on("click", () => this.clearLog());

		$r.on("click", ".agri-btns button", (e) => {
			const $b = $(e.currentTarget);
			this.cmd(+$b.attr("data-i"), $b.attr("data-a"), $b);
		});
		$r.on("click", ".agri-sched", (e) => this.openSched(+$(e.currentTarget).attr("data-i")));
		$r.on("click", ".agri-rname, .agri-rloc", (e) => this.inlineEdit($(e.currentTarget)));

		frappe.realtime.on("agri_status", (s) => this.applyStatus(s));
		frappe.realtime.on("agri_heartbeat", (h) => this.applyHeartbeat(h));
		frappe.realtime.on("agri_broker", (b) => this.applyBroker(b));
		frappe.realtime.on("agri_log", (row) => this.liveLog(row));
	}

	refresh() {
		frappe.call("agri_control.api.get_dashboard_data").then((r) => {
			const d = r.message;
			this.data = d;
			this.relays = d.relays;
			this.$root.find(".agri-farm-name").text(d.farm_name);
			this.$root.find(".agri-farm-loc").text(d.farm_location);
			this.$root.find(".agri-clear").toggle(!!d.is_manager);
			const $w = this.$root.find(".agri-warn");
			if (!d.configured) {
				$w.html(__("MQTT broker is not set up yet. Open <a href='/app/agri-mqtt-settings'>Agri MQTT Settings</a>.")).show();
			} else $w.hide();
			this.buildGrid();
			this.applyStatus(d.status);
			this.applyHeartbeat(d.heartbeat);
			this.applyBroker(d.broker);
		});
		this.loadLog(true);
	}

	pollLive() {
		frappe.call({ method: "agri_control.api.get_live_state", type: "GET" }).then((r) => {
			const d = r.message || {};
			this.applyStatus(d.status);
			this.applyHeartbeat(d.heartbeat);
			this.applyBroker(d.broker);
		});
	}

	// ------------------------------------------------------------ status bar
	applyHeartbeat(h) {
		if (h === "online") this.badge("hb", __("Device: Online"), "ok");
		else this.badge("hb", __("Device: Offline"), "fail");
	}
	applyBroker(b) {
		if (!b) this.badge("broker", __("Listener: not running"), "fail");
		else if (b.connected) this.badge("broker", __("Broker: Connected"), "ok");
		else this.badge("broker", __("Broker: Disconnected"), "fail");
	}
	applyStatus(s) {
		if (!s || !s.relays) return;
		if (s.time) this.badge("time", `${__("Time")}: ${s.time}`);
		if (s.rssi) this.badge("rssi", `${__("Signal")}: ${s.rssi} dBm`);
		if (s.wifi) this.badge("wifi", `IP: ${s.wifi}`);
		s.relays.forEach((r) => {
			const $c = this.$root.find(`#agri-card-${r.id}`);
			if (!$c.length) return;
			const $b = $c.find(".agri-badge").attr("class", "agri-badge");
			$c.removeClass("active");
			if (r.manual) $b.addClass("s-manual").text(r.state ? __("MANUAL ON") : __("MANUAL OFF"));
			else if (r.state) $b.addClass("s-on").text(__("ON"));
			else $b.text(__("OFF"));
			$c.toggleClass("active", !!r.state);
		});
	}

	// ------------------------------------------------------------ grid
	buildGrid() {
		const cls = { Master: "master", Fogger: "fogger", Pulse: "" };
		this.$root.find(".agri-grid").html(this.relays.map((r) => `
			<div class="agri-card ${cls[r.type]}" id="agri-card-${r.index}">
				<div class="agri-top">
					<span class="agri-rnum">${this.esc(r.label)}</span>
					<span class="agri-rname" data-i="${r.index}" data-f="relay_name" title="${__("Click to rename")}">${this.esc(r.name)}</span>
				</div>
				<div class="agri-rloc" data-i="${r.index}" data-f="location" title="${__("Click to set location")}">
					${r.location ? this.esc(r.location) : `<span class="ph">+ ${__("location")}</span>`}</div>
				<span class="agri-badge s-unknown">--</span>
				<div class="agri-btns">
					<button class="ab-on" data-i="${r.index}" data-a="ON">ON</button>
					<button class="ab-off" data-i="${r.index}" data-a="OFF">OFF</button>
					<button class="ab-auto" data-i="${r.index}" data-a="AUTO">AUTO</button>
				</div>
				<button class="agri-sched" data-i="${r.index}">${__("Edit schedule")}</button>
				<div class="agri-sum" id="agri-sum-${r.index}">${this.esc(r.summary)}</div>
			</div>`).join(""));
	}

	inlineEdit($el) {
		const idx = +$el.attr("data-i"), field = $el.attr("data-f");
		const r = this.relays.find((x) => x.index === idx);
		const cur = field === "relay_name" ? r.name : r.location;
		const $in = $(`<input class="form-control agri-inline" maxlength="${field === "relay_name" ? 30 : 50}">`)
			.val(cur).attr("placeholder", field === "relay_name" ? __("Name") : __("Location / zone"));
		$el.hide().after($in);
		$in.trigger("focus").trigger("select");
		let done = false;
		const finish = (save) => {
			if (done) return; done = true;
			const val = $in.val().trim();
			$in.remove(); $el.show();
			if (!save || val === cur) return;
			frappe.call({ method: "agri_control.api.update_relay", args: { relay_index: idx, [field]: val } })
				.then((res) => {
					Object.assign(r, res.message);
					if (field === "relay_name") $el.text(r.name);
					else $el.html(r.location ? this.esc(r.location) : `<span class="ph">+ ${__("location")}</span>`);
					frappe.show_alert({ message: __("Saved"), indicator: "green" }, 2);
				});
		};
		$in.on("blur", () => finish(true)).on("keydown", (e) => {
			if (e.key === "Enter") finish(true);
			if (e.key === "Escape") finish(false);
		});
	}

	cmd(idx, action, $btn) {
		$btn.prop("disabled", true);
		frappe.call({ method: "agri_control.api.send_command", args: { relay_index: idx, action } })
			.then(() => frappe.show_alert({ message: __("R{0}: {1} sent", [idx + 1, action]), indicator: "blue" }, 3))
			.always(() => $btn.prop("disabled", false));
	}

	pushAll() {
		frappe.confirm(__("Send every relay schedule (R2–R14) to the device now?"), () => {
			frappe.call({ method: "agri_control.api.push_all_schedules", freeze: true })
				.then((r) => frappe.show_alert({ message: __("{0} schedules sent", [r.message.count]), indicator: "green" }));
		});
	}

	editFarm() {
		const d = new frappe.ui.Dialog({
			title: __("Farm settings"),
			fields: [
				{ fieldname: "farm_name", label: __("Farm / Site Name"), fieldtype: "Data", default: this.data.farm_name },
				{ fieldname: "farm_location", label: __("Location / Address"), fieldtype: "Data", default: this.data.farm_location },
			],
			primary_action_label: __("Save"),
			primary_action: (v) => {
				frappe.call({ method: "agri_control.api.save_farm_info", args: v }).then((r) => {
					Object.assign(this.data, r.message);
					this.$root.find(".agri-farm-name").text(r.message.farm_name);
					this.$root.find(".agri-farm-loc").text(r.message.farm_location);
					d.hide();
					frappe.show_alert({ message: __("Settings saved"), indicator: "green" });
				});
			},
		});
		d.show();
	}

	importOld() {
		const snippet = "copy(JSON.stringify({rn:localStorage.rn,rl:localStorage.rl,sd:localStorage.sd,agri_name:localStorage.agri_name,agri_loc:localStorage.agri_loc}))";
		const d = new frappe.ui.Dialog({
			title: __("Import from old web app"),
			fields: [
				{ fieldtype: "HTML", options: `<p>${__("Open the old Agri Controller page in the browser you used it in, press F12 → Console, paste this and press Enter. It copies the saved names, locations and schedules.")}</p>
					<pre style="white-space:pre-wrap;font-size:11px">${frappe.utils.escape_html(snippet)}</pre>
					<p>${__("Then paste the result below. This only updates ERPNext — the device already runs these schedules.")}</p>` },
				{ fieldname: "data", fieldtype: "Code", label: __("Copied data"), reqd: 1 },
			],
			primary_action_label: __("Import"),
			primary_action: (v) => {
				frappe.call({ method: "agri_control.api.import_old_app", args: { data: v.data }, freeze: true }).then((r) => {
					d.hide();
					frappe.show_alert({ message: __("Imported {0} relays", [r.message.updated]), indicator: "green" });
					this.refresh();
				});
			},
		});
		d.show();
	}

	// ------------------------------------------------------------ schedule dialog
	openSched(idx) {
		const r = this.relays.find((x) => x.index === idx);
		this.edit = JSON.parse(JSON.stringify(r.schedule));
		const isMaster = this.edit.type === "none";
		this.sd = new frappe.ui.Dialog({
			title: __("Edit schedule — {0} {1}", [r.label, r.name]),
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: isMaster ? null : __("Send to Device"),
			primary_action: isMaster ? null : () => this.saveSched(idx),
		});
		this.$sb = this.sd.fields_dict.body.$wrapper;
		this.renderSched();
		this.sd.show();
	}

	freqVal(dm) {
		if (dm == null || dm === AG_DAY_EVERY) return "127";
		if (dm === AG_DAY_WEEKDAYS) return "62";
		if (dm === AG_DAY_WEEKEND) return "65";
		return "-1";
	}

	renderSched() {
		const s = this.edit, $b = this.$sb;
		if (s.type === "none") {
			$b.html(`<p>${__("R1 Master turns ON automatically whenever any other relay is active. No schedule editing needed.")}</p>`);
			return;
		}
		if (s.type === "fogger") {
			$b.html(`
				<div class="ag-se">
					<div class="ag-r"><span class="ag-lbl" style="min-width:120px">${__("Active window")}</span>
						<input class="form-control ag-in" id="ag-fsh" type="number" min="0" max="23" value="${s.startH}"><span class="ag-lbl">:00 ${__("to")}</span>
						<input class="form-control ag-in" id="ag-feh" type="number" min="0" max="23" value="${s.endH}"><span class="ag-lbl">:00 (24h)</span></div>
					<div class="ag-r"><span class="ag-lbl" style="min-width:120px">${__("Pulse ON / min")}</span>
						<input class="form-control ag-in" id="ag-fps" type="number" min="1" max="55" value="${s.pulseS}"><span class="ag-lbl">${__("seconds")}</span></div>
					<p class="ag-note">${__("Fogger turns ON for the set seconds every minute within the active window.")}</p>
				</div>`);
			return;
		}
		s.entries = s.entries || [];
		const opt = (v, cur, t) => `<option value="${v}" ${cur === v ? "selected" : ""}>${t}</option>`;
		let html = s.entries.map((e, i) => {
			const h12 = e.h % 12 || 12, pm = e.h >= 12, dm = e.days == null ? AG_DAY_EVERY : e.days, fv = this.freqVal(dm);
			const toggles = AG_DAY_SHORT.map((c, b) =>
				`<button type="button" class="ag-dt ${(dm >> b) & 1 ? "active" : ""}" data-e="${i}" data-b="${b}" title="${AG_DAY_NAMES[b]}">${c}</button>`).join("");
			return `
			<div class="ag-se" data-e="${i}">
				<div class="ag-r">
					<input class="form-control ag-in ag-h" type="number" min="1" max="12" value="${h12}" aria-label="${__("Hour")}">
					<span class="ag-lbl">:</span>
					<input class="form-control ag-in ag-m" type="number" min="0" max="59" value="${String(e.m).padStart(2, "0")}" aria-label="${__("Minute")}">
					<select class="form-control ag-ap"><option ${pm ? "" : "selected"}>AM</option><option ${pm ? "selected" : ""}>PM</option></select>
					<span class="ag-lbl">${__("for")}</span>
					<input class="form-control ag-in ag-dur" type="number" min="1" max="180" value="${e.dur}" aria-label="${__("Minutes")}">
					<span class="ag-lbl">${__("min")}</span>
					<button type="button" class="btn btn-xs btn-danger ag-del" data-e="${i}" aria-label="${__("Remove slot")}">✕</button>
				</div>
				<div class="ag-r">
					<span class="ag-lbl">${__("Days")}:</span>
					<select class="form-control ag-freq" data-e="${i}">
						${opt("127", fv, __("Every day"))}${opt("62", fv, __("Weekdays (Mon–Fri)"))}${opt("65", fv, __("Weekend (Sat–Sun)"))}${opt("-1", fv, __("Custom…"))}
					</select>
					<div class="ag-days" style="display:${fv === "-1" ? "flex" : "none"}">${toggles}</div>
				</div>
			</div>`;
		}).join("");
		html += s.entries.length < 6
			? `<button type="button" class="btn btn-default btn-sm ag-add">+ ${__("Add time slot")}</button>`
			: `<p class="ag-note">${__("The controller holds at most 6 slots per relay.")}</p>`;
		$b.html(html);

		$b.find(".ag-add").on("click", () => { this.readSched(); s.entries.push({ h: 6, m: 0, dur: 5, days: AG_DAY_EVERY }); this.renderSched(); });
		$b.find(".ag-del").on("click", (e) => { this.readSched(); s.entries.splice(+$(e.currentTarget).attr("data-e"), 1); this.renderSched(); });
		$b.find(".ag-dt").on("click", (e) => $(e.currentTarget).toggleClass("active"));
		$b.find(".ag-freq").on("change", (e) => {
			const $days = $(e.currentTarget).siblings(".ag-days");
			if (e.currentTarget.value === "-1") {
				$days.css("display", "flex").find(".ag-dt").each((b, el) => $(el).toggleClass("active", b >= 1 && b <= 5));
			} else $days.hide();
		});
	}

	readSched() {
		const s = this.edit, $b = this.$sb;
		const clamp = (v, lo, hi, d) => { v = parseInt(v, 10); return isNaN(v) ? d : Math.min(hi, Math.max(lo, v)); };
		if (s.type === "fogger") {
			s.startH = clamp($b.find("#ag-fsh").val(), 0, 23, 9);
			s.endH = clamp($b.find("#ag-feh").val(), 0, 23, 21);
			s.pulseS = clamp($b.find("#ag-fps").val(), 1, 55, 9);
			return;
		}
		$b.find(".ag-se").each((i, el) => {
			const $e = $(el), e = s.entries[i];
			const h = clamp($e.find(".ag-h").val(), 1, 12, 12), pm = $e.find(".ag-ap").val() === "PM";
			e.h = pm ? (h === 12 ? 12 : h + 12) : (h === 12 ? 0 : h);
			e.m = clamp($e.find(".ag-m").val(), 0, 59, 0);
			e.dur = clamp($e.find(".ag-dur").val(), 1, 180, 5);
			const fv = parseInt($e.find(".ag-freq").val(), 10);
			if (fv !== -1) e.days = fv;
			else {
				let mask = 0;
				$e.find(".ag-dt").each((b, d) => { if ($(d).hasClass("active")) mask |= 1 << b; });
				e.days = mask || AG_DAY_EVERY;
			}
		});
	}

	saveSched(idx) {
		this.readSched();
		frappe.call({
			method: "agri_control.api.save_schedule",
			args: { relay_index: idx, schedule: JSON.stringify(this.edit) },
			freeze: true,
		}).then((r) => {
			const m = r.message, rel = this.relays.find((x) => x.index === idx);
			Object.assign(rel, m.relay);
			this.$root.find(`#agri-sum-${idx}`).text(rel.summary);
			this.sd.hide();
			if (m.sent) frappe.show_alert({ message: __("Schedule saved and sent to device"), indicator: "green" });
			else frappe.show_alert({ message: __("Saved in ERPNext — could not reach device: {0}", [m.error || ""]), indicator: "orange" }, 8);
		});
	}

	// ------------------------------------------------------------ log
	logEntry(e, fresh) {
		const src = (e.source || "Device").toLowerCase();
		const who = e.user && e.source === "User" ? `<span class="agri-lu">${this.esc(frappe.user.full_name(e.user))}</span>` : "";
		return `<div class="agri-le ${src} ${fresh ? "fresh" : ""}"><span class="agri-lt">${this.fmtTime(e.event_time)}</span>
			<span class="agri-lm">${this.esc(e.message)}</span>${who}</div>`;
	}

	loadLog(reset) {
		const l = this.log, $list = this.$root.find(".agri-log");
		if (reset) l.offset = 0;
		frappe.call({
			method: "agri_control.api.get_log", type: "GET",
			args: { limit: l.limit, offset: l.offset, search: l.search || null, date: l.date || null },
		}).then((r) => {
			const d = r.message;
			if (reset) $list.empty();
			$list.append(d.items.map((e) => this.logEntry(e)).join(""));
			l.offset += d.items.length;
			l.total = d.total;
			if (!$list.children().length) {
				$list.html(`<div class="agri-empty">${l.search || l.date ? __("No events for this date or search.") : __("No events yet. They appear here as the device reports them.")}</div>`);
			}
			this.updateCount();
			this.$root.find(".agri-more").toggle(!!d.hasMore);
		}, () => this.$root.find(".agri-count").text(__("Could not load log")));
	}

	updateCount() {
		const n = this.$root.find(".agri-log .agri-le").length;
		this.$root.find(".agri-count").text(__("{0} / {1} entries", [n, this.log.total]));
	}

	liveLog(row) {
		const l = this.log;
		const today = frappe.datetime.get_today();
		if (l.date && l.date !== today) return;
		if (l.search && !(row.message || "").toLowerCase().includes(l.search.toLowerCase())) return;
		const $list = this.$root.find(".agri-log");
		$list.find(".agri-empty").remove();
		$list.prepend(this.logEntry(row, true));
		l.total += 1; l.offset += 1;
		this.updateCount();
	}

	clearLog() {
		frappe.confirm(__("Clear all log entries from the database?"), () => {
			frappe.call({ method: "agri_control.api.clear_log" }).then(() => {
				frappe.show_alert({ message: __("Event log cleared"), indicator: "green" });
				this.loadLog(true);
			});
		});
	}
}
