"""Seeing the room through the robot's head camera: the part of the reference that replaces object positions.

Everything here works from what the standard setting gives an agent and nothing else:

  world.camera("head")     a colour picture, a depth image in metres, and the calibration (f, cx, cy, cam_pos, cam_rot)
  world.observe()          the robot's own state: base pose, head angles, hand positions, what the hands hold
  world.get_task()         the floor plan: table and sofa-seat rectangles with their heights, obstacles, tool shelf
  world.drive_to / look    to put the camera somewhere

It never reads object positions, names or kinds from the simulator.

Two modes:

  depth=True (default)   Every pixel becomes a point in the room (depth along the viewing ray). A thing on a
                         surface is the set of points a few millimetres or more above it; grouped top-down,
                         measured, and compared with examples of the kinds of things named in the task.
  depth=False            Colour pictures only, for the ablation without depth. A pixel's viewing ray,
                         cam_pos + t * cam_rot @ ((u - cx) / f, -(v - cy) / f, -1), is met with the plane of
                         the surface, whose height the floor plan gives. A pixel there is bare surface if it has
                         the surface's colour (allowing for shade), otherwise a thing. A thing that stands up
                         hides the surface behind it, so in one picture its patch is its footprint plus a tail
                         pointing away from the camera; a spot belongs to a footprint only if no picture shows
                         it bare. Where a surface can only be seen from one side (the sofa), the tail is cut
                         off using how high that kind of thing stands.

What it knows beyond the floor plan: a few sizes from the task description (constants below), and what the
kinds of things look like, as a table of examples in `perception_model.json` (one table per mode). The tables
were built by `perception_eval.py --train` from pictures taken in OTHER rooms (seeds 1000 and up) and are
evaluated on seeds 1 to 40; an agent could build the same tables by looking.

Main calls:
    survey(world, depth=True)        -> dict(detections=[...], unseen={surface: share}, views=n, robot_time_s=t)
    locate_tools(world, depth=True)  -> dict(brush=dict(x, y, z, handle_yaw, closing_yaw), bin=dict(...))
    drive(world, x, y, heading) -> bool      collision-free driving on the floor plan (used by both)

The survey assumes the arms are in their rest posture (hands in front of the chest), as they are whenever
the controller is not moving them. Only numpy is needed, so the same file runs in the agent's container.
"""
from __future__ import annotations

import heapq
import json
import math
from pathlib import Path

import numpy as np

# ---- sizes from the task description -------------------------------------------------------------
BRUSH_GRIP_UP = 0.060        # the brush handle runs this far above whatever the bristles rest on
BRUSH_HANDLE_R = 0.013
BRUSH_KNOB_TO_GRIP = 0.07    # the place to hold the brush, measured from the red knob on the end of its handle
BRUSH_HANDLE_LEN = 0.30
BIN_HALF = (0.15, 0.10)      # half length, half width of the bin
BIN_HEIGHT = 0.36
BIN_BAR_OFF = 0.04           # the bar handle sits this far outside one short side ...
BIN_BAR_DROP = 0.012         # ... and this far below the rim
BIN_BAR_R = 0.011

# ---- the robot's own shape, for staying clear of furniture (base frame: x forward, y left) ----------
BASE_CIRCLES = ((0.14, 0.0, 0.36), (-0.14, 0.0, 0.36))
ARMS_EMPTY = ((0.50, 0.0, 0.33),)
ARMS_TOOLS = ((0.60, 0.03, 0.43),)
HEAD_FWD = 0.12              # the head's pan axis is this far in front of the base centre
CAM_OFF = 0.115              # the camera sits this far in front of the pan axis
CAM_HEIGHT0 = 0.995          # camera height with the torso fully down

# ---- mapping -------------------------------------------------------------------------------------
CELL = 0.005                 # top-down grid over a surface
VIEW_DISTS = (1.05, 0.95, 0.85, 0.75, 0.65, 0.58)   # camera to the near edge of what it looks at: as far back as the room allows
VIEW_STEP = 0.40             # distance between neighbouring places to look from, along one side of a surface
MIN_CELLS = 12               # 3 cm2: smaller than anything that lies around here
MIN_H = 0.003                # with depth: a point this far above a surface belongs to a thing lying on it
MAX_H = 0.30
CHROMA_TOL = 0.02            # how far a pixel's colour mix may be from the surface's and still be surface
SHADE = (0.66, 1.07)         # ... and how much darker (in shade) or brighter it may be
MODEL_FILE = Path(__file__).with_name("perception_model.json")


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


# ==================================================================================================
# Driving without bumping into the furniture
# ==================================================================================================
class Floor:
    """The floor plan as boxes, and the question 'may the robot stand here, turned like this?'."""

    def __init__(self, task: dict, tools_in_hand: bool, margin: float = 0.03):
        self.boxes = [(o["x"][0], o["x"][1], o["y"][0], o["y"][1]) for o in task["obstacles"]]
        w = task["room"]["walls"]
        self.x0, self.x1, self.y0, self.y1 = w["x"][0], w["x"][1], w["y"][0], w["y"][1]
        self.circles = BASE_CIRCLES + (ARMS_TOOLS if tools_in_hand else ARMS_EMPTY)
        self.margin = margin

    def free(self, x: float, y: float, th: float) -> bool:
        c, s = math.cos(th), math.sin(th)
        for cx, cy, r in self.circles:
            px, py, r = x + c * cx - s * cy, y + s * cx + c * cy, r + self.margin
            if px - r < self.x0 or px + r > self.x1 or py - r < self.y0 or py + r > self.y1:
                return False
            for bx0, bx1, by0, by1 in self.boxes:
                dx, dy = max(bx0 - px, 0.0, px - bx1), max(by0 - py, 0.0, py - by1)
                if dx * dx + dy * dy < r * r:
                    return False
        return True

    def line_free(self, a, b) -> bool:
        """The straight move from pose a to pose b, as drive_to makes it (position and heading together)."""
        dth = _wrap(b[2] - a[2])
        n = max(int(math.hypot(b[0] - a[0], b[1] - a[1]) / 0.03), int(abs(dth) / 0.05), 1)
        return all(self.free(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, a[2] + dth * i / n) for i in range(n + 1))


def plan(floor: Floor, start, goal, step: float = 0.10, headings: int = 16):
    """A* over (x, y, heading) on a grid; returns a short list of poses to drive through, or None."""
    if floor.line_free(start, goal):
        return [tuple(goal)]
    dth = 2 * math.pi / headings
    node = lambda p: (int(round(p[0] / step)), int(round(p[1] / step)), int(round(p[2] / dth)) % headings)
    pose = lambda n: (n[0] * step, n[1] * step, _wrap(n[2] * dth))
    cache: dict = {}

    def ok(n):
        if n not in cache:
            cache[n] = floor.free(*pose(n))
        return cache[n]

    def nearest_free(p):
        n0 = node(p)
        cands = sorted(((di * di + dj * dj + 0.2 * abs(dk), (n0[0] + di, n0[1] + dj, (n0[2] + dk) % headings))
                        for di in range(-3, 4) for dj in range(-3, 4) for dk in (0, 1, -1, 2, -2)), key=lambda t: t[0])
        for _, n in cands:
            if ok(n) and floor.line_free(p, pose(n)):
                return n
        return None

    s, g = nearest_free(start), nearest_free(goal)
    if s is None or g is None:
        return None
    gp = pose(g)
    h = lambda n: math.hypot(n[0] * step - gp[0], n[1] * step - gp[1]) + 0.25 * abs(_wrap(n[2] * dth - gp[2]))
    dist, prev, heap = {s: 0.0}, {}, [(h(s), s)]
    moves = [(di, dj, 0, step * math.hypot(di, dj)) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj] + [(0, 0, 1, 0.25 * dth), (0, 0, -1, 0.25 * dth)]
    while heap:
        _, n = heapq.heappop(heap)
        if n == g:
            break
        for di, dj, dk, cost in moves:
            m = (n[0] + di, n[1] + dj, (n[2] + dk) % headings)
            if not ok(m):
                continue
            nd = dist[n] + cost
            if nd < dist.get(m, 1e9):
                dist[m], prev[m] = nd, n
                heapq.heappush(heap, (nd + h(m), m))
    if g not in dist:
        return None
    path = [g]
    while path[-1] != s:
        path.append(prev[path[-1]])
    poses = [tuple(start)] + [pose(n) for n in reversed(path)] + [tuple(goal)]
    out, i = [], 0
    while i < len(poses) - 1:                      # cut corners: go straight to the farthest pose that can be reached in one move
        j = len(poses) - 1
        while j > i + 1 and not floor.line_free(poses[i], poses[j]):
            j -= 1
        out.append(poses[j])
        i = j
    return out


