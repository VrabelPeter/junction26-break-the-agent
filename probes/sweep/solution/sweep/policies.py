"""Scripted controllers. They use only the tool calls an agent has.

`reference_privileged` is the reference run. It reads where things are from the privileged
observation, and only through `_objects` and `_tool_handle`: a reference for the standard setting
replaces those two functions with a camera pipeline and keeps every motion below.

How the reference sweeps one piece of trash:

  1. choose an edge of the surface and a line across it so that no personal item lies between the
     piece and that edge inside the brush's 0.22 m swath;
  2. if the piece lies too deep to reach with the bin in the way, pull it towards the edge first
     ("gather": no bin involved, the robot stands close);
  3. set the bin against the edge on that line, put the brush down behind the piece, pull it over the
     edge into the bin, and check that it arrived.

All distances are metres. "Depth" is how far into a surface a point lies from the chosen edge.
"""
from __future__ import annotations

import math

from . import scene as S

# --- the robot's working geometry (measured on the arm: see probes/sweep/README.md) -------------------
TORSO = 0.25                 # torso height for all work
HAND_NEAR, HAND_FAR = 0.36, 0.65    # how close to / far from the base centre a hand works comfortably, palm down
BRUSH_LATERAL = 0.35         # the brush hand works this far to the left of the base centre
HEAD_AHEAD = 0.26            # the brush head is this far in front of the hand
HEAD_HALF = 0.11             # half the width of the brush head
BRISTLES = 0.018             # half the thickness of the bristle block, along the stroke
HANDLE_CLEAR = 0.045         # the handle runs this high above the surface when the brush is down: taller things
                             # (a standing can) must sit beside it, under the outer part of the head

# --- heights above a surface, for the brush hand ------------------------------------------------------
BRUSH_DOWN = 0.048           # bristles pressed about 15 mm into their spring (they touch at 0.064)
BRUSH_OVER = 0.17            # travelling over the surface: clears a standing can

# --- standing distances: base centre to the edge the brush pulls towards ------------------------------
SWEEP_STANDOFF = HAND_NEAR + HEAD_AHEAD          # 0.62: the head is exactly over the edge with the hand pulled in
GATHER_MIN, GATHER_MAX = 0.42, 0.52              # while gathering, with nothing between robot and edge
GATHER_TO = 0.17             # gathering leaves the brush head this deep (a light piece slides on a little)
PAST_EDGE = 0.08             # the final pull takes the head this far beyond the edge
RETREAT = 0.25               # step back this far before travelling

# --- travelling ---------------------------------------------------------------------------------------
LANE_X = S.SURFACES["table"]["x"][0] - 0.75      # the free strip between the tool station and the table
TURN_Y = -0.20               # the robot only turns here: nothing is within reach of the tools it carries

HOVER = 0.14                 # hand height above a handle before coming down on it
KEEP_CLEAR = 0.012           # the bristles stay this far from a personal item's footprint
MAX_TRIES = 3                # strokes per piece before giving up on it


# ======================================================================================================
# What the controller knows about the room. Everything that reads object positions is in this block.
# ======================================================================================================
class Told:
    """Privileged setting: the observation lists every loose thing and both tool handles, always up to date."""

    def objects(self, w) -> dict:
        out = {}
        for o in w.observe()["objects"]:
            o = dict(o)
            o["r"] = S.KINDS[o["kind"]]["r"]
            top = S.SURFACES[o["where"][3:]]["top"] if o["where"] in ("on_table", "on_sofa") else 0.0
            o["height"] = 2 * max(0.0, o["z"] - top)
            out[o["name"]] = o
        return out

    def tool_handle(self, w, tool):
        h = w.observe()[tool]["handle"]
        return h["x"], h["y"], h["z"]

    def pulled(self, side, line_x, from_depth, to_depth): pass      # nothing to remember: the next observation says it
    def pushed(self, name, new_x): pass
    def put_down(self, tool, x, y, z): pass


