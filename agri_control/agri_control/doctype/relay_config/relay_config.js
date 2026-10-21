frappe.ui.form.on("Relay Config", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.relay_type === "Master") return;
		frm.add_custom_button(__("Send to Device"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Save first, then send."));
				return;
			}
			frappe.call({
				method: "agri_control.api.push_schedule",
				args: { relay_index: frm.doc.relay_index },
				freeze: true,
				freeze_message: __("Sending schedule..."),
				callback: () => {
					frappe.show_alert({ message: __("Schedule sent to device"), indicator: "green" });
					frm.reload_doc();
				},
			});
		}).addClass("btn-primary");
		frm.add_custom_button(__("Open Dashboard"), () => frappe.set_route("agri-dashboard"));
	},
});