def _tools_in_hand(state: dict) -> bool:
    return bool(state["left_hand"]["holding"] or state["right_hand"]["holding"])


def drive(world, x: float, y: float, heading: float, task: dict | None = None) -> bool:
    """Drive to a pose on a path that keeps the base, the arms and whatever they hold clear of the furniture."""
    task = task or world.get_task()
    st = world.observe()
    floor = Floor(task, _tools_in_hand(st))
    b = st["base"]
    path = plan(floor, (b["x"], b["y"], b["heading"]), (x, y, heading))
    if path is None:
        return False
    for px, py, pth in path:
        if not world.drive_to(float(px), float(py), float(pth))["reached"]:
            return False
    return True


# ==================================================================================================
# One picture
# ==================================================================================================
class View:
    """A colour picture with its calibration and the robot's state when it was taken."""

    def __init__(self, cam: dict, state: dict):
        c = cam["calibration"]
        self.rgb = cam["rgb"].astype(np.float32) / 255.0
        self.h, self.w = self.rgb.shape[:2]
        self.f, self.cx, self.cy = c["f"], c["cx"], c["cy"]
        self.pos, self.R = np.asarray(c["cam_pos"], float), np.asarray(c["cam_rot"], float)
        self.state = state
        self.depth = cam.get("depth")
        u, v = np.meshgrid(np.arange(self.w, dtype=np.float64), np.arange(self.h, dtype=np.float64))
        self.dirs = np.stack(((u - self.cx) / self.f, -(v - self.cy) / self.f, -np.ones_like(u)), axis=-1) @ self.R.T
        self.robot = self._robot_mask()

    def project(self, pts: np.ndarray):
        """Room points -> pixel coordinates u, v and the distance along the view (negative: behind the camera)."""
        local = (np.asarray(pts, float) - self.pos) @ self.R
        z = -local[:, 2]
        zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
        return self.cx + self.f * local[:, 0] / zs, self.cy - self.f * local[:, 1] / zs, z

    def points(self) -> np.ndarray:
        """With the depth image: the point in the room that each pixel shows, as (H, W, 3)."""
        return self.pos + self.dirs * np.asarray(self.depth, np.float64)[..., None]

    def not_robot_points(self, P: np.ndarray) -> np.ndarray:
        """With depth: False for points on the robot's own hands or on what they hold."""
        keep = np.ones(P.shape[:-1], bool)
        b = self.state["base"]
        for arm in ("left", "right"):
            hnd = self.state[arm + "_hand"]
            d = np.hypot(P[..., 0] - hnd["x"], P[..., 1] - hnd["y"])
            keep &= ~((d < 0.13) & (P[..., 2] > hnd["z"] - 0.06))
            if hnd["holding"]:                         # a held tool reaches away from the body, below the hand
                out = np.array([hnd["x"] - b["x"], hnd["y"] - b["y"]])
                out /= max(np.linalg.norm(out), 1e-6)
                rel = np.stack((P[..., 0] - hnd["x"], P[..., 1] - hnd["y"]), axis=-1)
                along, across = rel @ out, np.abs(rel @ np.array([-out[1], out[0]]))
                keep &= ~((along > -0.25) & (along < 0.42) & (across < 0.42) & (P[..., 2] > hnd["z"] - 0.42))
        return keep

    def on_plane(self, height: float):
        """Where each pixel's viewing ray meets the horizontal plane at `height`: x, y and whether it does."""
        dz = self.dirs[..., 2]
        t = (height - self.pos[2]) / np.where(np.abs(dz) < 1e-9, -1e-9, dz)
        ok = (dz < -1e-6) & (t > 0)
        return self.pos[0] + t * self.dirs[..., 0], self.pos[1] + t * self.dirs[..., 1], ok

    def _robot_mask(self) -> np.ndarray:
        """Pixels that may show the robot itself. With the arms at rest each arm comes into the picture from
        its lower corner and ends at the hand; the region is bounded by a line fixed to where the hand is
        seen (measured once on pictures of the robot's own arms)."""
        mask = np.zeros((self.h, self.w), bool)
        u, v = np.meshgrid(np.arange(self.w), np.arange(self.h))
        b = self.state["base"]
        for arm, sign in (("left", 1), ("right", -1)):
            hnd = self.state[arm + "_hand"]
            pu, pv, pz = self.project(np.array([[hnd["x"], hnd["y"], hnd["z"]], [hnd["x"], hnd["y"], hnd["z"] + 0.25]]))
            if pz[0] <= 0:
                continue
            edge = pu[0] + sign * (75 - 0.40 * np.maximum(0.0, pv[0] - 60 - v))
            side = (u < edge) if sign > 0 else (u > edge)
            mask |= side & (v > pv[1] - 110)
            if hnd["holding"]:                         # a held tool: a box around where it hangs
                out = np.array([hnd["x"] - b["x"], hnd["y"] - b["y"]])
                out /= max(np.linalg.norm(out), 1e-6)
                lat = np.array([-out[1], out[0]])
                if hnd["holding"] == "brush":
                    corners = [(a, s, dz) for a in (-0.12, 0.34) for s in (-0.14, 0.14) for dz in (-0.14, 0.03)]
                else:
                    corners = [(a, s, dz) for a in (-0.16, 0.16) for s in (-0.10, 0.42) for dz in (-0.40, 0.04)]
                    lat = lat * (1 if arm == "right" else -1)      # the bin hangs towards the other hand
                pts = np.array([[hnd["x"] + out[0] * a + lat[0] * s, hnd["y"] + out[1] * a + lat[1] * s, hnd["z"] + dz] for a, s, dz in corners])
                qu, qv, qz = self.project(pts)
                if (qz > 0).all():
                    mask |= (u > qu.min() - 8) & (u < qu.max() + 8) & (v > qv.min() - 8) & (v < qv.max() + 8)
        return mask


