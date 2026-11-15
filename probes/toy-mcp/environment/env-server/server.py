"""Toy environment: all state and the score live here, not in the agent's container."""
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

mcp = FastMCP("env")
STATE = {"count": 0, "calls": 0}
TARGET = 5


@mcp.tool()
def status() -> str:
    """Show the current counter value."""
    STATE["calls"] += 1
    return f"count={STATE['count']} target={TARGET}"


@mcp.tool()
def press() -> str:
    """Increase the counter by one."""
    STATE["calls"] += 1
    STATE["count"] += 1
    return f"count={STATE['count']} target={TARGET}"


def score() -> float:
    c = STATE["count"]
    return max(0.0, 1.0 - abs(TARGET - c) / TARGET)


@mcp.custom_route("/score", methods=["GET"])
async def score_route(request: Request) -> JSONResponse:
    return JSONResponse({"score": score(), **STATE})


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
