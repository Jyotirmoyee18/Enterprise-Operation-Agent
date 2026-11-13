import uuid
import requests
from app.core.config import settings

class SAPConnectorError(RuntimeError): pass

class SAPODataConnector:
    def read(self, entity: str, params: dict | None = None):
        if settings.sap_mode == "mock":
            if entity != "PurchaseOrders": raise SAPConnectorError("Entity is not available in mock adapter")
            return {"value": [{"PurchaseOrder":"4500001001","Supplier":"SUP-1001","Status":"OPEN","Amount":"125000.00","Currency":"INR"}]}
        if settings.sap_mode != "odata" or not settings.sap_odata_base_url or not settings.sap_bearer_token:
            raise SAPConnectorError("SAP connector is not configured; failing closed")
        url = settings.sap_odata_base_url.rstrip("/") + "/" + entity
        response = requests.get(url, params=params or {}, headers={"Authorization":f"Bearer {settings.sap_bearer_token}","Accept":"application/json"}, timeout=15)
        response.raise_for_status()
        return response.json()

    def write(self, action_type: str, payload: dict):
        if settings.sap_mode == "mock":
            return {"mock": True, "document_id": f"MOCK-{uuid.uuid4().hex[:10].upper()}",
                    "action_type": action_type, "accepted_payload": payload}
        # Real SAP writes are deliberately disabled until tenant-specific CSRF,
        # OAuth refresh, entity allowlisting and idempotency are implemented.
        raise SAPConnectorError("Real SAP writes are disabled. Complete tenant-specific CSRF/auth integration first.")
