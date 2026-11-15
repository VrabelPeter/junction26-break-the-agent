#!/bin/bash
# Reference run: a scripted controller that uses only what the agent has (the MCP tools and the camera files).
#   SWEEP_POLICY=reference (default)      looks at the room through the head camera (colour and depth), then
#                                         fetches the tools and sweeps. Works in the standard setting.
#   SWEEP_POLICY=reference_privileged     the same controller reading object positions from observe();
#                                         needs SWEEP_SETTING=privileged
#   SWEEP_POLICY=stop_early               fetches the tools, then stops
#   SWEEP_POLICY=stop_after_one           sweeps one piece of trash, then stops
#   SWEEP_POLICY=smoke                    checks what the agent's container can and cannot get (see smoke.py)
# solution/sweep/ holds copies of the controller's files from environment/env-server/sweep
# (refresh with: cp environment/env-server/sweep/{__init__,scene,policies,perception}.py environment/env-server/sweep/perception_model.json solution/sweep/).
cd "$(dirname "$0")"
python3 - "${SWEEP_POLICY:-${TABLETOP_POLICY:-reference}}" <<'PY'
import asyncio, io, json, sys, urllib.request
import numpy as np
from PIL import Image
from fastmcp import Client
from sweep import policies


class Robot:
    """The same method names as the simulator's World, carried out through the MCP tools."""

    def __init__(self, call):
        self._call = call
        o = call("observe")
        self.scene = {"tools": "in_hand" if o["left_hand"]["holding"] or o["right_hand"]["holding"] else "station"}

    def observe(self): return self._call("observe")
    def get_task(self): return self._call("get_task")
    def drive_to(self, x, y, heading): return self._call("drive_to", x=float(x), y=float(y), heading=float(heading))
    def move_arm(self, arm, x, y, z, yaw): return self._call("move_arm", arm=arm, x=float(x), y=float(y), z=float(z), yaw=float(yaw))
    def home_arm(self, arm): return self._call("home_arm", arm=arm)
    def grasp(self, arm): return self._call("grasp", arm=arm)
    def release(self, arm): return self._call("release", arm=arm)
    def look(self, pan, tilt): return self._call("look", pan=float(pan), tilt=float(tilt))
    def set_torso(self, height): return self._call("set_torso", height=float(height))
    def score(self): return {}        # the score is the verifier's business

    def camera(self, name="head", width=640, height=480, depth=True, all_walls=True):
        """The camera's present frame as arrays, from the files the sidecar serves to the agent's container."""
        get = lambda what: urllib.request.urlopen(f"http://env-server:8000/camera/{name}/{what}", timeout=60).read()
        out = dict(rgb=np.array(Image.open(io.BytesIO(get("rgb.png"))).convert("RGB")), calibration=json.loads(get("calibration.json")))
        if depth:
            out["depth"] = np.load(io.BytesIO(get("depth.npy")))
        return out


async def main(name):
    async with Client("http://env-server:8000/mcp") as c:
        loop = asyncio.get_running_loop()

        def call(tool, **args):
            fut = asyncio.run_coroutine_threadsafe(c.call_tool(tool, args), loop)
            r = json.loads(fut.result().content[0].text)
            if not r.get("ok"):
                raise RuntimeError(f"{tool}{args}: {r.get('error')}")
            return r
        if name == "smoke":
            await smoke(c, call)
            return
        await asyncio.to_thread(lambda: policies.POLICIES[name](Robot(call)))
        print("done")


