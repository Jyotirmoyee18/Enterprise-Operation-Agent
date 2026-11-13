import pytest
from app.connectors.sap_odata import SAPODataConnector, SAPConnectorError
from app.core.config import settings

def test_real_sap_write_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "sap_mode", "odata")
    with pytest.raises(SAPConnectorError):
        SAPODataConnector().write("CREATE_PURCHASE_ORDER", {"supplier_id":"SUP-1","amount":10})
