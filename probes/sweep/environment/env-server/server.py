"""MCP front end for the living-room sweep. One episode per container; seed, level and setting come from the environment.

Everything that touches the simulator, rendering included, runs on one worker thread: the GL context
belongs to the thread that made it.
"""
import asyncio
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.types import Image
from mcp.types import TextContent
from PIL import Image as PILImage
from starlette.requests import Request
import numpy as np
from starlette.responses import JSONResponse, Response

from sweep.sim import TIME_LIMIT, World

SEED = int(os.environ.get("SWEEP_SEED", "1"))
LEVEL = int(os.environ.get("SWEEP_LEVEL", "1"))
SETTING = os.environ.get("SWEEP_SETTING", "standard")
CAMERAS = ("head", "wrist_left", "wrist_right")          # the only cameras the robot has
W, H = 640, 480
DEPTH_CAMERAS = ("head",)                                 # the head camera is a colour-and-depth camera; the wrist ones are colour only
DEPTH_NEAR, DEPTH_FAR = 0.3, 5.0                           # range of the grey depth picture, metres

EXEC = ThreadPoolExecutor(max_workers=1)
WORLD: World = EXEC.submit(lambda: World(SEED, LEVEL, privileged=(SETTING == "privileged"))).result()
LOG: list[dict] = []
mcp = FastMCP("robot")


async def _on_sim(fn):
    return await asyncio.get_running_loop().run_in_executor(EXEC, fn)


def _brief(r: dict) -> dict:
    return {k: v for k, v in r.items() if k not in ("room", "obstacles")}


async def _call(tool: str, **args) -> str:
    def work():
        t0 = WORLD.robot_time
        r = WORLD.call(tool, **args)
        _explain(tool, args, r)
        LOG.append(dict(tool=tool, args=args, t=round(t0, 2), result=_brief(r)))
        return r
    return json.dumps(await _on_sim(work), separators=(",", ":"))


REACH = ("palm down, a hand reaches about 0.30 to 0.60 m in front of the base centre, from the centre line to about 0.5 m on its own "
         "side, from about 0.25 m above the floor up to about 0.55 m plus the torso height; can_reach gives the exact answer")


def _explain(tool: str, args: dict, r: dict) -> None:
    """Add what the robot itself knows about a move that did not arrive: where the target lies relative to its
    base, and which of its parts touch what. Nothing here tells where an object is that the robot is not touching."""
    import math
    if tool not in ("observe", "get_task"):                 # the joint angles are in observe(); repeating them in every reply only fills the history
        for hand in ("left_hand", "right_hand"):
            if isinstance(r.get(hand), dict):
                r[hand].pop("joints", None)
    if not r.get("ok") or r.get("reached") is not False:
        return
    if tool == "move_arm":
        b = r["base"]
        dx, dy = args["x"] - b["x"], args["y"] - b["y"]
        c, s = math.cos(b["heading"]), math.sin(b["heading"])
        r["target_from_base"] = dict(forward_m=round(c * dx + s * dy, 2), to_the_left_m=round(-s * dx + c * dy, 2), height_m=round(args["z"], 2))
        if r.get("moved") is False:
            r["reach"] = REACH
    if tool in ("drive_to", "move_arm"):
        m, d = WORLD.m, WORLD.d
        robot_root = m.body("base_link").id
        held = {WORLD.bid[t]: t for t in WORLD.holding.values() if t}
        def part(body):
            n = m.body(body).name
            return ("the " + held[body] + " it holds") if body in held else "left arm or hand" if "_left" in n else "right arm or hand" if "_right" in n else "head" if "head" in n else "base or torso"
        hits = set()
        for i in range(d.ncon):
            b1, b2 = m.geom_bodyid[d.contact[i].geom1], m.geom_bodyid[d.contact[i].geom2]
            r1, r2 = m.body_rootid[b1] == robot_root or b1 in held, m.body_rootid[b2] == robot_root or b2 in held
            if r1 != r2:
                mine, other, g = (b1, b2, d.contact[i].geom2) if r1 else (b2, b1, d.contact[i].geom1)
                name = (m.geom(g).name or m.body(other).name).replace("_", " ")
                # In the standard setting the robot is not told what the loose things are; a name would be a label.
                if not WORLD.privileged and (m.body(other).name in WORLD.items or m.body(m.body_rootid[other]).name in WORLD.items):
                    name = "a loose object"
                if name != "floor":
                    hits.add(f"{part(mine)} against {'furniture or a wall' if name == 'world' else name}")
        if tool == "drive_to":
            r["why"] = ("stopped by contact: " + "; ".join(sorted(hits))) if hits else "stopped before arriving; nothing is in contact now"
        elif hits and r.get("moved"):
            r["touching"] = sorted(hits)


