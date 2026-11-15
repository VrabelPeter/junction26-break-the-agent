"""Shape board: a robot arm pushes shaped pegs (star, rectangle, ...) into matching holes by feel.

Units at every interface: millimetres, degrees, newtons, newton-millimetres.

The contact model is quasi-static geometry, not a rigid-body engine. A peg is a polygon, its hole is the
same polygon grown by the clearance. Three situations exist:

  air      the peg touches nothing.
  surface  the peg stands on the board because its outline overhangs the hole edge somewhere. The board
           pushes back where the rim overhangs, so the torque about the peg tip says on which side the
           peg is supported.
  inside   the outline fits. If it only nearly fits, the chamfer at the hole mouth and the springy wrist
           pull it in, provided the press is strong enough to bend the wrist that far. Inside, the hole
           walls hold the peg, the wrist springs load up sideways, and that side load is felt as
           friction on the way down.

Everything is deterministic for a seed. One `World` is one episode: several pegs, one after another.
"""
from __future__ import annotations

import json
import math

import numpy as np

# ---- the numbers the agent is told (get_task) -------------------------------------------------------
CLEARANCE = 0.2        # gap between peg and hole wall on every side
CHAMFER = 0.5          # width of the lead-in at the hole mouth
DEPTH = 8.0            # full insertion depth
START_Z = 3.0          # the peg starts this far above the estimated board surface
K_Z = 10.0             # wrist stiffness, vertical, N per mm
K_LAT = 15.0           # wrist stiffness, sideways, N per mm
K_ROT = 60.0           # wrist stiffness about the vertical axis, N mm per degree
R_REF = 15.0           # lever arm that turns a twist into a side load: K_ROT / R_REF newtons per degree
KAPPA = 0.6            # share of the press force the chamfer turns into centring force
MU = 0.6               # friction of a side-loaded peg against the hole wall
F0 = 0.5               # friction of a peg that is not side-loaded
SEAT_FORCE = 5.0       # press at the bottom needed to seat the peg
DAMAGE_FORCE = 15.0    # pressing harder than this on the board face damages it
FORCE_MIN, FORCE_MAX = 1.0, 25.0
MAX_STEP, MAX_TURN = 5.0, 5.0          # per move
ERR_XY, ERR_YAW, ERR_Z = 2.0, 4.0, 0.5  # how wrong the hole estimate can be
BUDGET = 24            # moves per peg
PEGS = 6
WORK_XY, WORK_YAW, WORK_Z = 10.0, 15.0, (-(DEPTH + 6.0), 15.0)
NOISE_POS, NOISE_YAW, NOISE_F, NOISE_T = 0.02, 0.05, 0.1, 2.0

K_YAW = K_ROT / R_REF  # side load per degree of twist
SUB = 0.04             # a move is simulated in steps of this many mm (or degrees)
TOL = 2e-3             # outline overhang below this counts as a fit
RIM_SPACING = 0.25


def _star(points=5, outer=15.0, inner=7.0):
    out = []
    for i in range(2 * points):
        r = outer if i % 2 == 0 else inner
        a = math.pi / 2 + i * math.pi / points
        out.append((r * math.cos(a), r * math.sin(a)))
    return out


def _regular(n, radius, phase=0.0):
    return [(radius * math.cos(phase + 2 * math.pi * i / n), radius * math.sin(phase + 2 * math.pi * i / n)) for i in range(n)]


def _box(w, h):
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def _cross(arm=14.0, half=5.0):
    a, b = half, arm
    return [(-a, -b), (a, -b), (a, -a), (b, -a), (b, a), (a, a), (a, b), (-a, b), (-a, a), (-b, a), (-b, -a), (-a, -a)]


# Outlines, counter-clockwise, centred on the peg axis.
SHAPES = {
    "star": _star(),
    "rectangle": _box(30.0, 16.0),
    "triangle": _regular(3, 16.0, math.pi / 2),
    "square": _box(22.0, 22.0),
    "cross": _cross(),
    "hexagon": _regular(6, 13.0),
}


