# Enterprise Operations Agent — Architecture & Engineering Design

## 1. Executive summary

The Enterprise Operations Agent is a governed orchestration layer for enterprise business operations. It accepts natural-language requests, determines the permitted execution path, retrieves policy context, queries approved operational data, reads SAP OData resources, and stages high-impact write actions for human approval.

The system is designed around a simple invariant:

**The model may propose and prepare an action; policy and a human approver control whether an external side effect can occur.**

The reference implementation uses LangGraph for explicit workflow control, PostgreSQL with pgvector for retrieval and workflow persistence, FastAPI for the service boundary, MCP for controlled tool interoperability, and OpenTelemetry for distributed tracing.

## 2. Goals and non-goals

### Goals
- Demonstrate an end-to-end agent workflow with auditable routing.
- Ground policy answers in indexed enterprise documents.
- Provide a constrained read-only SQL capability.
- Integrate an SAP OData read adapter.
- Require human approval for write actions.
- Make the default deployment runnable without SAP credentials.
- Provide clear extension points for enterprise identity, SAP authentication, and deployment controls.

### Non-goals
- Autonomous unrestricted SAP updates.
- Arbitrary SQL generation or unrestricted database access.
- Production identity federation out of the box.
- Guaranteed accuracy of natural-language intent classification.
- A claim of production certification or compliance.

## 3. System context

### Actors
1. **Business user** — submits a question or operational request.
2. **Agent API** — validates and orchestrates the request.
3. **LangGraph workflow** — selects a controlled path and carries state.
4. **Knowledge administrator** — ingests approved documents.
5. **Approver** — reviews staged actions and decides.
6. **SAP system** — external system of record, accessed through OData.
7. **Operations team** — monitors health, traces, logs, and audit events.

### Trust boundaries
- Client-to-API boundary: request validation and optional API authentication.
- Agent-to-data boundary: allowlisted views and parameterized application queries.
- Agent-to-SAP boundary: explicit connector configuration and fail-closed behavior.
- Proposal-to-execution boundary: approval record and approver authentication.
- MCP boundary: only read-only tools are published.

## 4. Logical architecture

```text
┌───────────────────────────┐
│ Web UI / API Consumer     │
└─────────────┬─────────────┘
              │ HTTPS + identity (deployment responsibility)
┌─────────────▼─────────────┐
│ FastAPI Service           │
│ Validation / API schemas  │
│ Request correlation       │
└─────────────┬─────────────┘
              │
┌─────────────▼─────────────┐
│ LangGraph StateGraph      │
│ route → capability node   │
└──────┬────────┬───────────┘
       │        │
  ┌────▼───┐ ┌──▼────────┐ ┌────────────────┐
  │ RAG    │ │ Read SQL  │ │ SAP OData Read │
  │ Node   │ │ Node      │ │ Node           │
  └────┬───┘ └──┬────────┘ └───────┬────────┘
       │        │                  │
       ▼        ▼                  ▼
 PostgreSQL  Approved view     SAP OData API
 + pgvector  (read-only)       (bearer token)
       │
       └──────────────┐
                      ▼
               Audit event store
                      ▲
                      │
 Write intent ─▶ Policy gate ─▶ Pending approval
                                      │
                               Approver decision
                                      │
                               SAP write adapter
                         mock enabled / real disabled
```

## 5. Request lifecycle

### 5.1 Request intake
`POST /chat` accepts `user_id` and `message`. Pydantic validates length and required fields. A request correlation ID is generated before the LangGraph invocation.

### 5.2 Routing
The router is a deterministic policy-first classifier in this MVP:
- Write verbs and business-object terms → `write`.
- Operational list/query terms → `sql`.
- Policy and explanatory terms → `rag`.
- Remaining SAP-oriented questions → `sap_read`.

This deterministic baseline makes the demo reproducible. In a production extension, an LLM may propose a route, but the policy engine must validate the proposed capability and arguments. The LLM must never be the authorization authority.

