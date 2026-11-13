# Enterprise Operations Agent

A production-oriented reference MVP for enterprise operations workflows using **LangGraph, RAG, MCP, PostgreSQL/pgvector, read-only SQL, SAP OData, human approval gates, audit logging, and OpenTelemetry**.

> **Safety default:** the application starts in `SAP_MODE=mock`. SAP write operations are never executed directly by the agent. The agent can only create a pending action; an authenticated approver must approve it. The included mock adapter makes the full workflow testable without SAP credentials.

## What it does

- Routes user requests through a LangGraph state machine.
- Retrieves grounded context from a PostgreSQL/pgvector knowledge base.
- Exposes a restricted, read-only SQL interface.
- Calls SAP OData through a fail-closed connector (mock by default).
- Creates pending approval records for write-intent requests.
- Requires explicit approval before executing a write action.
- Records append-only audit events for user requests, tool calls, approvals, rejections, and execution outcomes.
- Emits OpenTelemetry traces and structured application logs.
- Exposes read-only RAG and SQL tools through an MCP server.

## Architecture at a glance

```text
                 ┌──────────────────────────────┐
 User / Client ─▶│ FastAPI REST API              │
                 │ /chat /knowledge /approvals   │
                 └──────────────┬───────────────┘
                                │
                         LangGraph workflow
                                │
                ┌───────────────┼────────────────┐
                ▼               ▼                ▼
             RAG node       SQL node        SAP OData node
          pgvector search  read-only SQL    read-only query
                │               │                │
                └───────────────┼────────────────┘
                                ▼
                     Policy / approval gate
                                │
                     Pending approval record
                                │
                       Human approver
                                │
                       SAP write adapter
                     (mock or configured OData)
                                │
                     Audit + OpenTelemetry

 MCP client ─▶ MCP server ─▶ read-only RAG / SQL tools
```

## Quick start (Docker)

Requirements: Docker Desktop / Docker Engine with Compose.

```bash
git clone <your-repository-url>
cd enterprise-operations-agent
cp .env.example .env
docker compose up --build
```

Services:
- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Health: http://localhost:8000/health
- Jaeger UI: http://localhost:16686
-Dashboard: http://localhost:8000/

The first embedding request downloads `sentence-transformers/all-MiniLM-L6-v2` into the model cache. For a fully offline environment, pre-populate the Hugging Face cache and set `HF_HUB_OFFLINE=1`.

## Quick start (local Python)

Python 3.11 is recommended.

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
docker compose up -d db jaeger
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Run the MCP server in a second terminal:

```powershell
.venv\Scripts\activate
python -m app.mcp_server
```

## End-to-end walkthrough

### 1. Check service health

```bash
curl http://localhost:8000/health
```

### 2. Ingest a knowledge document

```bash
curl -X POST http://localhost:8000/knowledge \
  -H "Content-Type: application/json" \
  -d '{"title":"Purchase order policy","source":"policy-demo","text":"Purchase orders above INR 500000 require finance approval. A purchase order must reference a valid supplier and company code."}'
```

### 3. Ask a RAG question

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo.user","message":"What approval is required for purchase orders above INR 500000?"}'
```

### 4. Ask for read-only SQL

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo.user","message":"Show the open purchase orders"}'
```

The demo database is seeded with synthetic purchase-order records. SQL access is restricted to a fixed set of views and SELECT statements.

### 5. Request a write action

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id":"demo.user","message":"Create a purchase order for supplier SUP-1001 for INR 125000"}'
```

The response includes `approval_id` and `status: pending_approval`. No write occurs yet.

### 6. Approve or reject

For this MVP, set `APPROVER_API_KEY` in `.env` and pass it as `X-Approver-Key`.

```bash
curl -X POST http://localhost:8000/approvals/<APPROVAL_ID>/approve \
  -H "X-Approver-Key: change-me-approver-key"
```

Or reject:

```bash
curl -X POST http://localhost:8000/approvals/<APPROVAL_ID>/reject \
  -H "X-Approver-Key: change-me-approver-key" \
  -H "Content-Type: application/json" \
  -d '{"reason":"Incorrect supplier"}'