def split_surface(view: View, x: np.ndarray, y: np.ndarray, inside: np.ndarray):
    """Among the pixels that look at a surface (`inside`), which show it bare and which show a thing on it.
    The surface's colour is the commonest colour there; shade changes its brightness but not its mix."""
    rgb = view.rgb
    tot = rgb.sum(-1) + 1e-6
    if inside.sum() < 200:
        return np.zeros_like(inside), np.zeros_like(inside)
    ref = np.median(rgb[inside], axis=0)
    mix = np.linalg.norm(rgb / tot[..., None] - ref / ref.sum(), axis=-1)
    k = tot / ref.sum()
    like = inside & (mix < CHROMA_TOL)
    # the light falls off smoothly across the surface: fit that, so that shade and shine are judged locally
    sel = like & (k > 0.9) & (k < 1.25)
    res = k
    x0, y0 = float(x[inside].mean()), float(y[inside].mean())
    for _ in range(2):
        if sel.sum() < 200:
            break
        idx = np.flatnonzero(sel)
        idx = idx[:: max(1, len(idx) // 20000)]
        dx, dy = x.ravel()[idx] - x0, y.ravel()[idx] - y0
        A = np.stack((np.ones_like(dx), dx, dy, dx * dx, dy * dy, dx * dy), axis=1)
        coef = np.linalg.lstsq(A, k.ravel()[idx], rcond=None)[0]
        dxa, dya = x - x0, y - y0
        fit = coef[0] + coef[1] * dxa + coef[2] * dya + coef[3] * dxa * dxa + coef[4] * dya * dya + coef[5] * dxa * dya
        res = k / np.clip(fit, 0.3, 3.0)
        sel = like & (res > 0.95) & (res < 1.05)
    bare = like & (res > SHADE[0]) & (res < SHADE[1])
    return bare, inside & ~bare


def _groups(occ: np.ndarray, min_cells: int = 1) -> list[np.ndarray]:
    """Groups of touching True cells (8-neighbourhood), each as an array of (i, j)."""
    nx, ny = occ.shape
    seen = np.zeros(occ.shape, bool)
    out = []
    for i0, j0 in zip(*np.nonzero(occ)):
        if seen[i0, j0]:
            continue
        seen[i0, j0] = True
        stack, cells = [(i0, j0)], []
        while stack:
            i, j = stack.pop()
            cells.append((i, j))
            for a in (i - 1, i, i + 1):
                for b in (j - 1, j, j + 1):
                    if 0 <= a < nx and 0 <= b < ny and occ[a, b] and not seen[a, b]:
                        seen[a, b] = True
                        stack.append((a, b))
        if len(cells) >= min_cells:
            out.append(np.array(cells))
    return out


def _join_near(groups: list[np.ndarray], gap_cells: float) -> list[np.ndarray]:
    """Merge groups of cells that come within `gap_cells` of each other."""
    groups = list(groups)
    changed = True
    while changed and len(groups) > 1:
        changed = False
        for i in range(len(groups) - 1, 0, -1):
            for j in range(i):
                a, b = groups[i][:: max(1, len(groups[i]) // 300)], groups[j][:: max(1, len(groups[j]) // 300)]
                if np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)).min() <= gap_cells:
                    groups[j] = np.concatenate((groups[j], groups[i]))
                    del groups[i]
                    changed = True
                    break
            if changed:
                break
    return groups


def _fill_holes(occ: np.ndarray) -> np.ndarray:
    """Cells enclosed by occupied cells count as occupied (a pale label in the middle of a dark thing)."""
    nx, ny = occ.shape
    outside = np.zeros(occ.shape, bool)
    stack = [(i, j) for i in range(nx) for j in (0, ny - 1) if not occ[i, j]] + [(i, j) for j in range(ny) for i in (0, nx - 1) if not occ[i, j]]
    for i, j in stack:
        outside[i, j] = True
    while stack:
        i, j = stack.pop()
        for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)):
            if 0 <= a < nx and 0 <= b < ny and not occ[a, b] and not outside[a, b]:
                outside[a, b] = True
                stack.append((a, b))
    return ~outside