class Seen:
    """Standard setting: nobody tells the robot where things are. It looks once, with empty hands, through its
    head camera (colour and depth; `perception.py`), and from then on keeps its own account of what its strokes
    did to the things it saw. It cannot look again while it carries the tools, so this account is all it has."""

    def __init__(self, w):
        from . import perception
        tools = perception.locate_tools(w)
        if not tools["brush"] or not tools["bin"]:
            raise RuntimeError("could not find the tools at the station")
        self.tools = {t: (tools[t]["x"], tools[t]["y"], tools[t]["z"]) for t in ("brush", "bin")}
        self.things = {}
        for i, d in enumerate(perception.survey(w)["detections"]):
            if d["group"] == "tool":
                continue
            kind = d["kind"]
            top = S.SURFACES[d["surface"]]["top"]
            self.things[f"{kind}_{i}"] = dict(
                name=f"{kind}_{i}", kind=kind, trash=d["group"] == "trash", where="on_" + d["surface"],
                x=d["x"], y=d["y"], z=top + d["height"] / 2, height=d["height"],
                r=S.KINDS[kind]["r"] if kind in S.KINDS else max(d["length"], d["width"]) / 2)

    def objects(self, w) -> dict:
        return {n: dict(o) for n, o in self.things.items()}

    def tool_handle(self, w, tool):
        return self.tools[tool]

    def pulled(self, side, line_x, from_depth, to_depth):
        """A stroke along `line_x` from `from_depth` to `to_depth`: whatever lay under the head went with it."""
        for o in self.things.values():
            if o["where"] != "on_" + side.surface or abs(o["x"] - line_x) > HEAD_HALF:
                continue
            depth = side.depth(o["y"])
            if to_depth < depth <= from_depth:
                if to_depth < 0:
                    o["where"] = "in_bin" if o["trash"] else "on_floor"
                else:
                    o["y"] = side.y_at(max(0.02, to_depth - BRISTLES / 2 - min(o["r"], 0.04)))

    def pushed(self, name, new_x):
        if name in self.things:
            self.things[name]["x"] = new_x

    def put_down(self, tool, x, y, z):
        self.tools[tool] = (x, y, z)


ROOM = Told()


def _objects(w) -> dict:
    """name -> dict(kind, trash, where, x, y, z, r) for every loose thing; r is its footprint radius."""
    return ROOM.objects(w)


def _tool_handle(w, tool):
    return ROOM.tool_handle(w, tool)


# ======================================================================================================
# Frames: where the robot stands relative to a surface
# ======================================================================================================
class Side:
    """The robot faces `surface` from the south (looking north) or from the north (looking south)."""

    def __init__(self, surface: str, side: str):
        s = S.SURFACES[surface]
        self.surface, self.side, self.top = surface, side, s["top"]
        self.heading = math.pi / 2 if side == "south" else -math.pi / 2
        self.fy = 1.0 if side == "south" else -1.0          # forward is +y or -y
        self.lx = -self.fy                                    # the robot's left is -x or +x
        self.edge = s["y"][0] if side == "south" else s["y"][1]
        self.depth_max = s["y"][1] - s["y"][0]

    def depth(self, y: float) -> float:
        return (y - self.edge) * self.fy

    def y_at(self, depth: float) -> float:
        return self.edge + self.fy * depth

    def base(self, line_x: float, standoff: float, lateral: float):
        """Base position that puts the line across the surface `lateral` to the robot's left."""
        return line_x - self.lx * lateral, self.edge - self.fy * standoff

    def hand_y(self, head_depth: float) -> float:
        """Where the brush hand is when the brush head is at this depth."""
        return self.y_at(head_depth - HEAD_AHEAD)


# ======================================================================================================
# Moving about
# ======================================================================================================
def _zone(y: float) -> str:
    return "south" if y < -1.2 else "north" if y > -0.1 else "lane"


def travel(w, x: float, y: float, heading: float):
    """Drive to a pose. Sideways moves in front of a surface are direct; anything else goes through the lane,
    and the robot turns only at the turning spot, where the tools it carries cannot reach anything."""
    b = w.observe()["base"]
    turn = abs(math.remainder(heading - b["heading"], 2 * math.pi))
    if turn < 0.05 and _zone(b["y"]) == _zone(y) and _zone(y) != "lane":
        return w.drive_to(x, y, heading)
    w.drive_to(LANE_X, b["y"], b["heading"])
    if turn >= 0.05:
        w.drive_to(LANE_X, TURN_Y, b["heading"])
        w.drive_to(LANE_X, TURN_Y, heading)
    w.drive_to(LANE_X, y, heading)
    return w.drive_to(x, y, heading)