```

Inspect approvals:

```bash
curl -H "X-Approver-Key: change-me-approver-key" http://localhost:8000/approvals
```

## API reference

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Liveness and dependency health |
| POST | `/chat` | Run a LangGraph request |
| POST | `/knowledge` | Chunk, embed, and index a document |
| GET | `/knowledge/search?q=...` | Search indexed knowledge |
| GET | `/approvals` | List pending/recent approval records (approver key) |
| POST | `/approvals/{id}/approve` | Approve and execute a pending action |
| POST | `/approvals/{id}/reject` | Reject a pending action |
| GET | `/audit` | Read audit events (approver key) |

Full interactive schemas are available at `/docs`.

## Configuration

See `.env.example`. Important settings:

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | local Postgres | PostgreSQL connection |
| `SAP_MODE` | `mock` | `mock` or `odata` |
| `SAP_ODATA_BASE_URL` | empty | SAP OData service root |
| `SAP_BEARER_TOKEN` | empty | SAP OAuth bearer token |
| `APPROVER_API_KEY` | demo key | MVP approver authentication |
| `EMBEDDING_MODEL` | MiniLM | Sentence-transformer model |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Jaeger | OTLP endpoint |

### Connecting a real SAP system

1. Set `SAP_MODE=odata`.
2. Configure `SAP_ODATA_BASE_URL` to the exact OData service root.
3. Supply a short-lived OAuth bearer token through your secrets manager as `SAP_BEARER_TOKEN`.
4. Set `SAP_ALLOWED_WRITE_ENTITY` to the exact entity set your integration team has approved.
5. Implement and test the customer-specific CSRF-token and authentication flow in `app/connectors/sap_odata.py` before enabling writes.

The reference OData adapter intentionally **fails closed for writes** until the deployment-specific CSRF/authentication implementation is completed. Read-only requests use the configured bearer token. Do not put production credentials in source control or `.env` files.

## MCP

The stdio MCP server exposes only:
- `search_knowledge(query, top_k)` — read-only RAG search.
- `run_readonly_sql(query)` — constrained read-only SQL.

Run `python -m app.mcp_server` for an MCP stdio process. Configure the MCP client to launch it in the project directory with the same environment variables. The MCP server does not expose approval or write tools.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The tests cover write-intent routing, SQL read-only enforcement, approval state transitions, and fail-closed SAP writes.

## Production hardening checklist

This is a production-oriented MVP, not a certification that a deployment is production-ready. Before a real enterprise rollout:

- Replace the demo API-key approver with corporate OIDC/SSO, RBAC, and approver group mapping.
- Store secrets in a vault; use short-lived OAuth tokens and rotation.
- Add tenant isolation, row-level authorization, data classification, retention, and encryption-at-rest policies.
- Add idempotency keys and an outbox for external writes; define retry and reconciliation semantics.
- Use a dedicated read-only database role and approved database views.
- Add prompt-injection defenses and source-level trust labels for retrieved documents.
- Add PII redaction, rate limits, request-size limits, and abuse monitoring.
- Pin and scan dependencies; add CI, SAST, DAST, container scanning, SBOM, and signed images.
- Configure TLS, ingress authentication, network policies, backups, restore drills, and SLO alerts.
- Run load, security, failure-injection, and SAP integration tests in a non-production tenant.

## Repository layout

```text
app/
  api/              REST routes and schemas
  connectors/       database, RAG, SQL, SAP OData
  graph/            LangGraph state and nodes
  core/             settings, telemetry, audit, policy
  main.py           FastAPI entry point
  mcp_server.py     read-only MCP server
tests/
docs/
  document.md       detailed architecture and design decisions
```

## License

Internal evaluation / starter reference. Add your organization's approved license before public distribution.


## Web dashboard

After starting the stack with `docker compose up --build -d`, open:

- Dashboard: http://localhost:8000/
- API docs: http://localhost:8000/docs
- Jaeger traces: http://localhost:16686

The dashboard is a live UI over the existing API. It includes an overview, agent workspace,
knowledge ingestion/search, human approval queue, audit trail and capability map. It does not
add capabilities that the backend does not implement. In particular, the SAP adapter defaults
to mock mode and real SAP writes remain disabled. See `docs/document.md` for security and
production-hardening requirements.

## Troubleshooting

- `RuntimeError: Directory '/srv/static' does not exist` — fixed: the Dockerfile now copies `static/` into the image. Rebuild with `docker compose up --build`.
- First run is slow: the embedding model (~90 MB) downloads in the background after start-up and is cached in the `hf-cache` volume.
- Dashboard approver key (default): `change-me-approver-key`.
- Full reset: `docker compose down -v` (also wipes the database volume).