### 5.3 RAG path
1. Knowledge text is normalized and split into overlapping chunks.
2. Sentence Transformers creates 384-dimensional embeddings.
3. PostgreSQL stores content and vectors.
4. Similarity search uses cosine distance.
5. The response includes source title, source identifier, and relevance score.

Retrieved content is untrusted input. A production implementation should attach provenance, classification, tenant scope, and document ACL metadata to every chunk, and should never treat retrieved text as executable instructions.

### 5.4 SQL path
The reference SQL tool allows a single `SELECT`/`WITH` statement referencing only `v_open_purchase_orders`. It blocks common mutation keywords, multiple statements, system catalogs, and unapproved relations. The database transaction is set to read-only as defense in depth.

Production deployment must additionally:
- Connect with a database role that has SELECT grants only.
- Expose purpose-built views with row/tenant filtering.
- Apply query timeouts, row limits, and statement cost limits.
- Avoid allowing end users to supply raw SQL.

The demo graph maps natural-language list requests to a fixed approved query. It does not ask an LLM to compose SQL.

### 5.5 SAP OData path
The adapter supports:
- `mock`: deterministic local response for end-to-end testing.
- `odata`: configured bearer-token GET against a service root.

The real write method intentionally raises an error. SAP writes require customer-specific CSRF-token handling, OAuth token refresh, entity-set allowlisting, idempotency, payload validation, and integration tests. The approval endpoint therefore cannot accidentally turn on an unsafe generic OData POST.

## 6. Human-in-the-loop approval

A write-intent request is converted into a typed action proposal. The current demo supports a narrow purchase-order creation proposal requiring:
- Supplier ID in `SUP-*` form.
- Amount in INR.

If required data is absent, the system asks for details and creates no approval.

If valid:
1. A UUID approval record is inserted with status `PENDING`.
2. The requester receives the approval ID.
3. The approver authenticates using `X-Approver-Key`.
4. The API locks the record with `SELECT ... FOR UPDATE`.
5. The server revalidates action type and payload allowlisting.
6. The connector executes (mock only in this reference build).
7. The state transitions to `EXECUTED` or `FAILED`.
8. An audit event records the decision.

Allowed state transitions:

```text
PENDING ──approve + successful adapter──▶ EXECUTED
   │
   ├────approve + adapter failure────────▶ FAILED
   │
   └────reject───────────────────────────▶ REJECTED
```

Terminal states cannot be approved or rejected again. The database row lock prevents concurrent approvers from executing the same pending record at the same time. A production version should add a transactional outbox, external idempotency key propagation, and reconciliation for uncertain network outcomes.

## 7. MCP design

The MCP process publishes two tools:
- `search_knowledge`
- `run_readonly_sql`

No write, approval, or SAP mutation tool is exposed. This limits the capability surface for external agent clients. MCP clients should still be authenticated and authorized at the transport/deployment layer; stdio is intended for local development and trusted host processes.

## 8. Data model

### `knowledge_chunks`
Stores document title, source, chunk text, 384-dimensional vector, and creation timestamp.

### `purchase_orders`
Synthetic demo business data. In production, operational records should be read from approved SAP OData APIs or a governed replication layer rather than copied into this table without ownership rules.

### `approvals`
Stores requester, action type, JSON payload, state, decision metadata, result, and idempotency key.

### `audit_events`
Stores event type, actor, request correlation ID, JSON details, and timestamp. Treat this table as append-only operational evidence. Restrict update/delete privileges in production and export events to a tamper-resistant SIEM or immutable log store.

## 9. Security controls