def _left() -> float:
    return round(max(TIME_LIMIT - WORLD.robot_time, 0.0), 1)


@mcp.tool()
async def get_task() -> str:
    """The goal, the floor plan (table, sofa seat, tool shelf, every fixed obstacle, walls), tool sizes, the time limit, and examples of what counts as trash and what does not."""
    return await _call("get_task")


@mcp.tool()
async def observe() -> str:
    """The robot's own readings: base position and heading, torso height, head angles, each hand's pose, finger opening and what it holds, robot time left. Costs no robot time."""
    return await _call("observe")


@mcp.tool()
async def drive_to(x: float, y: float, heading: float) -> str:
    """Drive the base in a straight line to (x, y) in room coordinates (metres) while turning to `heading` (radians, 0 = facing +x). Stops where it is blocked; `reached` says whether it arrived."""
    return await _call("drive_to", x=x, y=y, heading=heading)


@mcp.tool()
async def move_arm(arm: str, x: float, y: float, z: float, yaw: float) -> str:
    """Move one hand ('left' or 'right') in a straight line so that the point between its fingers is at (x, y, z) in room coordinates, palm down, with the fingers closing along direction `yaw` (radians). A target the arm cannot reach from where the base stands is refused before anything moves (`moved` false, no robot time used). Otherwise `reached` and `error_m` say how close it got, and `why` says what stopped it."""
    return await _call("move_arm", arm=arm, x=x, y=y, z=z, yaw=yaw)


@mcp.tool()
async def can_reach(arm: str, x: float, y: float, z: float, yaw: float) -> str:
    """Would move_arm with these arguments arrive, from where the robot stands now? Worked out from the arm's own geometry (joint ranges and link lengths), not from what is in the way. Nothing moves and no robot time is used. If not, `why` says whether the point is out of reach or only the finger direction is."""
    return await _call("can_reach", arm=arm, x=x, y=y, z=z, yaw=yaw)


@mcp.tool()
async def home_arm(arm: str) -> str:
    """Bring one arm ('left' or 'right') back to its ready posture: hand in front of the chest, palm down. Use it when an arm no longer reaches targets it should reach."""
    return await _call("home_arm", arm=arm)


@mcp.tool()
async def grasp(arm: str) -> str:
    """Close the fingers of one hand. Takes the brush or the bin when the hand is on its handle with the fingers closing across it; if nothing is taken, `why` says what was missing. The fingers cannot hold trash or other loose things."""
    return await _call("grasp", arm=arm)


@mcp.tool()
async def release(arm: str) -> str:
    """Open the fingers of one hand and let go of what it holds."""
    return await _call("release", arm=arm)


@mcp.tool()
async def look(pan: float, tilt: float) -> str:
    """Point the head camera: pan in -1.2..1.2 rad (positive = left), tilt in -0.98..0.72 rad (negative = down)."""
    return await _call("look", pan=pan, tilt=tilt)


@mcp.tool()
async def set_torso(height: float) -> str:
    """Raise or lower the torso, 0 to 0.34 m. Both shoulders and the head move with it."""
    return await _call("set_torso", height=height)