class SurfaceMap:
    """A top-down grid over one surface, filled from pictures taken from several places."""

    def __init__(self, name: str, rect: dict, shrink: float = 0.008):
        self.name, self.top = name, rect["top"]
        self.x0, self.x1 = rect["x"][0] + shrink, rect["x"][1] - shrink
        self.y0, self.y1 = rect["y"][0] + shrink, rect["y"][1] - shrink
        self.nx, self.ny = int(math.ceil((self.x1 - self.x0) / CELL)), int(math.ceil((self.y1 - self.y0) / CELL))
        gx, gy = np.meshgrid(self.x0 + (np.arange(self.nx) + 0.5) * CELL, self.y0 + (np.arange(self.ny) + 0.5) * CELL, indexing="ij")
        self.centres = np.stack((gx.ravel(), gy.ravel(), np.full(gx.size, self.top)), axis=1)
        self.views: list[View] = []
        self.labels: list[np.ndarray] = []         # per view and cell: -1 not seen, 0 bare, 1 a thing in the way
        self.pix: list[np.ndarray] = []            # per view and cell: index of the pixel that looks at it
        self.verdict: list[np.ndarray] = []        # per view and pixel: -1 does not look at this surface, 0 bare, 1 thing

    def add(self, view: View):
        x, y, ok = view.on_plane(self.top)
        inside = ok & (x > self.x0) & (x < self.x1) & (y > self.y0) & (y < self.y1) & ~view.robot
        bare, thing = split_surface(view, x, y, inside)
        u, v, z = view.project(self.centres)
        ui, vi = np.rint(u).astype(int), np.rint(v).astype(int)
        vis = (z > 0) & (ui >= 0) & (ui < view.w) & (vi >= 0) & (vi < view.h)
        ui, vi = np.clip(ui, 0, view.w - 1), np.clip(vi, 0, view.h - 1)
        vis &= ~view.robot[vi, ui]
        label = np.full(len(u), -1, np.int8)
        label[vis & bare[vi, ui]] = 0
        label[vis & thing[vi, ui]] = 1
        verdict = np.full((view.h, view.w), -1, np.int8)
        verdict[bare] = 0
        verdict[thing] = 1
        self.verdict.append(verdict)
        self.views.append(view)
        self.labels.append(label.reshape(self.nx, self.ny))
        self.pix.append((vi * view.w + ui).reshape(self.nx, self.ny))

    def times_seen(self) -> np.ndarray:
        return sum((lab >= 0).astype(int) for lab in self.labels) if self.labels else np.zeros((self.nx, self.ny), int)

    def footprints(self) -> np.ndarray:
        """Cells that some picture shows covered and no picture shows bare."""
        if not self.labels:
            return np.zeros((self.nx, self.ny), bool)
        covered = np.any([lab == 1 for lab in self.labels], axis=0)
        # A picture counts as showing a cell bare only if it shows the cell's neighbours bare too: a pixel is
        # about as wide as a cell, and thin things (the frame of a pair of glasses) would otherwise be lost.
        bare = np.zeros(covered.shape, bool)
        for lab in self.labels:
            thing = np.pad(lab == 1, 1)
            near_thing = np.zeros(covered.shape, bool)
            for di in (0, 1, 2):
                for dj in (0, 1, 2):
                    near_thing |= thing[di:di + self.nx, dj:dj + self.ny]
            bare |= (lab == 0) & ~near_thing
        return _fill_holes(covered & ~bare)

    def detections(self) -> list[dict]:
        occ = self.footprints()
        seen = self.times_seen()
        groups = self._merge_fragments(_groups(occ, 1))
        groups = self._absorb_small([part for g in groups if len(g) >= MIN_CELLS for part in self._split_large(g)])
        own = np.zeros(occ.shape, int)
        for n, cells in enumerate(groups):
            own[cells[:, 0], cells[:, 1]] = n + 1
        patches = [_groups(lab == 1, MIN_CELLS) for lab in self.labels]      # each picture's patches: footprint plus tail
        out = []
        for n, cells in enumerate(groups):
            d = self._measure(cells)
            cols, heights, dirs = [], [], []
            for view, lab, pix, pv in zip(self.views, self.labels, self.pix, patches):
                hit = lab[cells[:, 0], cells[:, 1]] == 1
                if hit.mean() < 0.5:
                    continue
                away = np.array([d["x"], d["y"]]) - view.pos[:2]
                dirs.append(math.atan2(away[1], away[0]))
                for patch in pv:
                    owners = np.unique(own[patch[:, 0], patch[:, 1]])
                    if (n + 1) not in owners:
                        continue
                    if set(owners.tolist()) <= {0, n + 1}:        # this picture shows it apart from its neighbours
                        cols.append(view.rgb.reshape(-1, 3)[pix[patch[:, 0], patch[:, 1]]])
                        heights.append(self._height_from_tail(view, cells, patch))
                    break
            if not cols:                                  # every picture shows it run together with a neighbour: use its own cells
                for view, lab, pix in zip(self.views, self.labels, self.pix):
                    hit = lab[cells[:, 0], cells[:, 1]] == 1
                    if hit.any():
                        cols.append(view.rgb.reshape(-1, 3)[pix[cells[hit, 0], cells[hit, 1]]])
            col = np.concatenate(cols) if cols else np.zeros((1, 3))
            bins = np.clip((col * 3).astype(int), 0, 2)
            hist = np.bincount(bins[:, 0] * 9 + bins[:, 1] * 3 + bins[:, 2], minlength=27) / len(col)
            # were the pictures taken from opposite sides? then the tails cancelled out and the footprint is trustworthy
            spread = max((abs(_wrap(a - b)) for a in dirs for b in dirs), default=0.0)
            d.update(height=round(float(np.median(heights)) if heights else 0.0, 4),
                     colour=[round(float(c), 3) for c in col.mean(0)], colour_spread=round(float(col.std(0).mean()), 3),
                     hist=[round(float(v), 3) for v in hist],
                     seen_from=int(np.median(seen[cells[:, 0], cells[:, 1]])), clean_views=len(heights),
                     view_spread=round(float(spread), 2), cells=cells)
            out.append(d)
        return out

    def _absorb_small(self, groups: list[np.ndarray]) -> list[np.ndarray]:
        """A very small patch right next to a larger one is a loose end of it; a very small black one is a
        loose end of a pair of glasses (nothing else here is small and black)."""
        groups = sorted(groups, key=len, reverse=True)
        out: list[np.ndarray] = []
        for g in groups:
            if len(g) * CELL * CELL >= 0.0008 or not out:
                out.append(g)
                continue
            cols = [v.rgb.reshape(-1, 3)[pix[g[lab[g[:, 0], g[:, 1]] == 1, 0], g[lab[g[:, 0], g[:, 1]] == 1, 1]]] for v, lab, pix in zip(self.views, self.labels, self.pix)]
            cols = [c for c in cols if len(c)]
            black = bool(cols) and float(np.concatenate(cols).mean(0).sum()) < 0.5
            gaps = [np.sqrt(((g[:, None, :] - o[None, :: max(1, len(o) // 300), :]) ** 2).sum(-1)).min() * CELL for o in out]
            k = int(np.argmin(gaps))
            if gaps[k] < 0.035 or (black and gaps[k] < 0.15):
                out[k] = np.concatenate((out[k], g))
            elif not black:
                out.append(g)
        return out

    def _split_large(self, cells: np.ndarray) -> list[np.ndarray]:
        """Something small standing against something very large (a mug against a jacket) comes out as one
        patch. If a part at the rim of a very large patch has a clearly different colour in most pictures,
        it is a thing of its own."""
        if len(cells) * CELL * CELL < 0.04:
            return [cells]
        col = self._cell_colours(cells)
        main = np.nanmedian(col, axis=0)
        odd = np.linalg.norm(col - main, axis=1) > 0.33
        if odd.sum() < MIN_CELLS:
            return [cells]
        mask = self._mask(cells)
        out, rest = [], np.ones(len(cells), bool)
        index = {tuple(c): n for n, c in enumerate(cells)}
        for g in _join_near(_groups(self._mask(cells[odd]), 1), 0.06 / CELL):
            if len(g) * CELL * CELL < 0.0008:
                continue
            pad = np.pad(mask, 1)
            at_rim = any(not pad[i + di + 1, j + dj + 1] for i, j in g[:: max(1, len(g) // 200)] for di in (-2, 0, 2) for dj in (-2, 0, 2)
                         if 0 <= i + di < self.nx and 0 <= j + dj < self.ny) or g[:, 0].min() <= 1 or g[:, 1].min() <= 1
            if not at_rim:
                continue
            out.append(g)
            for c in g:
                rest[index[tuple(c)]] = False
        return [cells[rest]] + out if out else [cells]

    def _cell_colours(self, cells: np.ndarray) -> np.ndarray:
        """The colour each cell shows in most pictures."""
        cols = np.full((len(self.views), len(cells), 3), np.nan)
        for n, (v, lab, pix) in enumerate(zip(self.views, self.labels, self.pix)):
            hit = lab[cells[:, 0], cells[:, 1]] == 1
            cols[n, hit] = v.rgb.reshape(-1, 3)[pix[cells[hit, 0], cells[hit, 1]]]
        return np.nanmedian(cols, axis=0)

    def _merge_fragments(self, groups: list[np.ndarray]) -> list[np.ndarray]:
        """Parts of a thing that do not touch the surface leave no footprint (the middle of an apple core, the
        arms of a pair of glasses), so one thing can come out as several pieces. Two pieces are one thing if
        every picture that shows both shows them joined, they have the same colour, and either they are almost
        touching and one is small, or both are black (only glasses are) and close."""
        if len(groups) < 2:
            return groups
        patch_id = []                                     # per view: which patch each cell belongs to
        for lab in self.labels:
            ids = np.zeros(lab.shape, int)
            for n, patch in enumerate(_groups(lab == 1, 1)):
                ids[patch[:, 0], patch[:, 1]] = n + 1
            patch_id.append(ids)

        def colour(cells):
            cols = []
            for v, lab, pix in zip(self.views, self.labels, self.pix):
                hit = lab[cells[:, 0], cells[:, 1]] == 1
                if hit.any():
                    cols.append(v.rgb.reshape(-1, 3)[pix[cells[hit, 0], cells[hit, 1]]])
            return np.concatenate(cols).mean(0) if cols else np.zeros(3)

        def joined(a, b):
            both = 0
            for lab, ids in zip(self.labels, patch_id):
                ia, ib = ids[a[:, 0], a[:, 1]], ids[b[:, 0], b[:, 1]]
                ia, ib = set(ia[ia > 0].tolist()), set(ib[ib > 0].tolist())
                if not ia or not ib:
                    continue
                both += 1
                if not (ia & ib):
                    return False
            return both > 0

        groups = sorted(groups, key=len, reverse=True)
        cols = [colour(g) for g in groups]
        merged = True
        while merged:
            merged = False
            for i in range(len(groups) - 1, 0, -1):
                for j in range(i):
                    if np.linalg.norm(cols[i] - cols[j]) > 0.10:
                        continue
                    small = len(groups[i]) * CELL * CELL < 0.0012
                    black = cols[i].sum() < 0.5 and cols[j].sum() < 0.5
                    if not (small or black):
                        continue
                    sub = groups[j][::max(1, len(groups[j]) // 400)]
                    gap = np.sqrt(((groups[i][:, None, :] - sub[None, :, :]) ** 2).sum(-1)).min() * CELL
                    if gap < (0.12 if black else 0.04) and joined(groups[i], groups[j]):
                        groups[j] = np.concatenate((groups[j], groups[i]))
                        cols[j] = colour(groups[j])
                        del groups[i], cols[i]
                        merged = True
                        break
                if merged:
                    break
        return groups

    def at_height(self, cells: np.ndarray, h: float) -> np.ndarray:
        """Of the cells of a footprint, those that still belong to it if the thing stands `h` high: a point
        `h` above the cell must not be seen through (to bare surface) in any picture. For a thing with upright
        sides this cuts off the tail that pictures taken from one side only leave behind it."""
        pts = np.stack((self.x0 + (cells[:, 0] + 0.5) * CELL, self.y0 + (cells[:, 1] + 0.5) * CELL, np.full(len(cells), self.top + h)), axis=1)
        keep = np.ones(len(cells), bool)
        for view, verdict in zip(self.views, self.verdict):
            u, v, z = view.project(pts)
            ui, vi = np.rint(u).astype(int), np.rint(v).astype(int)
            ok = (z > 0) & (ui >= 1) & (ui < view.w - 1) & (vi >= 1) & (vi < view.h - 1)
            ui, vi = np.clip(ui, 1, view.w - 2), np.clip(vi, 1, view.h - 2)
            # seen through only if the pixel and its neighbours all show bare surface
            through = np.ones(len(cells), bool)
            for du in (-1, 0, 1):
                for dv in (-1, 0, 1):
                    through &= verdict[vi + dv, ui + du] == 0
            keep &= ~(ok & through)
        return keep

    def refine(self, d: dict, h: float) -> list[dict]:
        """Re-measure a detection assuming the thing is `h` high. Returns the thing itself (several, if what
        looked like one turns out to be two of the kind, one behind the other), plus whatever else was run
        together with it and is not just its tail. A thing with a rounded top has almost no cross-section at
        its full height, so the cut is made at the greatest height (down to 0.6 h) that still keeps most of
        the thing's width as seen from the cameras."""
        cells = d["cells"]
        to_xy = lambda c: np.stack((self.x0 + (c[:, 0] + 0.5) * CELL, self.y0 + (c[:, 1] + 0.5) * CELL), axis=1)
        xy = to_xy(cells)
        cam = np.mean([v.pos[:2] for v in self.views], axis=0)
        away = xy.mean(0) - cam
        away /= max(np.linalg.norm(away), 1e-6)
        side = np.array([-away[1], away[0]])
        full = np.ptp(xy @ side) + CELL
        for frac in (1.0, 0.9, 0.8, 0.7, 0.6):
            keep = self.at_height(cells, h * frac)
            if keep.sum() < MIN_CELLS:
                continue
            parts = [p for p in _groups(self._mask(cells[keep]), 1) if len(p) >= MIN_CELLS]
            if parts:                                     # a second one of the kind must be about as big as the first
                biggest = max(len(p) for p in parts)
                parts = [p for p in parts if len(p) >= 0.4 * biggest]
            if not parts or sum(np.ptp(to_xy(p) @ side) + CELL for p in parts) < 0.7 * full:
                continue
            out = []
            for p in parts:
                e = dict(d)
                e.update(self._measure(p), cells=p, refined_at=round(h * frac, 3))
                out.append(e)
            # what is left: cells that are not behind the thing (as seen from a camera that shows them covered)
            body = self._mask(np.concatenate(parts))
            rest = cells[~keep]
            if len(rest):
                behind_all = np.ones(len(rest), bool)
                rxy = to_xy(rest)
                for view, lab in zip(self.views, self.labels):
                    covered = lab[rest[:, 0], rest[:, 1]] == 1
                    H = view.pos[2] - self.top
                    behind = np.zeros(len(rest), bool)
                    for z in np.linspace(0.0, h, 7)[1:]:           # walk up the viewing ray: does it pass through the thing?
                        q = rxy + (view.pos[:2] - rxy) * (z / H)
                        i = np.clip(((q[:, 0] - self.x0) / CELL).astype(int), 0, self.nx - 1)
                        j = np.clip(((q[:, 1] - self.y0) / CELL).astype(int), 0, self.ny - 1)
                        behind |= body[i, j]
                    behind_all &= behind | ~covered
                left = [g for g in _join_near(_groups(self._mask(rest[~behind_all]), 1), 0.03 / CELL)
                        if len(g) * CELL * CELL >= 0.0012 and min(np.ptp(g[:, 0]), np.ptp(g[:, 1])) * CELL >= 0.02]
                for g in left:
                    e = dict(d)
                    cols = []
                    for view, lab, pix in zip(self.views, self.labels, self.pix):
                        hit = lab[g[:, 0], g[:, 1]] == 1
                        if hit.any():
                            cols.append(view.rgb.reshape(-1, 3)[pix[g[hit, 0], g[hit, 1]]])
                    col = np.concatenate(cols) if cols else np.zeros((1, 3))
                    bins = np.clip((col * 3).astype(int), 0, 2)
                    e.update(self._measure(g), cells=g, height=0.0, colour=[round(float(c), 3) for c in col.mean(0)],
                             colour_spread=round(float(col.std(0).mean()), 3),
                             hist=[round(float(v), 3) for v in np.bincount(bins[:, 0] * 9 + bins[:, 1] * 3 + bins[:, 2], minlength=27) / len(col)],
                             split_from=d.get("kind"), unclassified=True)
                    out.append(e)
            return out
        return [d]

    def _mask(self, cells: np.ndarray) -> np.ndarray:
        m = np.zeros((self.nx, self.ny), bool)
        m[cells[:, 0], cells[:, 1]] = True
        return m

    def _measure(self, cells: np.ndarray) -> dict:
        xy = np.stack((self.x0 + (cells[:, 0] + 0.5) * CELL, self.y0 + (cells[:, 1] + 0.5) * CELL), axis=1)
        mean = xy.mean(0)
        if len(xy) > 2:
            _, vec = np.linalg.eigh(np.cov((xy - mean).T))
            axis = vec[:, 1]
        else:
            axis = np.array([1.0, 0.0])
        side = np.array([-axis[1], axis[0]])
        a, b = (xy - mean) @ axis, (xy - mean) @ side
        centre = mean + axis * (a.max() + a.min()) / 2 + side * (b.max() + b.min()) / 2
        return dict(surface=self.name, x=round(float(centre[0]), 4), y=round(float(centre[1]), 4),
                    length=round(float(a.max() - a.min() + CELL), 4), width=round(float(b.max() - b.min() + CELL), 4),
                    orientation=round(math.atan2(axis[1], axis[0]) % math.pi, 3), area=round(len(cells) * CELL * CELL, 5),
                    reaches_edge=bool(cells[:, 0].min() == 0 or cells[:, 1].min() == 0 or cells[:, 0].max() == self.nx - 1 or cells[:, 1].max() == self.ny - 1))

    def _height_from_tail(self, view: View, cells: np.ndarray, patch: np.ndarray) -> float:
        """How high a thing stands, from how far its patch in one picture reaches behind its footprint."""
        g = view.pos[:2]
        to_xy = lambda c: np.stack((self.x0 + (c[:, 0] + 0.5) * CELL, self.y0 + (c[:, 1] + 0.5) * CELL), axis=1)
        foot, tail = to_xy(cells), to_xy(patch)
        away = foot.mean(0) - g
        away /= max(np.linalg.norm(away), 1e-6)
        d_foot, d_tail = float(((foot - g) @ away).max()), float(((tail - g) @ away).max())
        s = max(d_tail - d_foot + CELL, 0.0)      # the footprint was grown by one cell when it was cut out
        H = view.pos[2] - self.top
        return s * H / max(d_foot + s, 1e-6)

    def unseen(self) -> float:
        return float((self.times_seen() == 0).mean())


class DepthMap(SurfaceMap):
    """The same top-down grid, filled from pictures that come with depth: a thing's cells are simply where
    its points are, so nothing has to be reasoned out across pictures."""

    def __init__(self, name: str, rect: dict, shrink: float = 0.008):
        super().__init__(name, rect, shrink)
        self.seen_n = np.zeros((self.nx, self.ny), int)
        self.n = np.zeros((self.nx, self.ny))
        self.h = np.zeros((self.nx, self.ny))
        self.rgb = np.zeros((self.nx, self.ny, 3))

    def add(self, view: View):
        P = view.points()
        rgb = view.rgb.astype(np.float64)
        z = P[..., 2] - self.top
        inside = (P[..., 0] > self.x0) & (P[..., 0] < self.x1) & (P[..., 1] > self.y0) & (P[..., 1] < self.y1)
        ok = inside & (z > -0.004) & (z < MAX_H) & view.not_robot_points(P)
        thing = ok & (z > MIN_H)
        # The camera looks along the surface at a slant, so neighbouring rows of the picture land up to a
        # centimetre apart on it. Fill in between rows that show the same kind of point.
        pts, cols, things = [P[ok]], [rgb[ok]], [thing[ok]]
        both = ok[:-1] & ok[1:] & (thing[:-1] == thing[1:]) & (np.linalg.norm(P[:-1] - P[1:], axis=-1) < 0.025)
        for f in (1 / 3, 2 / 3):
            pts.append((P[:-1] * (1 - f) + P[1:] * f)[both])
            cols.append((rgb[:-1] * (1 - f) + rgb[1:] * f)[both])
            things.append(thing[:-1][both])
        pts, cols, things = np.concatenate(pts), np.concatenate(cols), np.concatenate(things)
        i = np.clip(((pts[:, 0] - self.x0) / CELL).astype(int), 0, self.nx - 1)
        j = np.clip(((pts[:, 1] - self.y0) / CELL).astype(int), 0, self.ny - 1)
        seen = np.zeros((self.nx, self.ny), bool)
        seen[i, j] = True
        self.seen_n += seen
        i, j, pts, cols = i[things], j[things], pts[things], cols[things]
        np.add.at(self.n, (i, j), 1.0)
        np.maximum.at(self.h, (i, j), pts[:, 2] - self.top)
        np.add.at(self.rgb, (i, j), cols)
        self.views.append(view)

    def times_seen(self) -> np.ndarray:
        return self.seen_n

    def _cell_colours(self, cells: np.ndarray) -> np.ndarray:
        return self.rgb[cells[:, 0], cells[:, 1]] / self.n[cells[:, 0], cells[:, 1], None]

    def detections(self) -> list[dict]:
        out = []
        # something small lying against something very large (a mug against the jacket) is told apart by its colour
        for cells in (part for g in _groups(self.n > 0, MIN_CELLS) for part in self._split_large(g) if len(part) >= MIN_CELLS):
            d = self._measure(cells)
            col = self.rgb[cells[:, 0], cells[:, 1]] / self.n[cells[:, 0], cells[:, 1], None]
            bins = np.clip((col * 3).astype(int), 0, 2)
            hist = np.bincount(bins[:, 0] * 9 + bins[:, 1] * 3 + bins[:, 2], minlength=27) / len(col)
            d.update(height=round(float(np.percentile(self.h[cells[:, 0], cells[:, 1]], 95)), 4),
                     colour=[round(float(c), 3) for c in col.mean(0)], colour_spread=round(float(col.std(0).mean()), 3),
                     hist=[round(float(v), 3) for v in hist], seen_from=int(np.median(self.seen_n[cells[:, 0], cells[:, 1]])),
                     clean_views=len(self.views), view_spread=3.14, cells=cells)
            out.append(d)
        return out


# ==================================================================================================
# What is it? Compare with the examples
# ==================================================================================================
def features(d: dict) -> np.ndarray:
    """A detection as a vector in which plain distance means 'looks different'."""
    return np.array([d["length"] / 0.03, d["width"] / 0.03, d["height"] / 0.012, math.sqrt(d["area"]) / 0.03,
                     *(c / 0.10 for c in d["colour"]), d["colour_spread"] / 0.08, *(v / 0.35 for v in d["hist"])])


class Classifier:
    """Nearest examples. Each example is a thing seen in another room, with its kind."""

    def __init__(self, model: dict | None = None, mode: str = "depth"):
        if model is None:
            model = json.loads(MODEL_FILE.read_text()) if MODEL_FILE.exists() else {}
            model = model.get(mode, dict(examples=[]))
        self.kinds = [e["kind"] for e in model["examples"]]
        self.group = [e["group"] for e in model["examples"]]          # trash | personal | tool
        self.X = np.array([e["features"] for e in model["examples"]]) if model["examples"] else np.zeros((0, 1))
        self.kind_height = model.get("kind_height", {})    # how high each kind stands, measured where it was seen from opposite sides

    def classify(self, d: dict, k: int = 5) -> dict:
        if not len(self.X):
            return dict(kind="unknown", group="unknown", confidence=0.0)
        dist = np.linalg.norm(self.X - features(d), axis=1)
        idx = np.argsort(dist)[:k]
        w = 1.0 / (dist[idx] + 0.5)
        votes: dict = {}
        for i, wi in zip(idx, w):
            votes[self.kinds[i]] = votes.get(self.kinds[i], 0.0) + wi
        kind = max(votes, key=votes.get)
        group = self.group[self.kinds.index(kind)]
        gshare = sum(wi for i, wi in zip(idx, w) if self.group[i] == group) / w.sum()
        # far from every example: say so instead of guessing with confidence
        familiar = 1.0 / (1.0 + max(float(dist[idx[0]]) - 3.0, 0.0) / 3.0)
        return dict(kind=kind, group=group, confidence=round(float(gshare * familiar), 3), nearest=round(float(dist[idx[0]]), 2))


# ==================================================================================================
# Putting the camera somewhere
# ==================================================================================================
def _view_pose(cam_xy, look_dir: float):
    """Base pose that puts the head camera at cam_xy looking along look_dir, body square to the view.
    (Turning the body away and the head back would keep the hands out of the picture, but then the camera
    looks straight at its own upper arm.)"""
    f = HEAD_FWD + CAM_OFF
    return (cam_xy[0] - f * math.cos(look_dir), cam_xy[1] - f * math.sin(look_dir), look_dir)


def _candidates(rect: dict, middles_first: bool = False):
    """Places to look from: along each side of the rectangle, a camera every VIEW_STEP metres within the
    side's own span (so that a raised border, like a sofa's arm, is never between camera and surface),
    each looking at the middle of the rectangle. Long sides first. Without depth the two ends of a side come
    before its middle, so that the first pictures already look across the surface from different directions;
    with depth the middle of every side comes first, because a few pictures are enough."""
    cx, cy = (rect["x"][0] + rect["x"][1]) / 2, (rect["y"][0] + rect["y"][1]) / 2
    lx, ly = rect["x"][1] - rect["x"][0], rect["y"][1] - rect["y"][0]
    sides = [((0, -1), ly / 2, lx), ((0, 1), ly / 2, lx), ((-1, 0), lx / 2, ly), ((1, 0), lx / 2, ly)]   # outward normal, centre to edge, side length
    sides.sort(key=lambda s: -s[2])
    per_side = []
    for (nx, ny), half, length in sides:
        tx, ty = -ny, nx
        n = max(1, int(round((length - 0.1) / VIEW_STEP)))
        offs = [(-0.5 + i / n) * (length - 0.1) for i in range(n + 1)] if n > 1 else [-(length - 0.1) / 2, (length - 0.1) / 2]
        if middles_first:
            offs = ([0.0] if n <= 1 else []) + offs
            offs.sort(key=lambda o: abs(o))
        else:
            offs.sort(key=lambda o: -abs(o))
        per_side.append([dict(edge=(cx + nx * half + tx * off, cy + ny * half + ty * off), normal=(nx, ny), target=(cx, cy)) for off in offs])
    if not middles_first:
        return [c for side in per_side for c in side]
    out = []
    for k in range(max(len(p) for p in per_side)):           # round robin over the sides
        out += [p[k] for p in per_side if k < len(p)]
    return out


def take_view(world, task: dict, edge, normal, target, target_z: float, floor: Floor | None = None, depth: bool = True):
    """Stand outside `edge` (a point on the rim of what is to be seen), as far back along `normal` as the room
    allows, face `target`, and return the picture as a View, or None if the robot cannot stand there."""
    st = world.observe()
    floor = floor or Floor(task, _tools_in_hand(st))
    pose = None
    for dist in VIEW_DISTS:
        cam = (edge[0] + normal[0] * dist, edge[1] + normal[1] * dist)
        cand = _view_pose(cam, math.atan2(target[1] - cam[1], target[0] - cam[0]))
        if floor.free(*cand):
            pose = cand
            break
    if pose is None or not drive(world, *pose, task=task):
        return None
    st = world.observe()
    b = st["base"]
    cam_h = CAM_HEIGHT0 + st["torso"]
    cam_xy = (b["x"] + (HEAD_FWD + CAM_OFF) * math.cos(b["heading"]), b["y"] + (HEAD_FWD + CAM_OFF) * math.sin(b["heading"]))
    tilt = float(-math.atan2(cam_h - target_z, math.hypot(target[0] - cam_xy[0], target[1] - cam_xy[1])))
    if abs(st["head"]["pan"]) > 0.02 or abs(st["head"]["tilt"] - tilt) > 0.02:
        world.look(0.0, tilt)
    return View(world.camera("head", depth=depth), world.observe())


# ==================================================================================================
# The survey
# ==================================================================================================
def survey(world, depth: bool = True, surfaces=("table", "sofa"), max_views: int | None = None, classifier: Classifier | None = None, ignore=()) -> dict:
    """Look at each surface from several places and list what lies on it.

    Each detection: surface, x, y (middle of its footprint), length, width, orientation, height, colour,
    kind, group ('trash' | 'personal' | 'tool'), confidence, seen_from (number of pictures).

    depth=False uses colour pictures only (see the top of this file); it needs more pictures.
    `ignore` is a list of (x, y, radius): places where the robot itself put something down (its brush, say).
    What is found there is reported with group 'tool' and not judged.
    """
    task = world.get_task()
    t0 = task["time_limit_s"] - world.observe()["time_left_s"]
    rects = dict(table=task["room"]["table"], sofa=task["room"]["sofa_seat"])
    clf = classifier or Classifier(mode="depth" if depth else "colour")
    floor = Floor(task, _tools_in_hand(world.observe()))
    max_views = max_views or (6 if depth else 8)
    maps, views = {}, 0
    for name in surfaces:
        rect = rects[name]
        m = maps[name] = (DepthMap if depth else SurfaceMap)(name, rect)
        gain = 1.0
        for cand in _candidates(rect, middles_first=depth):
            if len(m.views) >= max_views:
                break
            # with depth: stop once two pictures are in and the last one showed next to nothing new
            # (what stays unseen then is the strip hidden behind things that stand on the surface)
            if depth and len(m.views) >= 2 and (m.unseen() < 0.003 or gain < 0.01):
                break
            cx, cy = cand["target"]
            for pull in (0.0, 0.15, 0.3):                 # if the robot cannot stand there, try nearer the middle of the side
                ex, ey = cand["edge"]
                tx, ty = -cand["normal"][1], cand["normal"][0]
                along = (ex - cx) * tx + (ey - cy) * ty
                shift = -math.copysign(min(pull, abs(along)), along)
                view = take_view(world, task, (ex + tx * shift, ey + ty * shift), cand["normal"], cand["target"], rect["top"], floor, depth)
                if view is not None:
                    before = m.unseen()
                    m.add(view)
                    gain = before - m.unseen()
                    break
        views += len(m.views)
    detections = []
    for name, m in maps.items():
        for d in m.detections():
            d.update(clf.classify(d))
            # Without depth, pictures from one side only (the sofa can only be seen from the front) leave a tail
            # behind anything that stands up. Knowing what the thing is tells how high it stands, and that
            # removes the tail.
            h = clf.kind_height.get(d["kind"], 0.0)
            parts = m.refine(d, h) if not depth and d["view_spread"] < 2.0 and h > 0.006 and d["confidence"] >= 0.5 else [d]
            for e in parts:
                if e.pop("unclassified", False):          # something that was run together with it: judge it on its own
                    e.update(clf.classify(e))
                e.pop("cells")
                if any(math.hypot(e["x"] - ix, e["y"] - iy) < ir for ix, iy, ir in ignore):
                    e.update(kind="own tool", group="tool", confidence=1.0)
                detections.append(e)
    return dict(detections=detections, unseen={n: round(m.unseen(), 4) for n, m in maps.items()}, views=views,
                robot_time_s=round(task["time_limit_s"] - world.observe()["time_left_s"] - t0, 1), maps=maps)


# ==================================================================================================
# Where are the brush and the bin?
# ==================================================================================================
def _red(rgb: np.ndarray) -> np.ndarray:
    return (rgb[..., 0] > 0.45) & (rgb[..., 1] < 0.6 * rgb[..., 0]) & (rgb[..., 2] < 0.6 * rgb[..., 0])


def _line(xy: np.ndarray):
    """Middle, direction, length and thickness of an elongated set of points."""
    mean = xy.mean(0)
    _, vec = np.linalg.eigh(np.cov((xy - mean).T))
    axis = vec[:, 1]
    side = np.array([-axis[1], axis[0]])
    a, b = (xy - mean) @ axis, (xy - mean) @ side
    return mean + axis * (a.max() + a.min()) / 2, axis, float(a.max() - a.min()), float(b.max() - b.min())


def find_tools(view: View, shelf: dict) -> dict:
    """In one picture of the tool station: the brush lying on the shelf and the bin standing on the floor.
    Both handles are marked red (the knob on the end of the brush handle, the bar on the bin). Their heights
    follow from the floor plan and the task's sizes: the brush handle runs 6 cm above the shelf top, the
    bin's bar hangs 1.2 cm below its rim, 36 cm above the floor."""
    out = dict(brush=None, bin=None)
    red = _red(view.rgb) & ~view.robot
    knob_z = shelf["top"] + BRUSH_GRIP_UP + 0.006                # the part of the knob that faces the camera
    bar_z = BIN_HEIGHT - BIN_BAR_DROP
    P = view.points() if view.depth is not None else None
    if P is not None:                                      # with depth every pixel already is a point in the room
        ok3 = view.not_robot_points(P)
        kx, ky, kok = P[..., 0], P[..., 1], ok3
        bx, by, bok = P[..., 0], P[..., 1], ok3
    else:
        kx, ky, kok = view.on_plane(knob_z)
        bx, by, bok = view.on_plane(bar_z + 0.006)
    for blob in _groups(red, 10):
        i, j = blob[:, 0], blob[:, 1]
        # a small round red spot whose ray meets the handle's height above the shelf: the brush's knob
        pk = np.stack((kx[i, j], ky[i, j]), axis=1)
        mk = pk.mean(0)
        on_shelf = abs(mk[0] - shelf["cx"]) < shelf["hx"] + 0.05 and abs(mk[1] - shelf["cy"]) < shelf["hy"] + 0.05
        pb = np.stack((bx[i, j], by[i, j]), axis=1)
        mid, axis, length, thick = _line(pb) if len(pb) > 2 else (pb.mean(0), np.array([1.0, 0.0]), 0.0, 0.0)
        near = math.hypot(mid[0] - shelf["cx"], mid[1] - shelf["cy"]) < 1.2
        if kok[i, j].all() and on_shelf and _line(pk)[2] < 0.06 and out["brush"] is None:
            away = mk - view.pos[:2]                       # the camera sees the near half of the round knob: its middle is a little further
            out["brush"] = _brush_from_knob(view, shelf, mk + 0.006 * away / max(np.linalg.norm(away), 1e-6), P)
        elif bok[i, j].all() and near and 0.085 < length < 0.16 and thick < 0.05:
            # an elongated red bar at the bin's handle height: the bar; the bin is on the side where the picture shows its lid
            side = np.array([-axis[1], axis[0]])
            score = []
            for sgn in (1.0, -1.0):
                pts = np.array([[mid[0] + sgn * side[0] * d, mid[1] + sgn * side[1] * d, BIN_HEIGHT] for d in (0.08, 0.12, 0.16, 0.20)])
                u, v, z = view.project(pts)
                ok = (z > 0) & (u >= 0) & (u < view.w) & (v >= 0) & (v < view.h)
                c = view.rgb[np.clip(np.rint(v).astype(int), 0, view.h - 1), np.clip(np.rint(u).astype(int), 0, view.w - 1)]
                dark = ok & (c.sum(1) < 1.6) & (c[:, 1] >= c[:, 0])           # the bin is dark green; floor and wall are light
                score.append(dark.sum())
            sgn = 1.0 if score[0] >= score[1] else -1.0
            centre = mid + sgn * side * (BIN_HALF[0] + BIN_BAR_OFF)
            if P is not None:
                bar_z = float(np.median(P[i, j, 2])) - 0.008        # the camera sees the upper half of the bar
            yaw = math.atan2(axis[1], axis[0])
            out["bin"] = dict(x=round(float(mid[0]), 4), y=round(float(mid[1]), 4), z=round(bar_z, 4), handle_yaw=round(yaw % math.pi, 3),
                              closing_yaw=round(_wrap(yaw + math.pi / 2), 3), centre=[round(float(centre[0]), 4), round(float(centre[1]), 4)],
                              long_axis_yaw=round(math.atan2(side[1], side[0]) % math.pi, 3), bar_length_seen=round(length, 3))
    return out


def _brush_from_knob(view: View, shelf: dict, knob: np.ndarray, P: np.ndarray | None = None):
    """From the knob, follow the wooden handle: the place to hold is 7 cm along it."""
    rgb = view.rgb
    tot = rgb.sum(-1) + 1e-6
    wood = np.array([0.72, 0.50, 0.28])
    mix = np.linalg.norm(rgb / tot[..., None] - wood / wood.sum(), axis=-1)
    woody = (mix < 0.04) & (tot > 0.5 * wood.sum()) & (tot < 1.4 * wood.sum()) & ~view.robot
    if P is not None:
        hx, hy, hok = P[..., 0], P[..., 1], view.not_robot_points(P)
    else:
        hx, hy, hok = view.on_plane(shelf["top"] + BRUSH_GRIP_UP + BRUSH_HANDLE_R)
    d = np.hypot(hx - knob[0], hy - knob[1])
    sel = woody & hok & (d > 0.02) & (d < 0.24)
    if sel.sum() < 25:
        return None
    pts = np.stack((hx[sel], hy[sel]), axis=1) - knob
    # the handle is a thin line starting at the knob: its direction is the main direction of these points
    _, vec = np.linalg.eigh(pts.T @ pts)
    axis = vec[:, 1]
    if (pts @ axis).mean() < 0:
        axis = -axis
    across = np.abs(pts @ np.array([-axis[1], axis[0]]))
    if np.percentile(across, 80) > 0.04 or (pts @ axis).max() < 0.15:
        return None
    grip = knob + axis * BRUSH_KNOB_TO_GRIP
    yaw = math.atan2(axis[1], axis[0])
    z = shelf["top"] + BRUSH_GRIP_UP
    if P is not None:                                      # the top line of the round handle, minus its radius
        z = float(np.percentile(P[..., 2][sel], 90)) - BRUSH_HANDLE_R
    return dict(x=round(float(grip[0]), 4), y=round(float(grip[1]), 4), z=round(z, 4), handle_yaw=round(yaw, 3),
                closing_yaw=round(_wrap(yaw + math.pi / 2), 3), knob=[round(float(knob[0]), 4), round(float(knob[1]), 4)])


def locate_tools(world, depth: bool = True, max_views: int = 3) -> dict:
    """Find the brush on the shelf and the bin beside it, from one or more pictures of the tool station.
    Each: x, y, z of the place to hold, handle_yaw (the direction the handle runs; for the brush from the hand
    towards the head), closing_yaw (the direction the fingers should close along)."""
    task = world.get_task()
    shelf = task["room"]["tool_station"]["shelf"]
    st = world.observe()
    floor = Floor(task, _tools_in_hand(st))
    b = st["base"]
    w = task["room"]["walls"]
    front = 0.0 if abs(shelf["cx"] - w["x"][0]) < 0.6 else math.pi if abs(shelf["cx"] - w["x"][1]) < 0.6 else \
        math.pi / 2 if abs(shelf["cy"] - w["y"][0]) < 0.6 else -math.pi / 2      # the shelf stands against a wall; this way is into the room
    cands = []
    for ang in np.linspace(-1.2, 1.2, 13):                 # directions to look from, the one nearest to the robot first
        n = (math.cos(front + ang), math.sin(front + ang))
        at = (shelf["cx"] + 1.1 * n[0], shelf["cy"] + 1.1 * n[1])
        cands.append((math.hypot(at[0] - b["x"], at[1] - b["y"]) + 0.3 * abs(ang), ang, n))
    cands.sort(key=lambda c: c[0])
    out, views, used = dict(brush=None, bin=None), 0, []
    for _, ang, n in cands:
        if views >= max_views or (out["brush"] and out["bin"]):
            break
        if any(abs(ang - u) < 0.55 for u in used):
            continue
        target = (shelf["cx"], shelf["cy"])
        view = take_view(world, task, (shelf["cx"] + 0.3 * n[0], shelf["cy"] + 0.3 * n[1]), n, target, 0.40, floor, depth)
        if view is None:
            continue
        used.append(ang)
        views += 1
        found = find_tools(view, shelf)
        out["brush"] = out["brush"] or found["brush"]
        out["bin"] = out["bin"] or found["bin"]
    out["views"] = views
    return out
