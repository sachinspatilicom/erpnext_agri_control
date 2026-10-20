frappe.pages["agri-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Agri Control"),
		single_column: true,
	});
	wrapper.agri = new AgriDashboard(page);
};

frappe.pages["agri-dashboard"].on_page_show = function (wrapper) {
	wrapper.agri && wrapper.agri.refresh();
};

const AGRI_CSS = `
.agri { --agri-on: #3d8b37; --agri-on-soft: rgba(61,139,55,.12); --agri-warn: #b7791f; --agri-err: #c0392b;
	display: grid; gap: 20px; padding-bottom: 32px; }
.agri-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 28px;
	padding: 14px 18px; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; }
.agri-ctrl { display: flex; align-items: center; gap: 10px; font-weight: 600; }
.agri-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--gray-400); flex: none; }
.agri-ctrl.online .agri-dot { background: var(--agri-on); box-shadow: 0 0 0 4px var(--agri-on-soft); }
.agri-ctrl.offline .agri-dot { background: var(--agri-err); }
.agri-muted { color: var(--text-muted); font-weight: 400; font-size: var(--text-sm); }
.agri-readings { display: flex; flex-wrap: wrap; gap: 6px 22px; }
.agri-reading b { font-size: var(--text-lg); font-variant-numeric: tabular-nums; }
.agri-reading span { color: var(--text-muted); font-size: var(--text-sm); margin-left: 4px; }
.agri-h { font-size: var(--text-lg); font-weight: 600; margin: 4px 0 10px; }
.agri-relays { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
.agri-relay { position: relative; display: grid; gap: 12px; padding: 14px 16px 14px 22px;
	background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }
.agri-relay::before { content: ""; position: absolute; inset: 0 auto 0 0; width: 6px; background: var(--gray-300);
	transition: background .25s; }
.agri-relay.on { background: linear-gradient(90deg, var(--agri-on-soft), transparent 70%), var(--card-bg); }
.agri-relay.on::before { background: var(--agri-on); }
.agri-relay.disabled { opacity: .55; }
.agri-relay-top { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.agri-relay-name { font-weight: 600; font-size: var(--text-md); }
.agri-relay-idx { color: var(--text-muted); font-size: var(--text-sm); font-variant-numeric: tabular-nums; white-space: nowrap; }
.agri-state { font-size: 22px; font-weight: 700; letter-spacing: .02em; color: var(--text-muted); }
.agri-relay.on .agri-state { color: var(--agri-on); }
.agri-relay-btns { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.agri-relay-btns .btn { font-weight: 600; }
.agri-relay.on .agri-btn-on, .agri-relay.off .agri-btn-off { outline: 2px solid var(--text-color); outline-offset: -2px; }
.agri-empty { padding: 28px; text-align: center; color: var(--text-muted);
	border: 1px dashed var(--border-color); border-radius: 10px; }
.agri-log-tools { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.agri-log-tools input[type=search] { flex: 1 1 220px; }
.agri-log-tools input[type=date] { flex: 0 0 170px; }
.agri-log { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }
.agri-log-row { display: grid; grid-template-columns: 150px 70px 1fr; gap: 12px; padding: 8px 14px;
	border-top: 1px solid var(--border-color); border-left: 4px solid transparent; font-size: var(--text-sm); }
.agri-log-row:first-child { border-top: 0; }
.agri-log-row.Warning { border-left-color: var(--agri-warn); }
.agri-log-row.Error { border-left-color: var(--agri-err); }
.agri-log-row.fresh { animation: agri-fresh 1.6s ease-out; }
@keyframes agri-fresh { from { background: var(--agri-on-soft); } to { background: transparent; } }
.agri-log-time { color: var(--text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.agri-log-src { color: var(--text-muted); }
.agri-log-msg { word-break: break-word; }
.agri-pager { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; }
@media (max-width: 600px) {
	.agri-log-row { grid-template-columns: 1fr; gap: 2px; }
	.agri-relays { grid-template-columns: 1fr 1fr; }
	.agri-state { font-size: 18px; }
}
@media (prefers-reduced-motion: reduce) {
	.agri-relay::before { transition: none; }
	.agri-log-row.fresh { animation: none; }
}`;

