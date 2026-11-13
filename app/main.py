from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.api.schemas import ChatRequest, KnowledgeRequest, RejectRequest
from app.core.config import settings
from app.core.db import init_db, connection
from app.core.audit import audit
from app.core.telemetry import setup_telemetry, tracer
from app.graph.workflow import run_request
from app.connectors.rag import ingest, search
from app.connectors.sap_odata import SAPODataConnector
import json, uuid, threading, logging
from contextlib import asynccontextmanager

log = logging.getLogger("uvicorn.error")

setup_telemetry()
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _warm_embeddings():
    # Download/load the embedding model in the background so the first request is fast.
    try:
        from app.connectors.embeddings import embed
        embed("warm-up")
        log.info("Embedding model ready")
    except Exception as exc:
        log.warning("Embedding warm-up failed (will retry on first use): %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    threading.Thread(target=_warm_embeddings, daemon=True).start()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", description="Governed enterprise operations agent", lifespan=lifespan)
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", include_in_schema=False)
def dashboard():
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(404, "Dashboard not found; see /docs for the API")
    return FileResponse(index)

def approver_auth(x_approver_key: str | None = Header(default=None)):
    if not x_approver_key or x_approver_key != settings.approver_api_key:
        raise HTTPException(status_code=401, detail="Approver authentication required")

@app.get("/health")
def health():
    try:
        with connection() as c: c.execute("SELECT 1")
        return {"status":"ok","database":"ok","sap_mode":settings.sap_mode}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")

@app.post("/chat")
def chat(body: ChatRequest):
    with tracer().start_as_current_span("agent.request") as span:
        span.set_attribute("user.id", body.user_id)
        result = run_request(body.user_id, body.message)
        return {k:v for k,v in result.items() if k not in ("message","user_id","request_id")}

@app.post("/knowledge")
def add_knowledge(body: KnowledgeRequest):
    try:
        result = ingest(body.title, body.source, body.text)
        audit("knowledge_ingested","api",{"title":body.title,"source":body.source,**result})
        return {"status":"indexed",**result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/knowledge/search")
def knowledge_search(q: str, top_k: int = 5):
    if top_k < 1 or top_k > 20: raise HTTPException(400, "top_k must be between 1 and 20")
    return {"results":search(q,top_k)}

@app.get("/approvals", dependencies=[Depends(approver_auth)])
def list_approvals(status: str = "PENDING"):
    with connection() as c:
        rows=c.execute("SELECT id,requester,action_type,payload,status,created_at FROM approvals WHERE status=%s ORDER BY created_at DESC LIMIT 100",(status.upper(),)).fetchall()
    return {"approvals":[dict(r) for r in rows]}

@app.post("/approvals/{approval_id}/approve", dependencies=[Depends(approver_auth)])
def approve(approval_id: str, x_approver_id: str = Header(default="approver")):
    try: uuid.UUID(approval_id)
    except ValueError: raise HTTPException(400,"Invalid approval id")
    error = None
    result = None
    with connection() as c:
        row=c.execute("SELECT * FROM approvals WHERE id=%s FOR UPDATE",(approval_id,)).fetchone()
        if not row: raise HTTPException(404,"Approval not found")
        if row["status"] != "PENDING": raise HTTPException(409,f"Approval is {row['status']}")
        payload=row["payload"] if isinstance(row["payload"],dict) else json.loads(row["payload"])
        # Re-check policy at execution time. The adapter remains fail-closed for real SAP writes.
        if row["action_type"] != "CREATE_PURCHASE_ORDER" or payload.get("action") != "CREATE_PURCHASE_ORDER":
            raise HTTPException(403,"Action is not allowlisted")
        try:
            result=SAPODataConnector().write(row["action_type"],payload)
            if result.get("mock"):
                # Mock mode: reflect the "created" PO in the demo table so it shows up in SQL reads.
                c.execute("INSERT INTO purchase_orders(po_number,supplier_id,company_code,amount,currency,status) "
                          "VALUES (%s,%s,%s,%s,%s,'OPEN') ON CONFLICT DO NOTHING",
                          (result["document_id"],payload["supplier_id"],payload.get("company_code","IN01"),
                           payload["amount"],payload.get("currency","INR")))
            c.execute("UPDATE approvals SET status='EXECUTED',decided_at=now(),decided_by=%s,result=%s::jsonb WHERE id=%s",
                      (x_approver_id,json.dumps(result),approval_id))
        except Exception as exc:
            error = str(exc)
            c.execute("UPDATE approvals SET status='FAILED',decided_at=now(),decided_by=%s,result=%s::jsonb WHERE id=%s",
                      (x_approver_id,json.dumps({"error":error}),approval_id))
    # Raise only after the transaction has committed, otherwise the FAILED status would be rolled back.
    if error:
        audit("approval_failed",x_approver_id,{"approval_id":approval_id,"error":error})
        raise HTTPException(502,f"Execution failed closed: {error}")
    audit("approval_executed",x_approver_id,{"approval_id":approval_id,"result":result})
    return {"approval_id":approval_id,"status":"EXECUTED","result":result}

@app.post("/approvals/{approval_id}/reject", dependencies=[Depends(approver_auth)])
def reject(approval_id: str, body: RejectRequest, x_approver_id: str = Header(default="approver")):
    try: uuid.UUID(approval_id)
    except ValueError: raise HTTPException(400,"Invalid approval id")
    with connection() as c:
        row=c.execute("SELECT status FROM approvals WHERE id=%s FOR UPDATE",(approval_id,)).fetchone()
        if not row: raise HTTPException(404,"Approval not found")
        if row["status"] != "PENDING": raise HTTPException(409,f"Approval is {row['status']}")
        c.execute("UPDATE approvals SET status='REJECTED',decided_at=now(),decided_by=%s,result=%s::jsonb WHERE id=%s",
                  (x_approver_id,json.dumps({"reason":body.reason}),approval_id))
    audit("approval_rejected",x_approver_id,{"approval_id":approval_id,"reason":body.reason})
    return {"approval_id":approval_id,"status":"REJECTED"}

@app.get("/audit", dependencies=[Depends(approver_auth)])
def audit_log(limit: int = 100):
    if limit < 1 or limit > 500: raise HTTPException(400,"limit must be 1..500")
    with connection() as c:
        rows=c.execute("SELECT id,event_type,actor,request_id,details,created_at FROM audit_events ORDER BY id DESC LIMIT %s",(limit,)).fetchall()
    return {"events":[dict(r) for r in rows]}
