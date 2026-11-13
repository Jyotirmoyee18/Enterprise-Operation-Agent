"""Read-only MCP server. No write/approval tools are registered."""
from mcp.server.fastmcp import FastMCP
from app.connectors.rag import search
from app.connectors.readonly_sql import run_readonly

mcp = FastMCP("enterprise-operations-readonly")

@mcp.tool()
def search_knowledge(query: str, top_k: int = 5) -> list[dict]:
    """Search indexed enterprise knowledge. Read-only."""
    if top_k < 1 or top_k > 10: raise ValueError("top_k must be between 1 and 10")
    return search(query, top_k)

@mcp.tool()
def run_readonly_sql(query: str) -> list[dict]:
    """Execute a single SELECT against the approved read-only view only."""
    return run_readonly(query)

if __name__ == "__main__":
    mcp.run()
