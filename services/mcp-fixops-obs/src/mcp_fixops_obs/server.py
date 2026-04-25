"""stdio MCP server — `prometheus_query` calls PROMETHEUS_URL when set, else stub."""

import os
import sys

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fixops-observability")


@mcp.tool()
def prometheus_query(expr: str) -> str:
    """Run an instant PromQL query (read-only)."""
    base = os.environ.get("PROMETHEUS_URL")
    if not base:
        return f'{{"status":"success","stub":true,"expr":{expr!r}}}'
    url = base.rstrip("/") + "/api/v1/query"
    with httpx.Client(timeout=20.0) as c:
        r = c.get(url, params={"query": expr})
        r.raise_for_status()
        return r.text


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
