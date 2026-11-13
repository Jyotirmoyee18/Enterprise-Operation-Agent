from app.core.policy import classify, is_write_intent

def test_write_intent_routes_to_write():
    assert classify("Create a purchase order for SUP-1001 for INR 125000") == "write"

def test_policy_question_routes_to_rag():
    assert classify("What approval is required by purchase order policy?") == "rag"

def test_open_orders_routes_to_sql():
    assert classify("Show open purchase orders") == "sql"
