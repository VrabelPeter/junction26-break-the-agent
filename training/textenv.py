"""The living-room sweep as a text interface: what a small language model sees and says.

One place for everything that collection, the dataset, and the evaluation loop must agree on:

  * how a tool call is written          format_call / parse_call
  * how a tool reply is shortened       compact_reply   (the SAME function for training data and evaluation)
  * the system prompt                   SYSTEM_PROMPT   (a compact, faithful version of probes/sweep/instruction.md
                                                         for the privileged, text-only setting)
  * where the simulator lives           import_sweep()

Nothing here changes the environment: the simulator's World is used as it is, through World.call.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_SERVER = Path(os.environ.get("SWEEP_ENV_SERVER", HERE.parent / "probes" / "sweep" / "environment" / "env-server"))


def import_sweep():
    """The simulator package (probes/sweep/environment/env-server/sweep), imported from where it lives."""
    if str(ENV_SERVER) not in sys.path:
        sys.path.insert(0, str(ENV_SERVER))
    from sweep import policies, scene, sim       # noqa: PLC0415
    return sim, policies, scene


# ---------------------------------------------------------------------------------------------------
# Tool calls as text
# ---------------------------------------------------------------------------------------------------
ARGS = {                      # tool -> argument names, in the order they are written
    "get_task": (),
    "observe": (),
    "drive_to": ("x", "y", "heading"),
    "move_arm": ("arm", "x", "y", "z", "yaw"),
    "home_arm": ("arm",),
    "grasp": ("arm",),
    "release": ("arm",),
    "look": ("pan", "tilt"),
    "set_torso": ("height",),
}
MOVING = ("drive_to", "move_arm", "home_arm", "grasp", "release", "look", "set_torso")
DONE = "done"                 # not a simulator tool: the controller says it has finished
DECIMALS = 3                  # millimetres and milliradians: finer than anything the robot resolves


def _num(v):
    v = round(float(v), DECIMALS)
    return 0.0 if v == 0 else v          # no "-0.0"


def clean_args(tool: str, args: dict) -> dict:
    """Arguments in canonical order, numbers rounded to DECIMALS. What is logged is what is executed."""
    return {k: (args[k] if k == "arm" else _num(args[k])) for k in ARGS[tool]}


def format_call(tool: str, args: dict | None = None) -> str:
    """One tool call as the model writes it: a flat JSON object, e.g. {"tool":"drive_to","x":-1.05,"y":-0.6,"heading":3.142}"""
    if tool == DONE:
        return '{"tool":"done"}'
    return json.dumps({"tool": tool, **clean_args(tool, args or {})}, separators=(",", ":"))


class BadCall(ValueError):
    pass


_THINK = re.compile(r"<think>.*?</think>", re.S)


def parse_call(text: str) -> tuple[str, dict]:
    """The first JSON object in the model's text -> (tool, args). Lenient about wrapping (code fences, a
    sentence before it, {"name":..,"arguments":{..}}), strict about the tool name and its arguments."""
    text = _THINK.sub("", text)
    start = text.find("{")
    if start < 0:
        raise BadCall("no JSON object found")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as e:
        raise BadCall(f"not valid JSON ({e.msg})") from None
    if not isinstance(obj, dict):
        raise BadCall("the reply must be a JSON object")
    tool = obj.get("tool", obj.get("name"))
    if not isinstance(tool, str):
        raise BadCall('missing "tool"')
    args = obj.get("args", obj.get("arguments"))
    if not isinstance(args, dict):
        args = {k: v for k, v in obj.items() if k not in ("tool", "name", "args", "arguments")}
    if tool == DONE:
        return DONE, {}
    if tool == "camera":
        raise BadCall("there are no pictures in this setting; positions come from observe")
    if tool not in ARGS:
        raise BadCall(f"unknown tool {tool}; tools: {', '.join(ARGS)}, done")
    want = ARGS[tool]
    missing = [k for k in want if k not in args]
    extra = [k for k in args if k not in want]
    if missing or extra:
        raise BadCall(f"{tool} takes exactly: {', '.join(want) or 'no arguments'}")
    for k in want:
        v = args[k]
        if k == "arm":
            if v not in ("left", "right"):
                raise BadCall("arm must be 'left' or 'right'")
        elif isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise BadCall(f"{k} must be a finite number")
    return tool, clean_args(tool, args)


# ---------------------------------------------------------------------------------------------------
# Tool replies as text
# ---------------------------------------------------------------------------------------------------
GET_TASK_CHARS = 1500         # get_task is long (the floor plan); cut here. The system prompt carries the essentials.


def _dumps(o) -> str:
    return json.dumps(o, separators=(",", ":"))


def _hand(h: dict) -> dict:
    return {"pos": [h["x"], h["y"], h["z"]], "yaw": h["yaw"], "holding": h["holding"]}


def _tleft(r: dict) -> int:
    return int(max(r.get("time_left_s", 0.0), 0.0))


def compact_reply(tool: str, args: dict, r: dict) -> str:
    """A simulator reply (the dict World.call returns) as the short text the model reads. Deterministic.

    Dropped everywhere: arm joint angles, finger opening, head angles (no camera in this setting).
    A moving tool's reply keeps what that move changed; `observe` gives the whole state.
    """
    if not r.get("ok"):
        return _dumps({"ok": False, "error": str(r.get("error", "failed"))[:200]})
    if tool == "observe":
        out = {"ok": True, "base": [r["base"]["x"], r["base"]["y"], r["base"]["heading"]], "torso": r["torso"],
               "left": _hand(r["left_hand"]), "right": _hand(r["right_hand"])}
        if "objects" in r:
            out["objects"] = [{"name": o["name"], "kind": o["kind"], "trash": o["trash"], "where": o["where"],
                               "pos": [o["x"], o["y"], o["z"]]} for o in r["objects"]]
            for t in ("brush", "bin"):
                h = r[t]["handle"]
                out[t + "_handle"] = [h["x"], h["y"], h["z"]]
        out["t_left"] = _tleft(r)
        return _dumps(out)
    if tool == "get_task":
        def short(o):
            if isinstance(o, float):
                return round(o, 2)
            if isinstance(o, dict):
                return {k: short(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [short(v) for v in o]
            return o
        s = _dumps(short(r))
        return s if len(s) <= GET_TASK_CHARS else s[:GET_TASK_CHARS] + "...(cut)"
    out = {"ok": True}
    if tool == "drive_to":
        out["reached"] = r["reached"]
        out["base"] = [r["base"]["x"], r["base"]["y"], r["base"]["heading"]]
    elif tool in ("move_arm", "home_arm"):
        out["reached"] = r["reached"]
        if "error_m" in r:
            out["error_m"] = r["error_m"]
        h = r[args["arm"] + "_hand"]
        out["hand"] = [h["x"], h["y"], h["z"], h["yaw"]]
    elif tool == "grasp":
        out["holding"] = r["holding"]
    elif tool == "release":
        out["released"] = r["released"]
    elif tool == "set_torso":
        out["torso"] = r["torso"]
    elif tool == "look":
        out["head"] = [r["head"]["pan"], r["head"]["tilt"]]
    out["t_left"] = _tleft(r)
    return _dumps(out)


def expand_observe(text: str) -> dict:
    """The inverse of compact_reply for `observe`: back to the field names the scripted controller reads.
    Used only by the check that the compact text carries everything the reference needs."""
    c = json.loads(text)
    out = {"ok": c["ok"], "base": dict(zip(("x", "y", "heading"), c["base"])), "torso": c["torso"], "time_left_s": c["t_left"]}
    for a in ("left", "right"):
        h = c[a]
        out[a + "_hand"] = dict(x=h["pos"][0], y=h["pos"][1], z=h["pos"][2], yaw=h["yaw"], holding=h["holding"])
    if "objects" in c:
        out["objects"] = [dict(name=o["name"], kind=o["kind"], trash=o["trash"], where=o["where"],
                               x=o["pos"][0], y=o["pos"][1], z=o["pos"][2]) for o in c["objects"]]
        for t in ("brush", "bin"):
            out[t] = {"handle": dict(zip(("x", "y", "z"), c[t + "_handle"]))}
    return out


# ---------------------------------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------------------------------
SYSTEM_PROMPT = """You control a wheeled robot with two arms in a living room. Trash and personal items lie on a coffee table (at higher levels also on a sofa). A brush and a bin wait at a tool station.