def _grow(poly: np.ndarray, c: float) -> np.ndarray:
    """The polygon with every edge moved outwards by c (counter-clockwise input)."""
    d = np.roll(poly, -1, 0) - poly
    n = np.stack([d[:, 1], -d[:, 0]], 1) / np.linalg.norm(d, axis=1, keepdims=True)
    n_prev = np.roll(n, 1, 0)
    return poly + c * (n_prev + n) / (1.0 + (n_prev * n).sum(1, keepdims=True))


def _rim(poly: np.ndarray, spacing: float) -> np.ndarray:
    """Points along the outline, corners included."""
    pts = []
    for a, b in zip(poly, np.roll(poly, -1, 0)):
        k = max(1, int(math.ceil(np.linalg.norm(b - a) / spacing)))
        pts.append(a + (b - a) * (np.arange(k) / k)[:, None])
    return np.concatenate(pts)


def _nearest(q: np.ndarray, poly: np.ndarray):
    """For each point: is it inside the polygon, its distance to the outline, and the vector from the
    nearest outline point to it."""
    a, b = poly, np.roll(poly, -1, 0)
    d = b - a
    x, y = q[:, 0:1], q[:, 1:2]
    ay, by = a[:, 1][None], b[:, 1][None]
    span = by - ay
    crosses = (ay > y) != (by > y)
    xi = a[:, 0][None] + (y - ay) * d[:, 0][None] / np.where(span == 0.0, 1.0, span)
    inside = (np.sum(crosses & (x < xi), 1) % 2) == 1
    t = np.clip(((q[:, None, :] - a[None]) * d[None]).sum(2) / (d * d).sum(1)[None], 0.0, 1.0)
    diff = q[:, None, :] - (a[None] + t[..., None] * d[None])
    k = np.argmin((diff ** 2).sum(2), 1)
    diff = diff[np.arange(len(q)), k]
    return inside, np.linalg.norm(diff, axis=1), diff


def _min_norm(rows, rhs):
    """The shortest u with rows[i] . u <= rhs[i] for all i (Hildreth's method; three unknowns)."""
    lam = [0.0] * len(rows)
    u = [0.0, 0.0, 0.0]
    sq = [r[0] * r[0] + r[1] * r[1] + r[2] * r[2] for r in rows]
    for _ in range(400):
        worst = 0.0
        for i, r in enumerate(rows):
            viol = r[0] * u[0] + r[1] * u[1] + r[2] * u[2] - rhs[i]
            step = max(-lam[i], viol / sq[i])
            if step != 0.0:
                lam[i] += step
                u[0] -= step * r[0]
                u[1] -= step * r[1]
                u[2] -= step * r[2]
            worst = max(worst, abs(step) * sq[i] ** 0.5)
        if worst < 1e-7:
            break
    return u


