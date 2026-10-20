frappe.ui.form.on("Agri MQTT Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Test Connection"), () => {
			frappe.call({
				method: "agri_control.api.test_connection",
				freeze: true,
				freeze_message: __("Connecting to broker..."),
				callback: (r) => {
					if (r.message) {
						frappe.msgprint({ title: __("MQTT"), indicator: "green", message: r.message });
					}
				},
			});
		});
		frm.add_custom_button(__("Open Dashboard"), () => frappe.set_route("agri-dashboard"));
	},
});