class AgriDashboard {
	constructor(page) {
		this.page = page;
		this.relays = [];
		this.status = null;
		this.heartbeat = null;
		this.hbTimeout = 90;
		this.clockOffset = 0;
		this.log = { limit: 50, offset: 0, total: 0, search: "", date: "" };

		frappe.dom.set_style(AGRI_CSS, "agri-dashboard-css");
		this.page.set_primary_action(__("Send all schedules"), () => this.pushAll(), "upload");
		this.page.add_menu_item(__("Edit relays"), () => frappe.set_route("List", "Relay Config"));
		this.page.add_menu_item(__("Edit schedules"), () => frappe.set_route("List", "Relay Schedule"));
		this.page.add_menu_item(__("MQTT settings"), () => frappe.set_route("Form", "Agri MQTT Settings"));

		this.$root = $(`
			<div class="agri">
				<div class="agri-strip">
					<div class="agri-ctrl"><span class="agri-dot"></span><span class="agri-ctrl-text">${__("Connecting...")}</span></div>
					<div class="agri-readings"></div>
				</div>
				<section>
					<div class="agri-h">${__("Relays")}</div>
					<div class="agri-relays"></div>
				</section>
				<section>
					<div class="agri-h">${__("Event log")}</div>
					<div class="agri-log-tools">
						<input type="search" class="form-control agri-search" placeholder="${__("Search messages")}">
						<input type="date" class="form-control agri-date" aria-label="${__("Filter by date")}">
					</div>
					<div class="agri-log"></div>
					<div class="agri-pager">
						<span class="agri-muted agri-count"></span>
						<div>
							<button class="btn btn-default btn-sm agri-prev">${__("Newer")}</button>
							<button class="btn btn-default btn-sm agri-next">${__("Older")}</button>
						</div>
					</div>
				</section>
			</div>`).appendTo(this.page.main);

		this.bindEvents();
		this.bindRealtime();
		this.refresh();
		this.timer = setInterval(() => this.renderController(), 5000);
	}

	bindEvents() {
		const reload = frappe.utils.debounce(() => { this.log.offset = 0; this.loadLog(); }, 350);
		this.$root.find(".agri-search").on("input", (e) => { this.log.search = e.target.value; reload(); });
		this.$root.find(".agri-date").on("change", (e) => { this.log.date = e.target.value; reload(); });
		this.$root.find(".agri-prev").on("click", () => {
			this.log.offset = Math.max(0, this.log.offset - this.log.limit); this.loadLog();
		});
		this.$root.find(".agri-next").on("click", () => {
			this.log.offset += this.log.limit; this.loadLog();
		});
		this.$root.on("click", ".agri-relay-btns .btn", (e) => {
			const $b = $(e.currentTarget);
			this.sendCommand($b.attr("data-relay"), $b.attr("data-action"), $b);
		});
	}

	bindRealtime() {
		frappe.realtime.on("agri_status", (data) => { this.status = data; this.renderRelays(); this.renderReadings(); });
		frappe.realtime.on("agri_heartbeat", (data) => { this.heartbeat = data; this.renderController(); });
		frappe.realtime.on("agri_log", (row) => this.prependLog(row));
	}

	refresh() {
		frappe.call("agri_control.api.get_dashboard_data").then((r) => {
			const d = r.message || {};
			this.relays = d.relays || [];
			this.status = d.status;
			this.heartbeat = d.heartbeat;
			this.hbTimeout = d.heartbeat_timeout || 90;
			if (d.server_time) this.clockOffset = Date.now() - this.parse(d.server_time);
			this.renderController();
			this.renderReadings();
			this.renderRelays();
		});
		this.loadLog();
	}

	parse(dt) { return frappe.datetime.str_to_obj(dt).getTime(); }

	// ---------------------------------------------------------------- controller strip
	renderController() {
		const $c = this.$root.find(".agri-ctrl").removeClass("online offline");
		const $t = $c.find(".agri-ctrl-text");
		if (!this.heartbeat || !this.heartbeat.ts) {
			$c.addClass("offline");
			$t.html(`${__("Controller offline")} <span class="agri-muted">${__("no heartbeat received yet")}</span>`);
			return;
		}
		const age = Math.max(0, Math.round((Date.now() - this.clockOffset - this.parse(this.heartbeat.ts)) / 1000));
		const online = age <= this.hbTimeout;
		$c.addClass(online ? "online" : "offline");
		$t.html(`${online ? __("Controller online") : __("Controller offline")}
			<span class="agri-muted">${__("last heartbeat {0} ago", [this.ago(age)])}</span>`);
	}

	ago(s) {
		if (s < 60) return `${s}s`;
		if (s < 3600) return `${Math.floor(s / 60)}m`;
		if (s < 86400) return `${Math.floor(s / 3600)}h`;
		return `${Math.floor(s / 86400)}d`;
	}

	renderReadings() {
		const extra = (this.status && this.status.extra) || {};
		const labels = { temp: "°C", temperature: "°C", t: "°C", hum: "% RH", humidity: "% RH", h: "% RH" };
		const html = Object.keys(extra).map((k) => {
			const unit = labels[k.toLowerCase()];
			const name = unit ? (unit === "°C" ? __("Temperature") : __("Humidity")) : k;
			return `<div class="agri-reading"><b>${frappe.utils.escape_html(String(extra[k]))}${unit || ""}</b>
				<span>${frappe.utils.escape_html(name)}</span></div>`;
		}).join("");
		this.$root.find(".agri-readings").html(html);
	}