def _in_robot_frame(w, arm: str):
    """Where a hand is relative to the base: (forward, to the left)."""
    obs = w.observe()
    b, h = obs["base"], obs[arm + "_hand"]
    c, s = math.cos(b["heading"]), math.sin(b["heading"])
    dx, dy = h["x"] - b["x"], h["y"] - b["y"]
    return c * dx + s * dy, -s * dx + c * dy


def _hand_world(w, forward: float, lateral: float):
    b = w.observe()["base"]
    c, s = math.cos(b["heading"]), math.sin(b["heading"])
    return b["x"] + c * forward - s * lateral, b["y"] + s * forward + c * lateral


def _carry_brush(w, top: float = S.TABLE["top"]):
    """Brush hand pulled in and raised, so the head clears whatever stands on a surface."""
    x, y = _hand_world(w, 0.45, BRUSH_LATERAL)
    yaw = w.observe()["left_hand"]["yaw"]
    w.move_arm("left", x, y, top + BRUSH_OVER, yaw)


# ======================================================================================================
# Tools: fetching, setting the bin down, taking it up again
# ======================================================================================================
def fetch_tools(w, tools=("brush", "bin")):
    """Stand at the tool station and take the brush with the left hand and the bin with the right."""
    sx, sy, sh = S.STATION["stand"]
    travel(w, LANE_X, sy, sh)
    w.drive_to(sx, sy, sh)
    for arm, tool in (("left", "brush"), ("right", "bin")):
        if tool not in tools or w.observe()[arm + "_hand"]["holding"] == tool:
            continue
        x, y, z = _tool_handle(w, tool)
        yaw = w.observe()[arm + "_hand"]["yaw"]
        w.move_arm(arm, x, y, z + HOVER, yaw)
        w.move_arm(arm, x, y, z + 0.004, yaw)
        w.grasp(arm)
        w.move_arm(arm, x, y, z + 0.10, yaw)
    w.drive_to(LANE_X, sy, sh)
    w.set_torso(TORSO)
    if w.observe()["left_hand"]["holding"] == "brush":
        _carry_brush(w)


class Bin:
    """Setting the bin down against an edge and taking it up again. Remembers where it stands."""

    BAR_TO_CENTRE = S.BIN["hx"] + S.BIN["handle"]      # 0.19: the held bin's centre is this far left of the hand

    def __init__(self):
        self.spot = None        # (base x, base y, heading, line x, Side) of where the bin stands, or None while it is carried

    def set_down(self, w, side: Side, line_x: float) -> None:
        """Carry the bin to the edge of a surface and stand it on the floor against that edge, centred on the line."""
        forward, lateral = _in_robot_frame(w, "right")                # where the hand holds the bar, measured, not assumed
        bx, by = side.base(line_x, forward + S.BIN["hy"] + 0.01, lateral + self.BAR_TO_CENTRE)
        travel(w, bx, by - side.fy * RETREAT, side.heading)
        w.drive_to(bx, by, side.heading)
        h = w.observe()["right_hand"]
        z = S.BIN["height"] - 0.006                                   # the bar's height when the bin stands on the floor
        w.move_arm("right", h["x"], h["y"], z, h["yaw"])
        w.release("right")
        ROOM.put_down("bin", h["x"], h["y"], z)
        w.move_arm("right", h["x"], h["y"], z + 0.12, h["yaw"])
        self.spot = (bx, by, side.heading, line_x, side)
        w.drive_to(bx, by - side.fy * RETREAT, side.heading)

    def take_up(self, w) -> bool:
        """Stand where the bin was set down, find its handle, take it."""
        bx, by, heading, _, side = self.spot
        travel(w, bx, by - side.fy * RETREAT, heading)
        w.drive_to(bx, by, heading)
        yaw = w.observe()["right_hand"]["yaw"]
        for _ in range(2):
            x, y, z = _tool_handle(w, "bin")
            w.move_arm("right", x, y, z + 0.12, yaw)
            w.move_arm("right", x, y, z + 0.004, yaw)
            if w.grasp("right")["holding"] == "bin":
                h = w.observe()["right_hand"]
                w.move_arm("right", h["x"], h["y"], z + 0.10, yaw)
                w.drive_to(bx, by - side.fy * RETREAT, heading)
                self.spot = None
                return True
            w.release("right")
        w.drive_to(bx, by - side.fy * RETREAT, heading)
        return False

    @staticmethod
    def centre_for(line_x: float, o, objects: dict) -> float:
        """Where to centre the bin for a stroke along `line_x` that carries piece `o`: under the swath, shifted
        towards whichever end of the head carries trash."""
        riding = [k for k in objects.values() if k["trash"] and k["where"] == o["where"] and abs(k["x"] - line_x) < HEAD_HALF + 0.02]
        middle = (min(k["x"] - k["r"] for k in riding) + max(k["x"] + k["r"] for k in riding)) / 2 if riding else line_x
        return line_x + max(-0.03, min(0.03, middle - line_x))

    def serves(self, side: Side, line_x: float, o) -> bool:
        """Is the bin standing where a stroke along this line would drop the piece into it?"""
        inner = S.BIN["hx"] - S.BIN["wall"]
        return (self.at(side) and abs(self.spot[3] - line_x) <= inner - HEAD_HALF
                and abs(self.spot[3] - o["x"]) <= inner - min(o["r"], 0.05) - 0.02)

    def at(self, side: Side) -> bool:
        return self.spot is not None and self.spot[4].surface == side.surface and self.spot[4].side == side.side


