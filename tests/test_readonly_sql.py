import pytest
from app.connectors.readonly_sql import validate_query

def test_approved_select():
    assert "v_open_purchase_orders" in validate_query("SELECT * FROM v_open_purchase_orders LIMIT 10")

@pytest.mark.parametrize("query", [
    "DELETE FROM v_open_purchase_orders",
    "SELECT * FROM users",
    "SELECT * FROM v_open_purchase_orders; DROP TABLE approvals",
    "SELECT * FROM information_schema.tables",
])
def test_unsafe_query_rejected(query):
    with pytest.raises(ValueError): validate_query(query)
