
from typing import TypedDict, Any
from langgraph.graph import StateGraph, END

from app.core.policy import classify
from app.connectors.rag import search
from app.connectors.readonly_sql import run_readonly
from app.connectors.sap_odata import SAPODataConnector
from app.core.audit import audit

import uuid
import re


class State(TypedDict, total=False):
    user_id: str
    message: str
    request_id: str
    route: str
    answer: str
    sources: list
    approval_id: str
    status: str
    tool_result: Any


def route_node(state: State):
    selected_route = classify(state["message"])

    audit(
        "request_routed",
        state["user_id"],
        {
            "route": selected_route,
            "message": state["message"][:500],
        },
        state["request_id"],
    )

    return {"route": selected_route}


def rag_node(state: State):
    hits = search(state["message"], 5)

    if not hits:
        answer = (
            "I could not find supporting content in the indexed knowledge "
            "base. Ingest the relevant policy or document and ask again."
        )
    else:
        answer = "Retrieved knowledge (grounded excerpts):\n" + "\n".join(
            f"- [{h['title']} | {h['source']} | "
            f"relevance {float(h['score']):.3f}] {h['content']}"
            for h in hits
        )

    audit(
        "tool_rag_search",
        state["user_id"],
        {"hit_count": len(hits)},
        state["request_id"],
    )

    return {
        "answer": answer,
        "sources": hits,
        "status": "completed",
    }


def sql_node(state: State):
    msg = state["message"].lower()

    # This view exposes open purchase orders only.
    # Do not query it for closed purchase orders.
    if "closed" in msg:
        return {
            "answer": (
                "The current read-only database view exposes open purchase "
                "orders only. Closed purchase orders are not available "
                "through this query."
            ),
            "status": "not_supported",
        }

    query = (
        "SELECT * FROM v_open_purchase_orders "
        "ORDER BY created_at DESC LIMIT 50"
    )

    try:
        rows = run_readonly(query)

        answer = (
            f"Read-only query returned {len(rows)} row(s): {rows}"
        )

        audit(
            "tool_readonly_sql",
            state["user_id"],
            {
                "query": query,
                "row_count": len(rows),
            },
            state["request_id"],
        )

        return {
            "answer": answer,
            "tool_result": rows,
            "status": "completed",
        }

    except Exception as exc:
        audit(
            "tool_sql_denied",
            state["user_id"],
            {"error": str(exc)},
            state["request_id"],
        )

        return {
            "answer": f"SQL request was blocked: {exc}",
            "status": "blocked",
        }


def sap_read_node(state: State):
    try:
        result = SAPODataConnector().read(
            "PurchaseOrders",
            {"$top": 10},
        )

        audit(
            "tool_sap_read",
            state["user_id"],
            {"entity": "PurchaseOrders"},
            state["request_id"],
        )

        return {
            "answer": f"SAP OData read completed: {result}",
            "tool_result": result,
            "status": "completed",
        }

    except Exception as exc:
        audit(
            "tool_sap_read_failed",
            state["user_id"],
            {"error": str(exc)},
            state["request_id"],
        )

        return {
            "answer": f"SAP read failed closed: {exc}",
            "status": "blocked",
        }


def write_node(state: State):
    msg = state["message"]

    # Extract supplier ID.
    supplier = re.search(
        r"\bSUP-[A-Za-z0-9-]+\b",
        msg,
        re.IGNORECASE,
    )

    # Extract amount in INR, Rs, or rupee notation.
    amount = re.search(
        r"\b(?:INR|Rs\.?|₹)\s*([0-9,]+(?:\.\d{1,2})?)",
        msg,
        re.IGNORECASE,
    )

    if not supplier or not amount:
        return {
            "answer": (
                "This is a write-intent request. No action was executed. "
                "To prepare a PO request, include a supplier ID "
                "(for example SUP-1001) and amount "
                "(for example INR 125000)."
            ),
            "status": "needs_details",
        }

    import json
    from app.core.db import connection

    approval_id = str(uuid.uuid4())

    payload = {
        "supplier_id": supplier.group(0).upper(),
        "amount": float(amount.group(1).replace(",", "")),
        "currency": "INR",
        "action": "CREATE_PURCHASE_ORDER",
    }

    with connection() as c:
        c.execute(
            """
            INSERT INTO approvals
            (id, requester, action_type, payload, status, idempotency_key)
            VALUES (%s, %s, %s, %s::jsonb, 'PENDING', %s)
            """,
            (
                approval_id,
                state["user_id"],
                "CREATE_PURCHASE_ORDER",
                json.dumps(payload),
                approval_id,
            ),
        )

    audit(
        "approval_requested",
        state["user_id"],
        {
            "approval_id": approval_id,
            "payload": payload,
        },
        state["request_id"],
    )

    return {
        "approval_id": approval_id,
        "answer": (
            "A purchase-order creation request has been staged "
            "for human approval. No SAP write has occurred."
        ),
        "status": "pending_approval",
    }


def build_graph():
    g = StateGraph(State)

    # Register graph nodes.
    g.add_node("router", route_node)
    g.add_node("rag", rag_node)
    g.add_node("sql", sql_node)
    g.add_node("sap_read", sap_read_node)
    g.add_node("write", write_node)

    # IMPORTANT: The node is named "router", not "route".
    g.set_entry_point("router")

    # The state field remains "route".
    g.add_conditional_edges(
        "router",
        lambda state: state["route"],
        {
            "rag": "rag",
            "sql": "sql",
            "sap_read": "sap_read",
            "write": "write",
        },
    )

    for node in ("rag", "sql", "sap_read", "write"):
        g.add_edge(node, END)

    return g.compile()


graph = build_graph()


def run_request(user_id: str, message: str):
    request_id = str(uuid.uuid4())

    return graph.invoke(
        {
            "user_id": user_id,
            "message": message,
            "request_id": request_id,
        }
    )