	// ---------------------------------------------------------------- relays
	renderRelays() {
		const $grid = this.$root.find(".agri-relays");
		if (!this.relays.length) {
			$grid.html(`<div class="agri-empty" style="grid-column:1/-1">
				${__("No relays set up yet.")}
				<div style="margin-top:10px"><a class="btn btn-primary btn-sm" href="/app/relay-config/new">${__("Add relay")}</a></div></div>`);
			return;
		}
		const states = (this.status && this.status.relays) || {};
		$grid.html(this.relays.map((r) => {
			const s = states[String(r.relay_index)];
			const cls = s === true ? "on" : s === false ? "off" : "unknown";
			const label = s === true ? __("ON") : s === false ? __("OFF") : __("Unknown");
			const esc = frappe.utils.escape_html;
			const dis = r.enabled ? "" : "disabled";
			return `<div class="agri-relay ${cls} ${r.enabled ? "" : "disabled"}">
				<div class="agri-relay-top">
					<div>
						<div class="agri-relay-name">${esc(r.relay_name)}</div>
						<div class="agri-muted">${esc(r.location || "")}</div>
					</div>
					<span class="agri-relay-idx">${__("Relay {0}", [r.relay_index])}</span>
				</div>
				<div class="agri-state">${label}</div>
				<div class="agri-relay-btns">
					<button class="btn btn-default btn-sm agri-btn-on" data-relay="${esc(r.name)}" data-action="ON" ${dis}>${__("Turn on")}</button>
					<button class="btn btn-default btn-sm agri-btn-off" data-relay="${esc(r.name)}" data-action="OFF" ${dis}>${__("Turn off")}</button>
				</div>
			</div>`;
		}).join(""));
	}

	sendCommand(relay, action, $btn) {
		$btn.prop("disabled", true);
		frappe.call({ method: "agri_control.api.send_command", args: { relay, action } })
			.then(() => frappe.show_alert({
				message: __("{0}: {1} sent. Waiting for the controller to confirm.", [relay, action]),
				indicator: "blue",
			}, 4))
			.always(() => $btn.prop("disabled", false));
	}

	pushAll() {
		frappe.confirm(__("Send every relay schedule to the controller now?"), () => {
			frappe.call({ method: "agri_control.api.push_all_schedules", freeze: true })
				.then((r) => frappe.show_alert({
					message: __("{0} schedules sent", [(r.message || {}).count || 0]), indicator: "green",
				}));
		});
	}

	// ---------------------------------------------------------------- log
	loadLog() {
		const l = this.log;
		frappe.call("agri_control.api.get_log", {
			limit: l.limit, offset: l.offset, search: l.search || null, date: l.date || null,
		}).then((r) => {
			const d = r.message || { rows: [], total: 0 };
			l.total = d.total;
			const $log = this.$root.find(".agri-log");
			$log.html(d.rows.length ? d.rows.map((row) => this.logRow(row)).join("")
				: `<div class="agri-empty" style="border:0">${l.search || l.date ? __("No events match this filter.") : __("No events yet. They appear here as the controller reports them.")}</div>`);
			const from = d.total ? l.offset + 1 : 0;
			const to = Math.min(l.offset + l.limit, d.total);
			this.$root.find(".agri-count").text(__("{0}–{1} of {2}", [from, to, d.total]));
			this.$root.find(".agri-prev").prop("disabled", l.offset === 0);
			this.$root.find(".agri-next").prop("disabled", to >= d.total);
		});
	}

	logRow(row, fresh) {
		const esc = frappe.utils.escape_html;
		return `<div class="agri-log-row ${esc(row.level || "Info")} ${fresh ? "fresh" : ""}">
			<span class="agri-log-time">${frappe.datetime.str_to_user(row.event_time)}</span>
			<span class="agri-log-src">${esc(__(row.source || ""))}</span>
			<span class="agri-log-msg">${esc(row.message || "")}</span>
		</div>`;
	}

	prependLog(row) {
		const l = this.log;
		if (l.offset !== 0 || l.search || l.date) return; // don't disturb a filtered/paged view
		const $log = this.$root.find(".agri-log");
		$log.find(".agri-empty").remove();
		$log.prepend(this.logRow(row, true));
		$log.children().slice(l.limit).remove();
		l.total += 1;
		this.$root.find(".agri-count").text(__("{0}–{1} of {2}", [1, Math.min(l.limit, l.total), l.total]));
	}
}