| Control | MVP implementation | Production requirement |
|---|---|---|
| API authentication | Optional API key setting placeholder | OIDC/JWT validation, audience and issuer checks |
| Approver authentication | Shared demo key | SSO, MFA, RBAC, approver groups |
| Write governance | Pending approval + revalidation | Separation of duties and policy-as-code |
| SQL safety | Allowlisted view + read-only transaction | DB grants, RLS, query timeout, tenant scoping |
| SAP access | Mock default; bearer read | OAuth client credentials / principal propagation |
| SAP writes | Disabled for real SAP | CSRF, idempotency, allowlisted entity/action |
| Secrets | Environment variables | Vault/KMS, rotation, short-lived credentials |
| Audit | PostgreSQL event table | Immutable log/SIEM, retention and access controls |
| Retrieval | Source labels | Document ACLs, tenant filters, poisoning defenses |

The demo approver key is not suitable for production. Configure TLS at ingress and do not expose the approval endpoint to untrusted networks.

## 10. Observability

The API creates OpenTelemetry spans for agent requests and exports OTLP traces to Jaeger. Audit events provide business-level traceability; telemetry provides technical execution visibility.

Recommended production signals:
- Request count, latency percentiles, and error rate.
- Route distribution and tool success/failure.
- Retrieval hit rate and score distribution.
- Approval queue age and decision latency.
- SAP OData latency, throttling, and error classes.
- SQL duration and returned-row count.
- Token/cost metrics if an LLM provider is added.

Do not place credentials, full sensitive documents, or unrestricted prompt content in span attributes.

## 11. Reliability and failure behavior

- Missing database: health endpoint returns 503; tool operations fail.
- Empty knowledge base: RAG reports no supporting content rather than fabricating an answer.
- SQL validation failure: query is blocked and audited.
- SAP configuration failure: connector fails closed.
- Missing PO supplier/amount: no approval is created.
- Real SAP write attempt: explicitly disabled.
- Duplicate approval decision: conflict response.
- Embedding model unavailable: ingestion/search fails visibly; no fake retrieval result is returned.

## 12. Deployment topology

The Compose deployment runs:
- PostgreSQL 16 with pgvector.
- FastAPI application.
- Jaeger all-in-one for local trace inspection.

For production, deploy the API as a stateless container behind an authenticated ingress, PostgreSQL as a managed HA service, and telemetry to the organization's OTLP collector. Run MCP as a separate process or service with network-level access controls.

## 13. Test strategy

- Unit tests: routing, write-intent detection, SQL allowlist, SAP fail-closed behavior.
- Integration tests: database schema, ingestion/retrieval, approval state transitions.
- Contract tests: SAP OData metadata, CSRF and error handling.
- Security tests: prompt injection, SQL bypass attempts, approval race conditions, privilege escalation.
- Resilience tests: database outage, SAP timeout, OTLP outage, duplicate delivery.
- Acceptance tests: business-owner validation of policy answers and action payloads.

## 14. Known MVP limitations

- Routing uses deterministic keyword rules, not a production intent model.
- SQL natural-language support is intentionally narrow and maps to a fixed query.
- PO creation payload is a demo proposal, not a complete SAP PO schema.
- The real SAP write connector is deliberately disabled.
- The demo approver key is shared-secret authentication, not enterprise identity.
- Knowledge ingestion does not yet implement document ACLs, tenant partitioning, OCR, or malware scanning.
- The application has no frontend; Swagger and REST are the operator interface.
- Dependency versions are pinned, but production CI vulnerability scanning is still required.

## 15. Recommended next increments

1. Add OIDC login and role/tenant-aware policy enforcement.
2. Add a React approval console with diff view, comments, and decision history.
3. Add SAP OAuth token lifecycle, CSRF handling, metadata-driven entity validation, and sandbox contract tests.
4. Add a policy engine (OPA or Cedar) for action-level authorization.
5. Add hybrid retrieval (BM25 + vector), reranking, citations, and document-level ACL filters.
6. Add evaluation datasets for routing, retrieval relevance, groundedness, and tool safety.
7. Add transactional outbox and reconciliation for SAP side effects.
8. Add CI pipeline, container hardening, SBOM, and deployment manifests.