class Peg:
    """One peg and its hole, and the geometry questions the contact model asks about them."""

    def __init__(self, shape: str):
        self.shape = shape
        self.outline = np.array(SHAPES[shape], float)
        self.hole = _grow(self.outline, CLEARANCE)
        self.rim = _rim(self.outline, RIM_SPACING)
        self._cache = {}

    def gaps(self, q):
        """How far each corner is from fitting, for a peg at pose q = (x, y, yaw in radians) in the
        hole's frame: positive = a peg corner beyond the hole edge, or a hole corner poking into the
        peg; negative = room to spare. Also the direction in which each grows, and where it acts
        (relative to the peg centre). For a peg close to its hole the corners decide the fit."""
        c, s = math.cos(q[2]), math.sin(q[2])
        rot = np.array([[c, -s], [s, c]])
        centre = np.array(q[:2])
        x = self.outline @ rot.T + centre
        inside, dist, diff = _nearest(x, self.hole)
        sign = np.where(inside, -1.0, 1.0)
        s1, n1 = sign * dist, sign[:, None] * diff / np.maximum(dist, 1e-12)[:, None]
        hp = (self.hole - centre) @ rot
        inside, dist, diff = _nearest(hp, self.outline)
        sign = np.where(inside, 1.0, -1.0)
        s2, n2 = sign * dist, (-sign[:, None] * diff / np.maximum(dist, 1e-12)[:, None]) @ rot.T
        return np.concatenate([s1, s2]), np.concatenate([n1, n2]), np.concatenate([x - centre, self.hole - centre])

    def support(self, q):
        """Centre of the board's support under a peg standing on the board at pose q, relative to the
        peg centre: the rim carries the load where it overhangs the hole edge (weight grows with the
        overhang up to 1 mm)."""
        c, s = math.cos(q[2]), math.sin(q[2])
        r = self.rim @ np.array([[c, s], [-s, c]])
        inside, dist, _ = _nearest(r + np.array(q[:2]), self.hole)
        wt = np.where(inside, 0.0, np.minimum(dist, 1.0))
        return (wt[:, None] * r).sum(0) / wt.sum() if wt.sum() > 0 else np.zeros(2)

    def project(self, q0):
        """The pose closest to q0 at which the peg fits the hole (closest in mm, with a turn counted
        as the distance it moves a point R_REF from the centre). Returns the pose and whether it fits."""
        key = tuple(round(v, 9) for v in q0)
        if key in self._cache:
            return self._cache[key]
        q0 = np.array(q0, float)
        q = q0.copy()
        ok = False
        for _ in range(12):
            g, n, r = self.gaps(q)
            if g.max() <= TOL:
                ok = True
                break
            m = g > -1.5
            jac = np.column_stack([n[m], (r[m, 0] * n[m, 1] - r[m, 1] * n[m, 0]) / R_REF])
            at = (q - q0) * (1.0, 1.0, R_REF)
            u = _min_norm(jac.tolist(), (jac @ at - g[m] - TOL / 2).tolist())
            q = q0 + (u[0], u[1], u[2] / R_REF)
        if len(self._cache) > 4000:
            self._cache.clear()
        self._cache[key] = (q, ok)
        return q, ok


def _side_load(d) -> float:
    """Newtons of sideways spring load for a wrist deflection d = (dx, dy, dyaw in radians)."""
    return K_LAT * math.hypot(d[0], d[1]) + K_YAW * abs(math.degrees(d[2]))