# ======================================================================================================
# Strokes
# ======================================================================================================
def _pull(w, side: Side, line_x: float, standoff: float, from_depth: float, to_depth: float):
    """One stroke: stand `standoff` from the edge with the brush on the line, put the brush head down at
    `from_depth` and pull it to `to_depth` (negative: beyond the edge). The arm pulls the hand in as far
    as it goes; if that is not far enough the base rolls back for the rest with the brush still down.
    Ends with the brush lifted and the robot one step back from where it stood."""
    bx, by = side.base(line_x, standoff, BRUSH_LATERAL)
    travel(w, bx, by - side.fy * RETREAT, side.heading)
    _carry_brush(w, side.top)
    w.drive_to(bx, by, side.heading)
    yaw = w.observe()["left_hand"]["yaw"]
    hand = lambda depth: depth + standoff - HEAD_AHEAD                 # hand's distance from the base centre for a head depth
    start = min(hand(from_depth), HAND_FAR)                            # as deep as the arm reaches from here
    end = max(hand(to_depth), HAND_NEAR)
    y_of = lambda forward: side.edge + side.fy * (forward - standoff)
    w.move_arm("left", line_x, y_of(start), side.top + BRUSH_OVER, yaw)
    w.move_arm("left", line_x, y_of(start), side.top + BRUSH_DOWN, yaw)
    w.move_arm("left", line_x, y_of(end), side.top + BRUSH_DOWN, yaw)
    if end > hand(to_depth) + 0.005:
        w.drive_to(bx, by - side.fy * (end - hand(to_depth)), side.heading)
    h = w.observe()["left_hand"]
    w.move_arm("left", h["x"], h["y"], side.top + BRUSH_OVER, yaw)
    w.drive_to(bx, by - side.fy * RETREAT, side.heading)
    ROOM.pulled(side, line_x, start - standoff + HEAD_AHEAD, to_depth)


def _behind(o, tight: bool = False) -> float:
    """How far behind a piece's centre the brush head comes down: with room to spare, or as close as it can."""
    return 0.8 * min(o["r"], 0.05) + BRISTLES + 0.008 if tight else min(o["r"], 0.06) + BRISTLES + 0.03


def gather(w, side: Side, line_x: float, start: float) -> None:
    """Pull a deep piece towards the edge, to where the final stroke can reach it. No bin involved."""
    standoff = max(GATHER_MIN, min(GATHER_MAX, HAND_FAR + HEAD_AHEAD - start))
    _pull(w, side, line_x, standoff, start, GATHER_TO)


def into_bin(w, side: Side, line_x: float, start: float) -> None:
    """The final stroke: over the edge, into the bin standing there."""
    _pull(w, side, line_x, SWEEP_STANDOFF, start, -PAST_EDGE)