GOAL: get every piece of trash into the bin. Leave personal items where they are. One attempt, real physics, nothing is reset.

SCORE (0 to 1) = (trash in the bin / all trash) x 0.5^mistakes, read from where everything lies 2 s after you stop.
- Trash counts when it lies inside the bin, on the bin's floor, and the bin stands upright.
- A mistake is a personal item that ends in the bin or on the floor, or the bin lying on its side.
- Nothing is paid for fetching or holding the tools, or for touching things. Only the end state counts.

HOW TO ACT: reply with exactly one JSON object per turn and nothing else. The next message is the tool's reply.
{"tool":"observe"}                                       full state (free): base [x,y,heading], torso, each hand {pos:[x,y,z],yaw,holding}, every object {name,kind,trash,where,pos}, brush_handle and bin_handle [x,y,z] (the grasp points), t_left
{"tool":"get_task"}                                      goal and floor plan (free)
{"tool":"drive_to","x":X,"y":Y,"heading":H}              straight-line move of the base while turning to H; stops where blocked (reached:false); no route planning
{"tool":"move_arm","arm":"left","x":X,"y":Y,"z":Z,"yaw":A}   straight-line move of one hand ("left" or "right"), palm down; fingers close along direction A; replies reached, error_m, hand [x,y,z,yaw]
{"tool":"home_arm","arm":"left"}                         bring one arm back to its ready posture
{"tool":"grasp","arm":"left"}                            close the fingers; takes a tool when the hand is within 0.035 m of its grasp point with the fingers closing across the handle
{"tool":"release","arm":"left"}                          open the fingers, let go
{"tool":"set_torso","height":T}                          raise or lower the torso, 0 to 0.34
{"tool":"look","pan":P,"tilt":T}                         point the head (not needed here: there are no pictures)
{"tool":"done"}                                          stop; the room is then scored
Numbers have at most 3 decimals. Replies are JSON with "ok"; a tool that cannot act replies ok:false with an error. Robot time is limited to 900 s (t_left); only moving costs time.