async def smoke(c, call):
    """Quick check, from inside the agent's container, that the agent gets what the instruction promises and nothing more."""
    import io, urllib.request, urllib.error
    import numpy as np
    out = {}
    def get(path):
        try:
            with urllib.request.urlopen("http://env-server:8000" + path, timeout=30) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, b""
    task = await asyncio.to_thread(call, "get_task"); obs = await asyncio.to_thread(call, "observe")
    out["setting"] = task.get("setting")
    out["objects_in_observation"] = "objects" in obs
    tools = sorted(t.name for t in await c.list_tools())
    out["tools"] = tools
    out["no_pixel_to_position_tool"] = not any("depth_at" in t or "pixel" in t for t in tools)
    head = await c.call_tool("camera", {"name": "head"}); wrist = await c.call_tool("camera", {"name": "wrist_left"})
    out["head_parts"] = [p.type for p in head.content]; out["wrist_parts"] = [p.type for p in wrist.content]
    meta = json.loads(head.content[0].text)
    out["calibration_keys"] = sorted(meta["calibration"])
    code, raw = get("/camera/head/depth.npy"); d = np.load(io.BytesIO(raw)) if code == 200 else None
    out["depth"] = dict(status=code, shape=list(d.shape) if d is not None else None, dtype=str(d.dtype) if d is not None else None,
                        min=float(d.min()) if d is not None else None, centre=float(d[240, 320]) if d is not None else None)
    out["rgb_png_status"] = get("/camera/head/rgb.png")[0]
    out["wrist_depth_status"] = get("/camera/wrist_left/depth.npy")[0]            # must be refused
    out["room_camera_status"] = get("/camera/overview/rgb.png")[0]                # must be refused
    bad = await c.call_tool("camera", {"name": "overview"}); out["room_camera_by_tool"] = json.loads(bad.content[0].text).get("ok")
    moved = await asyncio.to_thread(call, "drive_to", x=obs["base"]["x"] + 0.2, y=obs["base"]["y"], heading=obs["base"]["heading"])
    out["drive_reached"] = moved.get("reached")
    # The arm: every target the reach check accepts must arrive; a target it rejects must be refused without moving.
    import math
    o = await asyncio.to_thread(call, "observe"); b = o["base"]; c0, s0 = math.cos(b["heading"]), math.sin(b["heading"])
    arm = dict(accepted=0, arrived=0, refused_ok=0, rejected=0, worst_m=0.0)
    for name, sign in (("left", 1), ("right", -1)):
        yaw0 = o[name + "_hand"]["yaw"]
        for fwd, side, z, dyaw in ((0.45, 0.05, 0.50, 0.0), (0.40, 0.25, 0.40, 0.0), (0.55, 0.35, 0.55, 0.0), (0.40, 0.30, 0.45, math.pi / 2), (0.50, 0.0, 0.60, 0.0), (0.95, 0.2, 0.5, 0.0)):
            args = dict(arm=name, x=b["x"] + c0 * fwd - s0 * side * sign, y=b["y"] + s0 * fwd + c0 * side * sign, z=z, yaw=yaw0 + dyaw)
            chk = await asyncio.to_thread(lambda: call("can_reach", **args)); r = await asyncio.to_thread(lambda: call("move_arm", **args))
            if chk["reachable"]:
                arm["accepted"] += 1; arm["arrived"] += bool(r["reached"]); arm["worst_m"] = max(arm["worst_m"], r["error_m"])
            else:
                arm["rejected"] += 1; arm["refused_ok"] += (r.get("moved") is False and bool(r.get("why")))
        await asyncio.to_thread(lambda: call("home_arm", arm=name))
    g = await asyncio.to_thread(lambda: call("grasp", arm="left"))
    out["arm"] = arm; out["empty_grasp_says_why"] = bool(g.get("why")); out["joints_only_in_observe"] = "joints" not in g["left_hand"] and "joints" in o["left_hand"]
    ok = (out["no_pixel_to_position_tool"] and out["head_parts"] == ["text", "image", "image"] and out["wrist_parts"] == ["text", "image"]
          and out["depth"]["shape"] == [480, 640] and 0.2 < out["depth"]["centre"] < 10 and out["rgb_png_status"] == 200
          and out["wrist_depth_status"] == 404 and out["room_camera_status"] == 404 and out["room_camera_by_tool"] is False
          and arm["accepted"] >= 8 and arm["arrived"] == arm["accepted"] and arm["rejected"] >= 2 and arm["refused_ok"] == arm["rejected"]
          and out["empty_grasp_says_why"] and out["joints_only_in_observe"]
          and out["drive_reached"] is True and (out["objects_in_observation"] == (out["setting"] == "privileged")))
    out["ok"] = bool(ok)
    print("SMOKE_JSON " + json.dumps(out))

asyncio.run(main(sys.argv[1]))
PY