FINAL_REACH = HAND_FAR + HEAD_AHEAD - SWEEP_STANDOFF      # 0.29: how deep the final stroke can start
GATHER_REACH = HAND_FAR + HEAD_AHEAD - GATHER_MIN         # 0.49: how deep a gathering stroke can start


# ======================================================================================================
# Deciding where to sweep
# ======================================================================================================
def _head_fits(surface: str, x: float) -> bool:
    """The sofa's seat lies between its arms: the brush head has to come down between them."""
    s = S.SURFACES[surface]
    return surface != "sofa" or s["x"][0] + HEAD_HALF + 0.015 <= x <= s["x"][1] - HEAD_HALF - 0.015


def plan(o, objects: dict):
    """Choose the edge and the line for one piece of trash. Returns (Side, line x, depth at which the brush
    comes down, blockers, tall things under the handle).

    The stroke moves everything in a strip 0.22 wide from where the bristles come down to the edge. A
    personal item whose footprint reaches into that strip in front of the piece blocks it; one behind the
    piece only limits how far behind the brush may come down. The line may sit beside the piece: to keep
    a personal item out of the strip, and, for a piece taller than the handle's clearance, to bring it
    under the outer part of the head. Prefers no blockers, then a reachable start, then nothing under
    the handle, then the nearer edge, then a line through the piece."""
    surface = o["where"][3:]
    here = [k for k in objects.values() if k["where"] == o["where"] and k["name"] != o["name"]]
    slack = HEAD_HALF - 0.02                                           # the piece's centre stays 2 cm inside the head's end
    beside = 0.013 + min(o["r"], 0.05) + 0.02                          # how far beside the line a tall piece must sit
    offsets = [dx for dx in (0.0, 0.03, -0.03, 0.06, -0.06, beside, -beside, slack, -slack)
               if o["height"] <= HANDLE_CLEAR or abs(dx) >= beside]
    best = None
    for side_name in (("south", "north") if surface == "table" else ("south",)):
        side = Side(surface, side_name)
        depth = side.depth(o["y"])
        for dx in offsets:
            line_x = o["x"] + dx
            if not _head_fits(surface, line_x):
                continue
            start, blockers, under_handle = depth + _behind(o), [], []
            for k in here:
                outside = abs(k["x"] - line_x) - HEAD_HALF            # how far its centre lies beside the strip
                reach = k["r"] + KEEP_CLEAR
                if outside >= reach:
                    continue
                front = side.depth(k["y"]) - (reach if outside <= 0 else math.sqrt(reach ** 2 - outside ** 2))
                if k["trash"]:
                    if k["height"] > HANDLE_CLEAR and abs(k["x"] - line_x) < 0.013 + k["r"] + 0.015 and side.depth(k["y"]) < depth:
                        under_handle.append(k["name"])
                elif front - BRISTLES < depth + _behind(o, tight=True):
                    blockers.append(k["name"])                        # in front of the piece, or too close behind it
                else:
                    start = min(start, front - BRISTLES)              # behind: come down short of it
            cost = (len(blockers), start > GATHER_REACH, len(under_handle), round(depth, 2), abs(dx))
            if best is None or cost < best[0]:
                best = (cost, side, line_x, start, blockers, under_handle)
    if best is None:                                                   # no line fits (a piece jammed against a sofa arm)
        side = Side(surface, "south")
        return side, o["x"], side.depth(o["y"]) + _behind(o), ["the sofa's arm"], []
    return best[1:]


def _touches(k, x0: float, x1: float, y0: float, y1: float) -> bool:
    """Does the footprint of thing `k` (a circle) come within KEEP_CLEAR of the rectangle?"""
    dx = max(x0 - k["x"], 0.0, k["x"] - x1)
    dy = max(y0 - k["y"], 0.0, k["y"] - y1)
    return math.hypot(dx, dy) < k["r"] + KEEP_CLEAR