class World:
    def __init__(self, seed: int, pegs: int = PEGS, budget: int = BUDGET):
        rng = np.random.default_rng([int(seed), 1])
        self.noise = np.random.default_rng([int(seed), 2])
        names = list(SHAPES)
        order = [names[i] for i in rng.permutation(len(names))]
        self.seed, self.budget = int(seed), int(budget)
        self.jobs = []
        for i in range(pegs):
            rad, ang = ERR_XY * math.sqrt(rng.uniform()), rng.uniform(0, 2 * math.pi)
            self.jobs.append({
                "shape": order[i % len(order)],
                # Hidden: where the hole really is, in the frame of the estimate the agent works in.
                "err": (rad * math.cos(ang), rad * math.sin(ang), rng.uniform(-ERR_YAW, ERR_YAW), rng.uniform(-ERR_Z, ERR_Z)),
                "result": None,
            })
        self.pegs = {name: Peg(name) for name in set(j["shape"] for j in self.jobs)}
        self.log = []      # every tool call, for replay
        self.frames = []   # true states, for the viewer only: (peg index, x, y, yaw_deg, height, mode)
        self.index = -1
        self.done = False
        self._begin(0)

    # ---- episode bookkeeping ------------------------------------------------------------------------
    def _begin(self, i: int):
        self.index = i
        job = self.jobs[i]
        self.peg = self.pegs[job["shape"]]
        self.err = job["err"]
        self.arm = [0.0, 0.0, START_Z, 0.0]
        self.moves_left = self.budget
        q0, ht = self._free(self.arm)
        self.st = {"mode": "air", "h": ht, "q": q0, "fz": 0.0, "lat": (0.0, 0.0), "tz": 0.0, "tq": (0.0, 0.0),
                   "seated": False, "damaged": False}
        self.moved = [0.0, 0.0, 0.0, 0.0]
        self.events = []
        self._measure()
        self._frame()

    def _result(self) -> dict:
        st = self.st
        depth = max(0.0, -st["h"]) if st["mode"] == "inside" else 0.0
        if st["damaged"]:
            score, what = 0.0, "board damaged"
        elif st["seated"]:
            score, what = 1.0, "seated"
        elif depth > 0:
            score, what = 0.5 * min(1.0, depth / DEPTH), f"in the hole, {depth:.1f} of {DEPTH:.0f} mm deep, not seated"
        else:
            score, what = 0.0, "not in the hole"
        return {"shape": self.jobs[self.index]["shape"], "score": round(score, 4), "outcome": what,
                "moves_used": self.budget - self.moves_left}

    # ---- geometry between the agent's frame and the hole ---------------------------------------------
    def _free(self, arm):
        """Where the peg would be with relaxed wrist springs: pose in the true hole frame, and height
        of its tip above the true board surface."""
        ex, ey, eyaw, ez = self.err
        a = math.radians(-eyaw)
        dx, dy = arm[0] - ex, arm[1] - ey
        return (dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a), math.radians(arm[3] - eyaw)), arm[2] - ez

    # ---- contact model ------------------------------------------------------------------------------
    def _settle(self, arm, prev, sliding: bool) -> dict:
        """The state of the peg when the arm is at `arm`, coming from state `prev`."""
        q0, ht = self._free(arm)
        st = dict(prev, q=q0, fz=0.0, lat=(0.0, 0.0), tz=0.0, tq=(0.0, 0.0))
        h_prev = prev["h"]
        if prev["mode"] != "inside":
            if ht >= 0.0:
                st.update(mode="air", h=ht)
                return st
            press = K_Z * -ht
            near = self.peg.gaps(q0)[0].max() <= CHAMFER
            q, ok = self.peg.project(q0) if near else (q0, False)
            d = np.subtract(q, q0)
            load = _side_load(d)
            if not (ok and not sliding and load <= KAPPA * press + 1e-9):
                # Standing on the board: the reaction sits where the rim overhangs the hole edge.
                cop = self.peg.support(q0)
                st.update(mode="surface", h=0.0, fz=press, tq=(press * cop[1], -press * cop[0]))
                if ok and load > 1e-9:
                    # Riding on the chamfer: it pushes towards the fit with all the press gives it.
                    g = KAPPA * press / load
                    st.update(lat=(g * K_LAT * d[0], g * K_LAT * d[1]), tz=g * K_YAW * math.degrees(d[2]) * R_REF)
                if press > DAMAGE_FORCE:
                    st["damaged"] = True
                return st
            h_prev = 0.0
        q, ok = self.peg.project(q0)
        d = np.subtract(q, q0)
        load = _side_load(d)
        slack = (F0 + MU * load) / K_Z
        h = -DEPTH if prev["seated"] else max(-DEPTH, min(max(h_prev, ht - slack), ht + slack))
        if h > 0.0:
            st.update(mode="air", h=ht)
            return st
        fz = K_Z * (h - ht)
        st.update(mode="inside", h=h, q=tuple(q), fz=fz, lat=(K_LAT * d[0], K_LAT * d[1]), tz=K_ROT * math.degrees(d[2]))
        if h <= -DEPTH + 1e-9 and fz >= SEAT_FORCE:
            st["seated"] = True
        return st

    def _load(self, st, arm) -> float:
        if st["mode"] != "inside":
            return abs(st["fz"])
        q0, _ = self._free(arm)
        return math.hypot(st["fz"], _side_load(np.subtract(st["q"], q0)))

    # ---- tools ----------------------------------------------------------------------------------------
    def call(self, tool: str, **args) -> str:
        fn = getattr(self, "t_" + tool, None)
        if fn is None:
            return json.dumps(self._obs(ok=False, error=f"unknown tool '{tool}'"))
        try:
            out = fn(**args)
        except TypeError as e:
            return json.dumps(self._obs(ok=False, error=f"bad arguments for {tool}: {e}"))
        if tool != "observe":
            self.log.append({"tool": tool, "args": args})
        return json.dumps(out)

    def t_observe(self):
        return self._obs()

    def t_move(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0, dyaw: float = 0.0, max_force: float = 5.0):
        try:
            dx, dy, dz, dyaw, max_force = (float(v) for v in (dx, dy, dz, dyaw, max_force))
        except (TypeError, ValueError):
            return self._obs(ok=False, error="dx, dy, dz, dyaw and max_force must be numbers")
        if not all(math.isfinite(v) for v in (dx, dy, dz, dyaw, max_force)):
            return self._obs(ok=False, error="dx, dy, dz, dyaw and max_force must be finite numbers")
        if self.done:
            return self._obs(ok=False, error="the job is over")
        if self.st["seated"]:
            return self._obs(ok=False, error="this peg is seated; call next_peg")
        if self.moves_left <= 0:
            return self._obs(ok=False, error="no moves left for this peg; call next_peg")
        if math.hypot(dx, dy, dz) > MAX_STEP + 1e-9 or abs(dyaw) > MAX_TURN + 1e-9:
            return self._obs(ok=False, error=f"a move is at most {MAX_STEP:g} mm and {MAX_TURN:g} degrees; nothing was moved")
        if not FORCE_MIN <= max_force <= FORCE_MAX:
            return self._obs(ok=False, error=f"max_force must be between {FORCE_MIN:g} and {FORCE_MAX:g} N; nothing was moved")
        goal = [self.arm[0] + dx, self.arm[1] + dy, self.arm[2] + dz, self.arm[3] + dyaw]
        if abs(goal[0]) > WORK_XY or abs(goal[1]) > WORK_XY or abs(goal[3]) > WORK_YAW or not WORK_Z[0] <= goal[2] <= WORK_Z[1]:
            return self._obs(ok=False, error=f"outside the working range (x, y within {WORK_XY:g} mm of the estimate, yaw within "
                                             f"{WORK_YAW:g} degrees, z from {WORK_Z[0]:g} to {WORK_Z[1]:g}); nothing was moved")
        self.moves_left -= 1
        self.events = []
        start = list(self.arm)
        sliding = dx != 0.0 or dy != 0.0 or dyaw != 0.0
        steps = max(1, int(math.ceil(max(math.hypot(dx, dy, dz), abs(dyaw)) / SUB)))
        st, was_damaged = self.st, self.st["damaged"]
        for i in range(1, steps + 1):
            arm = [s + (g - s) * i / steps for s, g in zip(start, goal)]
            new = self._settle(arm, st, sliding)
            if self._load(new, arm) > max_force + 1e-9 and self._load(new, arm) > self._load(st, self.arm) + 1e-9:
                self.events.append("force limit reached")
                break
            st, self.arm = new, arm
            if i % 5 == 0:
                self.st = st
                self._frame()
            if st["seated"]:
                break
        if sliding and st["mode"] == "surface":
            st = self._settle(self.arm, st, False)   # at rest, the peg drops in if it fits here
        self.st = st
        if st["seated"]:
            self.events.append("peg seated")
        if st["damaged"] and not was_damaged:
            self.events.append("board damaged")
        self.moved = [a - s for a, s in zip(self.arm, start)]
        self._measure()
        self._frame()
        return self._obs()

    def t_next_peg(self):
        if self.done:
            return self._obs(ok=False, error="the job is over")
        self.jobs[self.index]["result"] = self._result()
        closed = self.jobs[self.index]["result"]["outcome"]
        if self.index + 1 >= len(self.jobs):
            self.done = True
            self.events = [f"peg {self.index + 1} closed: {closed}", "the job is over"]
            return self._obs()
        self._begin(self.index + 1)
        self.events = [f"peg {self.index} closed: {closed}"]
        return self._obs()

    # ---- what the agent sees --------------------------------------------------------------------------
    def _measure(self):
        """One noisy reading per move, so asking again does not average the noise away."""
        st, g = self.st, self.noise.normal
        a = math.radians(self.err[2])
        c, s = math.cos(a), math.sin(a)
        rot = lambda v: (v[0] * c - v[1] * s, v[0] * s + v[1] * c)   # hole frame -> the agent's frame
        fx, fy = rot(st["lat"])
        tx, ty = rot(st["tq"])
        self.reading = {
            "tool": {"x": round(self.arm[0] + g(0, NOISE_POS), 2), "y": round(self.arm[1] + g(0, NOISE_POS), 2),
                     "z": round(self.arm[2] + g(0, NOISE_POS), 2), "yaw": round(self.arm[3] + g(0, NOISE_YAW), 2)},
            "wrench": {"fx": round(fx + g(0, NOISE_F), 1), "fy": round(fy + g(0, NOISE_F), 1), "fz": round(st["fz"] + g(0, NOISE_F), 1),
                       "tx": round(tx + g(0, NOISE_T), 0), "ty": round(ty + g(0, NOISE_T), 0), "tz": round(st["tz"] + g(0, NOISE_T), 0)},
            "moved": {k: round(v + g(0, n), 2) for k, v, n in zip(("dx", "dy", "dz", "dyaw"), self.moved, (NOISE_POS,) * 3 + (NOISE_YAW,))},
        }

    def _obs(self, ok: bool = True, error: str | None = None) -> dict:
        out = {"ok": ok}
        if error:
            out["error"] = error
        out.update(peg=self.index + 1, pegs_total=len(self.jobs), shape=self.jobs[self.index]["shape"], moves_left=self.moves_left)
        out.update(self.reading)
        out.update(seated=bool(self.st["seated"]), events=list(self.events), job_over=self.done)
        return out

    def _frame(self):
        q, st = self.st["q"], self.st
        self.frames.append((self.index, round(q[0], 4), round(q[1], 4), round(math.degrees(q[2]), 4), round(st["h"], 4), st["mode"]))

    def task(self) -> dict:
        return {
            "units": "millimetres, degrees, newtons, newton-millimetres",
            "pegs": [{"peg": i + 1, "shape": j["shape"], "outline": [[round(x, 3), round(y, 3)] for x, y in SHAPES[j["shape"]]]}
                     for i, j in enumerate(self.jobs)],
            "clearance": CLEARANCE, "chamfer": CHAMFER, "full_depth": DEPTH, "start_height": START_Z,
            "estimate_error": {"xy_radius": ERR_XY, "yaw": ERR_YAW, "height": ERR_Z},
            "wrist": {"k_vertical_N_per_mm": K_Z, "k_sideways_N_per_mm": K_LAT, "k_twist_Nmm_per_deg": K_ROT, "twist_lever_mm": R_REF},
            "chamfer_centring_share": KAPPA, "wall_friction": MU, "free_friction_N": F0,
            "seat_force": SEAT_FORCE, "damage_force": DAMAGE_FORCE, "max_force_range": [FORCE_MIN, FORCE_MAX],
            "move_limits": {"step": MAX_STEP, "turn": MAX_TURN},
            "working_range": {"xy": WORK_XY, "yaw": WORK_YAW, "z": list(WORK_Z)},
            "moves_per_peg": self.budget,
            "sensor_noise": {"position": NOISE_POS, "yaw": NOISE_YAW, "force": NOISE_F, "torque": NOISE_T},
        }

    # ---- score ----------------------------------------------------------------------------------------
    def score(self) -> dict:
        res = []
        for i, j in enumerate(self.jobs):
            if j["result"] is not None:
                res.append(j["result"])
            elif i == self.index and not self.done:
                res.append(self._result())   # the peg in hand when the agent stopped, as it stands
            else:
                res.append({"shape": j["shape"], "score": 0.0, "outcome": "never started", "moves_used": 0})
        total = sum(r["score"] for r in res) / len(res)
        return {"score": round(total, 4), "seated": sum(r["outcome"] == "seated" for r in res), "pegs": len(res),
                "damaged": sum(r["outcome"] == "board damaged" for r in res),
                "flawless": all(r["outcome"] == "seated" for r in res),
                "moves_used": sum(r["moves_used"] for r in res),
                "detail": {"pegs": res, "damage": [r["shape"] for r in res if r["outcome"] == "board damaged"]}}
