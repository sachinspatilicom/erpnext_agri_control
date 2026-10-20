import frappe
from frappe.model.document import Document


class AgriMQTTSettings(Document):
    def validate(self):
        self.topic_prefix = (self.topic_prefix or "agri").strip().strip("/")
        if not (0 < (self.broker_port or 0) < 65536):
            frappe.throw("Broker Port must be between 1 and 65535")
        if (self.heartbeat_timeout_sec or 0) < 10:
            self.heartbeat_timeout_sec = 90
        if (self.log_retention_days or 0) < 0:
            self.log_retention_days = 0

    def on_update(self):
        frappe.msgprint(
            "Saved. Restart the MQTT listener (sudo supervisorctl restart agri-mqtt) "
            "for broker changes to take effect.",
            indicator="blue", alert=True,
        )