def plan_nudge(o, objects: dict):
    """A piece with a personal item between it and every edge: find a sideways push along the surface that
    brings it to where a stroke is clear. Returns (Side, direction +1/-1 along x, distance, where the head
    comes down) for the shortest such push, or None. The brush head lies beside the piece, end on, and the
    base rolls sideways; nothing personal may lie in the strip the head and the piece pass through."""
    surface = o["where"][3:]
    s = S.SURFACES[surface]
    here = [k for k in objects.values() if k["where"] == o["where"] and k["name"] != o["name"]]
    best = None
    for side_name in (("south", "north") if surface == "table" else ("south",)):
        side = Side(surface, side_name)
        if side.depth(o["y"]) > FINAL_REACH:          # reached from the sweeping distance, clear of a bin at the edge
            continue
        for sign in (1.0, -1.0):
            head_x = o["x"] - sign * (HEAD_HALF + min(o["r"], 0.06) + 0.025)
            for dist in (0.12, 0.18, 0.24, 0.30, 0.36):
                x_new = o["x"] + sign * dist
                if not s["x"][0] + 0.07 <= x_new <= s["x"][1] - 0.07:
                    break
                ends = sorted((head_x - sign * HEAD_HALF, head_x + sign * (HEAD_HALF + dist)))
                if not (_head_fits(surface, ends[0] + HEAD_HALF) and _head_fits(surface, ends[1] - HEAD_HALF)):
                    break
                path = sorted((o["x"] - sign * o["r"], x_new + sign * (o["r"] + 0.02)))
                in_strip = [k for k in here if
                            (not k["trash"] and (_touches(k, ends[0], ends[1], o["y"] - BRISTLES, o["y"] + BRISTLES)
                                                 or _touches(k, path[0], path[1], o["y"] - o["r"], o["y"] + o["r"])))
                            or (k["trash"] and k["height"] > 0.02
                                and _touches(k, head_x - HEAD_HALF, head_x + HEAD_HALF, o["y"] - BRISTLES, o["y"] + BRISTLES))]
                if in_strip:
                    break
                moved = dict(o, x=x_new)
                if not plan(moved, {**objects, o["name"]: moved})[3] and (best is None or dist < best[2]):
                    best = (side, sign, dist, head_x)
    return best


def nudge(w, side: Side, sign: float, dist: float, head_x: float, o) -> None:
    depth = side.depth(o["y"])
    bx, by = side.base(head_x, SWEEP_STANDOFF, BRUSH_LATERAL)
    travel(w, bx, by - side.fy * RETREAT, side.heading)
    _carry_brush(w, side.top)
    w.drive_to(bx, by, side.heading)
    yaw = w.observe()["left_hand"]["yaw"]
    w.move_arm("left", head_x, side.hand_y(depth), side.top + BRUSH_OVER, yaw)
    w.move_arm("left", head_x, side.hand_y(depth), side.top + BRUSH_DOWN, yaw)
    w.drive_to(bx + sign * dist, by, side.heading)
    h = w.observe()["left_hand"]
    w.move_arm("left", h["x"], h["y"], side.top + BRUSH_OVER, yaw)
    w.drive_to(bx + sign * dist, by - side.fy * RETREAT, side.heading)
    ROOM.pushed(o["name"], head_x + sign * (dist + HEAD_HALF + min(o["r"], 0.04)))     # it lies against the end of the head


# ======================================================================================================
# The reference run
# ======================================================================================================
def _trash_left(w) -> list:
    return [o for o in _objects(w).values() if o["trash"] and o["where"] in ("on_table", "on_sofa")]


