
import re


WRITE_PATTERNS = [
    r"\b(create|raise|submit|post|release|change|update|delete|cancel)\b.{0,80}\b(po|purchase order|sales order|vendor|supplier|delivery|invoice)\b",
    r"\b(po|purchase order|sales order)\b.{0,80}\b(create|raise|submit|post|release|change|update|delete|cancel)\b",
]

SAP_PATTERNS = [
    r"\b(sap|odata|s/4hana|s4hana|fiori|business partner)\b",
    r"\b(read|fetch|get|retrieve|check)\b.{0,50}\b(sap|purchase orders|sales orders)\b",
]

SQL_PATTERNS = [
    r"\b(show|list|display|fetch|retrieve|get)\b.{0,60}\b(open )?(purchase orders|pos|sales orders|suppliers|vendors|invoices)\b",
    r"\b(latest|recent|all|open|pending)\b.{0,40}\b(purchase orders|pos|sales orders|suppliers|vendors|invoices)\b",
    r"\b(sql|database|db query|table records)\b",
]

RAG_PATTERNS = [
    r"\b(policy|procedure|document|knowledge|guideline|guidelines)\b",
    r"\b(what approval|what approvals|approval requirement|approval requirements)\b",
    r"\b(explain|summarize|describe|according to|based on|as per)\b",
    r"\b(what is|required|how do|how does|why does|why is)\b",
]


def matches_any(patterns, message):
    return any(
        re.search(pattern, message, re.IGNORECASE)
        for pattern in patterns
    )


def is_write_intent(message: str) -> bool:
    return matches_any(WRITE_PATTERNS, message)


def classify(message: str) -> str:
    message = message.strip()

    # Transactional requests have the highest priority.
    if is_write_intent(message):
        return "write"

    # Explicit SAP-system requests.
    if matches_any(SAP_PATTERNS, message):
        return "sap_read"

    # Policy and explanatory questions should use enterprise RAG.
    if matches_any(RAG_PATTERNS, message):
        return "rag"

    # Explicit requests for business records use read-only SQL.
    if matches_any(SQL_PATTERNS, message):
        return "sql"

    # Safe default: retrieve information from the knowledge base.
    return "rag"
