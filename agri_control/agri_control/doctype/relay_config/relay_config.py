import frappe
from frappe.model.document import Document


class RelayConfig(Document):
    def validate(self):
        if (self.relay_index or 0) < 1:
            frappe.throw("Relay Index must be 1 or higher")