def sweep_all(w, limit: int | None = None) -> dict:
    """Sweep every reachable piece of trash into the bin. `limit` stops after that many pieces (for the
    stop-early baseline). Returns a short report of what was skipped and why."""
    report = dict(swept=[], skipped={})
    bin_ = Bin()
    tries: dict[str, int] = {}
    nudges: dict[str, int] = {}

    def needs_gathering(o, objects) -> bool:
        _, _, start, blockers, _ = plan(o, objects)
        return not blockers and FINAL_REACH < start <= GATHER_REACH

    def gather_piece(name) -> None:
        for _ in range(2):                                        # a second pull if the first left it short
            objects = _objects(w)
            o = objects[name]
            if o["where"] not in ("on_table", "on_sofa") or not needs_gathering(o, objects):
                return
            side, line_x, start, _, _ = plan(o, objects)
            if bin_.at(side) and abs(side.base(line_x, 0, BRUSH_LATERAL)[0] - bin_.spot[3]) < 0.48:
                if not bin_.take_up(w):                           # the bin stands where the robot has to stand:
                    return
                bin_.set_down(w, side, line_x + side.lx * 0.13)   # move it just beyond the line
            gather(w, side, line_x, start)

    # 1. gather the deep pieces while the bin is still at the station: the robot has to stand close for that
    objects = _objects(w)
    deep = [o["name"] for o in _trash_left(w) if needs_gathering(o, objects)]
    fetch_tools(w, tools=("brush",) if deep else ("brush", "bin"))
    for name in deep:
        gather_piece(name)
    if deep:
        fetch_tools(w, tools=("bin",))

    # 2. one piece after the other: bin to the edge, stroke, check
    while limit is None or len(report["swept"]) < limit:
        objects = _objects(w)
        todo = []
        for o in _trash_left(w):
            side, line_x, start, blockers, under_handle = plan(o, objects)
            why = ("a personal item is in the brush's path: " + ", ".join(blockers)) if blockers else \
                  "out of the brush's reach" if start > GATHER_REACH else \
                  "did not go in after %d strokes" % MAX_TRIES if tries.get(o["name"], 0) >= MAX_TRIES else None
            if why:
                report["skipped"][o["name"]] = why
            else:
                todo.append((o, side, line_x, start, len(under_handle)))
        if not todo:
            # what is left has a personal item in its way: push one such piece sideways into the clear and look again
            pushed = False
            for o in _trash_left(w):
                if "personal item" in report["skipped"].get(o["name"], "") and nudges.get(o["name"], 0) < 2:
                    found = plan_nudge(o, objects)
                    if found:
                        nudges[o["name"]] = nudges.get(o["name"], 0) + 1
                        nudge(w, *found, o)
                        pushed = True
                        break
            if pushed:
                continue
            break

        def order(t):     # a piece the bin already serves, then the same edge, then nothing under the handle, then the nearest
            o, side, line_x, _, under = t
            return (not bin_.serves(side, line_x, o), not bin_.at(side), under, side.depth(o["y"]))
        o, side, line_x, start, _ = min(todo, key=order)
        if needs_gathering(o, objects):                           # it was pushed deeper since the first round
            gather_piece(o["name"])
            tries[o["name"]] = tries.get(o["name"], 0) + 1
            continue
        if not bin_.serves(side, line_x, o):
            if bin_.spot is not None and not bin_.take_up(w):
                report["skipped"]["bin"] = "could not take the bin up again"
                break
            bin_.set_down(w, side, Bin.centre_for(line_x, o, objects))
        into_bin(w, side, line_x, start)
        tries[o["name"]] = tries.get(o["name"], 0) + 1
        if _objects(w)[o["name"]]["where"] == "in_bin":
            report["swept"].append(o["name"])
            report["skipped"].pop(o["name"], None)
    return report


def reference_privileged(w):
    """The scripted controller, told where everything is (privileged setting)."""
    global ROOM
    ROOM = Told()
    try:
        sweep_all(w)
    except RuntimeError:          # out of robot time: what is in the bin by now counts
        pass
    return w.score()


def reference(w):
    """The reference run: the same controller working from what the agent gets in the standard setting.
    It looks at the room through the head camera first, then fetches the tools and sweeps."""
    global ROOM
    try:
        ROOM = Seen(w)
        sweep_all(w)
    except RuntimeError:
        pass
    finally:
        ROOM = Told()
    return w.score()


# ======================================================================================================
# Baselines
# ======================================================================================================
def do_nothing(w):
    return w.score()


def _room_for(w):
    """Told in the privileged setting, Seen (through the camera) in the standard one."""
    return Told() if "objects" in w.observe() else Seen(w)


def stop_early(w):
    """Fetch the tools, then stop."""
    global ROOM
    try:
        ROOM = _room_for(w)
        fetch_tools(w)
    except RuntimeError:
        pass
    finally:
        ROOM = Told()
    return w.score()


def stop_after_one(w):
    """Sweep one piece of trash into the bin, then stop."""
    global ROOM
    try:
        ROOM = _room_for(w)
        sweep_all(w, limit=1)
    except RuntimeError:
        pass
    finally:
        ROOM = Told()
    return w.score()


POLICIES = dict(do_nothing=do_nothing, stop_early=stop_early, stop_after_one=stop_after_one,
                reference_privileged=reference_privileged, reference=reference)