@mcp.tool(output_schema=None)
async def camera(name: str):
    """A 640x480 colour picture from one of the robot's cameras: 'head', 'wrist_left' or 'wrist_right' (the wrist cameras look straight down past the fingers). Returns the picture and, as JSON, the camera's calibration: focal length f in pixels, cx, cy, and the camera's position and rotation in room coordinates. The head camera also measures depth: a second, grey picture shows it (near is bright), and the exact values in metres can be downloaded from http://env-server:8000/camera/head/depth.npy. Costs no robot time."""
    def work():
        if WORLD.closed:
            return dict(ok=False, error="the episode is over"), None
        if name not in CAMERAS:
            return dict(ok=False, error="camera must be one of " + ", ".join(CAMERAS)), None
        has_depth = name in DEPTH_CAMERAS
        c = WORLD.camera(name, W, H, depth=has_depth, all_walls=True)
        buf = io.BytesIO()
        PILImage.fromarray(c["rgb"]).save(buf, "JPEG", quality=88)
        meta = dict(ok=True, camera=name, width=W, height=H, calibration=c["calibration"], time_left_s=_left())
        grey = None
        if has_depth:
            meta["depth"] = dict(picture="second image: grey, near is bright", near_m=DEPTH_NEAR, far_m=DEPTH_FAR,
                                 values="http://env-server:8000/camera/head/depth.npy")
            g = io.BytesIO()
            PILImage.fromarray(_depth_grey(c["depth"])).save(g, "JPEG", quality=85)
            grey = g.getvalue()
        return meta, (buf.getvalue(), grey)
    meta, pics = await _on_sim(work)
    jpg, grey = pics if pics else (None, None)
    LOG.append(dict(tool="camera", args=dict(name=name), t=round(WORLD.robot_time, 2), result=meta))
    content = [TextContent(type="text", text=json.dumps(meta, separators=(",", ":")))]
    if jpg is not None:
        content.append(Image(data=jpg, format="jpeg").to_image_content())
    if grey is not None:
        content.append(Image(data=grey, format="jpeg").to_image_content())
    return ToolResult(content=content)


def _depth_grey(depth) -> "np.ndarray":
    t = np.clip((depth - DEPTH_NEAR) / (DEPTH_FAR - DEPTH_NEAR), 0.0, 1.0)
    return (255 * (1.0 - t)).astype(np.uint8)


# The head camera's frame for the agent's own code. The world is paused between calls, so a download shows
# the present moment. Only the robot's own cameras are served; nothing here tells where an object is.
@mcp.custom_route("/camera/{name}/{what}", methods=["GET"])
async def camera_file(request: Request) -> Response:
    name, what = request.path_params["name"], request.path_params["what"]
    if name not in CAMERAS or what not in ("depth.npy", "rgb.png", "calibration.json") or (what == "depth.npy" and name not in DEPTH_CAMERAS):
        return JSONResponse(dict(ok=False, error="available: /camera/<head|wrist_left|wrist_right>/rgb.png and calibration.json, /camera/head/depth.npy"), status_code=404)

    def work():
        if WORLD.closed:
            return None
        c = WORLD.camera(name, W, H, depth=(what == "depth.npy"), all_walls=True)
        buf = io.BytesIO()
        if what == "depth.npy":
            np.save(buf, c["depth"].astype(np.float32))
            return buf.getvalue(), "application/octet-stream"
        if what == "rgb.png":
            PILImage.fromarray(c["rgb"]).save(buf, "PNG")
            return buf.getvalue(), "image/png"
        return json.dumps(dict(camera=name, width=W, height=H, **c["calibration"])).encode(), "application/json"
    out = await _on_sim(work)
    LOG.append(dict(tool="camera_file", args=dict(name=name, what=what), t=round(WORLD.robot_time, 2), result=dict(ok=out is not None)))
    if out is None:
        return JSONResponse(dict(ok=False, error="the episode is over"), status_code=410)
    return Response(content=out[0], media_type=out[1])


@mcp.custom_route("/score", methods=["GET"])
async def score_route(request: Request) -> JSONResponse:
    # Final: asking for the score ends the episode.
    return JSONResponse(await _on_sim(WORLD.score))


@mcp.custom_route("/log", methods=["GET"])
async def log_route(request: Request) -> JSONResponse:
    # Seed and level name the room. They are given once the episode is over (the grader asks for the score
    # first, which ends it) and to requests from inside this container (the live viewer), never to the agent's
    # container while it plays.
    out = dict(setting=SETTING, calls=LOG)
    local = request.client is not None and request.client.host in ("127.0.0.1", "::1")
    if WORLD.closed or local:
        out = dict(seed=SEED, level=LEVEL, **out)
    return JSONResponse(out)


if __name__ == "__main__":
    def warm():
        t = time.time()
        WORLD.camera("head", W, H, depth=False)
        first = time.time() - t
        t = time.time()
        for _ in range(3):
            WORLD.camera("head", W, H, depth=False)
        return first, (time.time() - t) / 3
    first, each = EXEC.submit(warm).result()
    print(f"sweep server: seed {SEED} level {LEVEL} setting {SETTING}; colour frame {each:.3f} s (first {first:.2f} s), GL={os.environ.get('MUJOCO_GL')}", flush=True)
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
