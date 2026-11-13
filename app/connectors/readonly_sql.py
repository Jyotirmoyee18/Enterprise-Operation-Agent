import re
from app.core.db import connection

_ALLOWED = {"v_open_purchase_orders"}
_BLOCKED = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|copy|call|execute|vacuum|analyze)\b", re.I)

def validate_query(query: str) -> str:
    q = query.strip()
    if not q or len(q) > 2000: raise ValueError("Query is empty or too long")
    if ";" in q.rstrip(";"): raise ValueError("Only one SQL statement is allowed")
    if _BLOCKED.search(q): raise ValueError("Only read-only SELECT statements are allowed")
    if not re.match(r"^(select|with)\b", q, re.I): raise ValueError("Only SELECT queries are allowed")
    refs = set(re.findall(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)", q, re.I))
    if not refs or any(ref.split(".")[-1].lower() not in _ALLOWED for ref in refs):
        raise ValueError("Query may only read from approved views: v_open_purchase_orders")
    if re.search(r"\b(pg_|information_schema|pg_catalog)\b", q, re.I):
        raise ValueError("System catalog access is not permitted")
    return q.rstrip(";")

def run_readonly(query: str):
    q = validate_query(query)
    # Enforce read-only at the database transaction level as a second control.
    with connection() as c:
        c.execute("SET TRANSACTION READ ONLY")
        return [dict(row) for row in c.execute(q).fetchall()]
