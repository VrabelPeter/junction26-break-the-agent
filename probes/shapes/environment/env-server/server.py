"""MCP front end for the shape-board simulator. One episode per container; the seed
comes from the environment."""
import json
import os
import threading

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from shapeboard.sim import World

WORLD = World(int(os.environ.get("SHAPES_SEED", "1")))
LOCK = threading.Lock()
mcp = FastMCP("robot")


def _call(tool: str, **args) -> str:
    with LOCK:
        return WORLD.call(tool, **args)


@mcp.tool()
def get_task() -> str:
    """Everything that is known in advance: the pegs of this job and their outlines, clearance, chamfer, insertion depth, wrist stiffness, friction, force limits, how wrong the hole estimate can be, and the move budget."""
    return json.dumps(WORLD.task())


@mcp.tool()
def observe() -> str:
    """The latest reading again: tool pose, wrench, what the last move achieved, moves left. Free. It is the same reading as the last move returned, not a new measurement."""
    return _call("observe")


@mcp.tool()
def move(dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, dyaw: float = 0.0, max_force: float = 5.0) -> str:
    """One guarded move of the peg, relative to where the arm is now: dx, dy, dz in mm (at most 5 mm in total), dyaw in degrees (at most 5). The arm stops early when the contact force reaches max_force (1 to 25 N). Costs one move. Returns the new reading."""
    return _call("move", dx=dx, dy=dy, dz=dz, dyaw=dyaw, max_force=max_force)


@mcp.tool()
def next_peg() -> str:
    """Close the current peg as it stands (it is scored where it is) and pick up the next one above its hole. After the last peg the job is over."""
    return _call("next_peg")


@mcp.custom_route("/score", methods=["GET"])
async def score_route(request: Request) -> JSONResponse:
    with LOCK:
        return JSONResponse(WORLD.score())


@mcp.custom_route("/log", methods=["GET"])
async def log_route(request: Request) -> JSONResponse:
    # The operator's own command history: nothing the tools did not already return.
    with LOCK:
        return JSONResponse(WORLD.log)


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
