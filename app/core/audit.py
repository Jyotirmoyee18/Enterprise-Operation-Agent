import json
from app.core.db import connection

def audit(event_type: str, actor: str, details: dict, request_id: str | None = None):
    with connection() as c:
        c.execute("INSERT INTO audit_events(event_type,actor,request_id,details) VALUES (%s,%s,%s,%s::jsonb)",
                  (event_type, actor, request_id, json.dumps(details, default=str)))
