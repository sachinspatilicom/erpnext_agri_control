frappe.ui.form.on("Relay Schedule", {
	refresh(frm) {
		if (frm.is_new() || frm.is_dirty()) return;
		frm.add_custom_button(__("Send to Controller"), () => {
			frappe.call({
				method: "agri_control.api.push_schedule",
				args: { name: frm.doc.name },
				freeze: true,
				freeze_message: __("Sending schedule..."),
				callback: () => {
					frappe.show_alert({ message: __("Schedule sent"), indicator: "green" });
					frm.reload_doc();
				},
			});
		}).addClass("btn-primary");
	},
});
