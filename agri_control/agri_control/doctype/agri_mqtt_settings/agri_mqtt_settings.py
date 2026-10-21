import frappe
from frappe.model.document import Document


class AgriMQTTSettings(Document):
    def validate(self):
        self.topic_prefix = (self.topic_prefix or "agri").strip().strip("/")
        self.broker_host = (self.broker_host or "").strip()
        if not (0 < (self.broker_port or 0) < 65536):
            frappe.throw("Broker Port must be between 1 and 65535")
        if (self.log_retention_days or 0) < 0:
            self.log_retention_days = 0
        self.farm_name = (self.farm_name or "Agri Controller").strip()

    def on_update(self):
        if self.has_value_changed("broker_host") or self.has_value_changed("topic_prefix") \
                or self.has_value_changed("username") or self.has_value_changed("broker_port"):
            frappe.msgprint(
                "Broker settings changed. Restart the MQTT listener for them to take effect: "
                "<code>sudo supervisorctl restart agri-mqtt</code>",
                indicator="blue", alert=True,
            )
