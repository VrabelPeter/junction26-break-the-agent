"""Scripted controllers. Each takes `call(tool, **args) -> dict` and the dict from `get_task`: exactly
what the agent under test gets. None of them reads anything else."""
from __future__ import annotations

import math

PRESS = 12.0   # probing force on the board face: below the damage force, strong enough for the chamfer to work
PUSH = 10.0    # insertion force: above the seat force


def _inside(o, press):
    """After pressing with `press`, a peg on the board face shows the whole press as fz; one that
    dropped into the hole shows only wall friction."""
    return o["wrench"]["fz"] < press - 3.0


def _push_home(call, t, o):
    """Peg is in the hole: step the wrist the way the walls push it, then go down."""
    k_lat, k_rot = t["wrist"]["k_sideways_N_per_mm"], t["wrist"]["k_twist_Nmm_per_deg"]
    while not o["seated"] and o["moves_left"] > 0 and o["ok"]:
        w = o["wrench"]
        if math.hypot(w["fx"], w["fy"]) > 1.0 or abs(w["tz"]) > 15:
            o = call("move", dx=w["fx"] / k_lat, dy=w["fy"] / k_lat, dyaw=w["tz"] / k_rot, max_force=PUSH)
        else:
            o = call("move", dz=-4.0, max_force=PUSH)
    return o


def _insert(call, t):
    """One peg, by feel. On the board face the torque says which side the peg is supported on, so slide
    away from that side. A turned star or cross is supported all round and that rule only circles the
    hole: then the hole is at the centre of the circle. Once centred, the chamfer says the rest."""
    k_lat, k_rot = t["wrist"]["k_sideways_N_per_mm"], t["wrist"]["k_twist_Nmm_per_deg"]
    o = call("move", dz=-5.0, max_force=PRESS)
    yaw0 = o["tool"]["yaw"]
    step, last, flips, trail, centred = 1.0, None, 0, [], False
    yaw_plan = [3.2, -3.2]
    while o["ok"] and not _inside(o, PRESS) and o["moves_left"] > 4:
        w = o["wrench"]
        fz = max(w["fz"], 1.0)
        cop = (-w["ty"] / fz, w["tx"] / fz)           # where the board supports the peg, relative to its centre
        size = math.hypot(*cop)
        if math.hypot(w["fx"], w["fy"]) > 0.8 or abs(w["tz"]) > 12:
            # On the chamfer: it pushes straight towards the fit. Follow it, a little further than the least it could mean.
            o = call("move", dx=1.6 * w["fx"] / k_lat, dy=1.6 * w["fy"] / k_lat, dyaw=1.6 * w["tz"] / k_rot, max_force=PRESS + 2)
            continue
        if centred and yaw_plan:
            # Centred, not in, chamfer silent: turned too far for the chamfer to reach. Try a turn each way.
            turn = yaw0 + yaw_plan[0] - o["tool"]["yaw"]
            if abs(turn) <= t["move_limits"]["turn"]:
                yaw_plan.pop(0)
            o = call("move", dyaw=max(-t["move_limits"]["turn"], min(t["move_limits"]["turn"], turn)), max_force=PRESS + 2)
            continue
        trail.append((o["tool"]["x"], o["tool"]["y"]))
        d = (-cop[0] / max(size, 1e-9), -cop[1] / max(size, 1e-9))
        if last and d[0] * last[0] + d[1] * last[1] < 0:
            flips += 1
            step = max(0.3, step / 2)
        circling = flips >= 3 or (len(trail) >= 5 and math.dist(trail[-1], trail[-5]) < 1.5 * step)
        if circling and len(trail) >= 4:
            k = min(len(trail), 5)
            cx, cy = sum(p[0] for p in trail[-k:]) / k, sum(p[1] for p in trail[-k:]) / k
            o = call("move", dx=cx - o["tool"]["x"], dy=cy - o["tool"]["y"], max_force=PRESS + 2)
            step, last, flips, trail, centred = 0.3, None, 0, [], True
        elif size < 1.5:
            centred = True
            if not yaw_plan:
                o = call("move", dx=d[0] * 0.2, dy=d[1] * 0.2, max_force=PRESS + 2)
        else:
            last = d
            o = call("move", dx=d[0] * step, dy=d[1] * step, max_force=PRESS + 2)
    if o["ok"] and _inside(o, PRESS):
        o = _push_home(call, t, o)
    return o


def reference(call, task, **_):
    for _ in task["pegs"]:
        _insert(call, task)
        call("next_peg")


def stop_early(call, task, **_):
    """Does the first peg properly, then walks away."""
    _insert(call, task)


def do_nothing(call, task, **_):
    return


def straight_down(call, task, **_):
    """Trusts the estimate: goes down where vision says the hole is and pushes."""
    for _ in task["pegs"]:
        o = call("move", dz=-5.0, max_force=PRESS)
        if _inside(o, PRESS):
            _push_home(call, task, o)
        call("next_peg")


def blind_search(call, task, **_):
    """Never looks at the torque: presses at one spot after another on a spiral, at three yaws, until the peg drops."""
    spots = [(0.0, 0.0)]
    for ring in range(1, 4):
        n = 6 * ring
        spots += [(0.9 * ring * math.cos(2 * math.pi * i / n), 0.9 * ring * math.sin(2 * math.pi * i / n)) for i in range(n)]
    plan = [(x, y, yaw) for yaw in (0.0, 2.5, -2.5) for x, y in spots]
    for _ in task["pegs"]:
        o = call("move", dz=-5.0, max_force=PRESS)
        for x, y, yaw in plan[1:]:
            if not o["ok"] or _inside(o, PRESS) or o["moves_left"] <= 4:
                break
            o = call("move", dx=x - o["tool"]["x"], dy=y - o["tool"]["y"], dyaw=yaw - o["tool"]["yaw"], max_force=PRESS + 2)
        if o["ok"] and _inside(o, PRESS):
            _push_home(call, task, o)
        call("next_peg")


POLICIES = {"do_nothing": do_nothing, "stop_early": stop_early, "straight_down": straight_down,
            "blind_search": blind_search, "reference": reference}