THE ROOM: metres and radians, floor z = 0. Walls at x = -2 and 2, y = -2.4 and 1.85. Heading 0 faces +x, 1.571 faces +y. The robot starts near (-0.9, -1.35) facing +y.
Coffee table: x 0.30 +- 0.50, y -0.70 +- 0.25, top at z 0.45. Sofa seat against the +y wall: x 0.30 +- 0.80, y 1.30 +- 0.33, top 0.42. Tool shelf at the -x wall near (-1.75, -0.82), top 0.50; a robot standing at (-1.10, -0.60) facing -x (heading 3.142) has the brush handle in front of its left hand and the bin handle in front of its right hand.

THE ROBOT: base 0.72 long, 0.50 wide, drives in any direction. A hand's position is the point between its fingers; the fingers hang about 0.03 below it. Palm down, a hand reaches about 0.30 to 0.65 m in front of the base centre, from the centre line to about 0.6 m on its own side, at heights 0.26 to 0.70.

THE TOOLS: Brush: head with bristles 0.22 wide, straight handle 0.30 long; the middle of the head is 0.26 from the grasp point along the handle; the grasp point is 0.06 above the bristle tips: with the hand about 0.05 above a surface the bristles press on it, above 0.065 they do not touch. Bin: open box 0.30 long, 0.20 wide, 0.36 tall, with a bar handle 0.07 outside one short side, 0.35 above its bottom; the grasp point is 0.22 from the middle of the bin. A held tool moves with the hand until release. The brush pushes whatever its bristles meet; a thing pushed over the table edge falls, and lands in the bin only if the bin stands there.

WHAT GOES WRONG: personal items are loose like the trash and get pushed the same way. The bin can be knocked over. A blocked move stops; what was pushed stays pushed."""

FIRST_USER = "Level {level}. The room is ready. Send your first tool call."


def start_messages(level: int) -> list[dict]:
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": FIRST_USER.format(level=level)}]


def approx_tokens(text: str) -> int:
    """Token count without a tokenizer. Measured on this data with the Qwen3 tokenizer: see training/README.md."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


CHARS_PER_TOKEN = 2.5         # measured on this data with the Qwen3 tokenizer (2.48); a real tokenizer is used wherever one is available


def parse_seeds(spec: str) -> list[int]:
    """'1-32' or '1,2,5-8' -> list of ints."""
    out: list[int] = []
    for part in str(spec).replace(" ", ",").split(","):
        if not part:
            continue
        if "-" in part[1:]:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out
