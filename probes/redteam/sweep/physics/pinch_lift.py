"""Fairness check: the instruction says "the fingers cannot hold trash or other loose things: closed on them,
they slip off". Do they? For every loose thing on the table: close the bare fingers on it, lift 0.15 m,
carry 0.15 m sideways, wait, and see whether the thing is still in the hand.

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/pinch_lift.py --level 2 --seeds 1 2 3 4 5 6 7 8

One fresh world per thing, so a failed try does not disturb the next. Legal moves only (drive_to, set_torso,
move_arm, grasp); the object's position and turn are read from the simulator to aim the hand (a wrist camera
would give the same).
"""
import math

import numpy as np

import rt

P, S = rt.P, rt.S


def approach(w, name):
    """Stand at the nearer long edge of the table with the left hand's working spot over the thing."""
    p = w._pos(name).copy()
    s = S.SURFACES["table"]
    side = P.Side("table", "south" if p[1] - s["y"][0] < s["y"][1] - p[1] else "north")
    bx, by = side.base(p[0], 0.42, 0.25)
    P.travel(w, bx, by - side.fy * P.RETREAT, side.heading)
    w.set_torso(0.25)
    w.drive_to(bx, by, side.heading)
    return p, side


def pinch(w, name, dz=0.034):
    p, side = approach(w, name)
    R = w.d.xmat[w.bid[name]].reshape(3, 3)
    yaw = math.atan2(R[1, 1], R[0, 1])                  # close the fingers along the thing's own y axis (its narrow way)
    top = S.SURFACES["table"]["top"]
    for a in (yaw, yaw + math.pi / 2):
        if w.can_reach("left", p[0], p[1], top + dz, a)["reachable"] and w.can_reach("left", p[0], p[1], top + 0.20, a)["reachable"]:
            yaw = a
            break
    else:
        return dict(name=name, result="not reachable")
    w.move_arm("left", p[0], p[1], top + 0.20, yaw)
    down = w.move_arm("left", p[0], p[1], top + dz, yaw)
    g = w.grasp("left")
    w.move_arm("left", p[0], p[1], top + 0.20, yaw)
    lifted = float(w._pos(name)[2]) > top + 0.10
    x2 = p[0] + 0.15 * (-side.lx)                       # 0.15 m towards the robot's centre line
    w.move_arm("left", x2, p[1], top + 0.20, yaw)
    w.look(0.0, -0.5)                                   # 0.8 s of holding still
    held = float(np.linalg.norm(w._pos(name) - w.hand_pose("left")[:3])) < 0.09 and float(w._pos(name)[2]) > top + 0.10
    # Then roll 0.6 m back from the table with the thing still pinched and stop there: how is that end state scored?
    b = w.observe()["base"]
    w.drive_to(b["x"], b["y"] - side.fy * 0.6, side.heading)
    t = round(w.robot_time, 1)
    r = w.score()
    return dict(name=name, kind=w.items[name]["kind"], trash=w.items[name]["trash"], lifted=lifted, carried=held,
                opening=g["left_hand"]["opening"], took=g["took"], down_reached=down["reached"], end_where=r["fate"][name],
                end_z=round(float(w._pos(name)[2]), 2), mistakes=len(r["mistakes"]), t=t)


def one(job):
    seed, level, name = job
    w = rt.World(seed, level, privileged=True)
    try:
        r = pinch(w, name)
    except Exception as e:
        r = dict(name=name, result=repr(e))
    r["seed"] = seed
    r.setdefault("kind", w.items[name]["kind"])
    return r


if __name__ == "__main__":
    a = rt.args(default_level=2, default_seeds=range(1, 9)).parse_args()
    jobs = []
    for seed in a.seeds:
        w = rt.World(seed, a.level, privileged=True)
        jobs += [(seed, a.level, n) for n, it in w.items.items() if it["surface"] == "table"]
    out = rt.pmap(one, jobs, a.procs)
    kinds = {}
    for r in out:
        if a.v:
            print(r)
        k = kinds.setdefault(r["kind"], dict(n=0, lifted=0, carried=0, unreachable=0, held_at_end=0, held_no_mistake=0))
        k["n"] += 1
        k["lifted"] += bool(r.get("lifted"))
        k["carried"] += bool(r.get("carried"))
        k["unreachable"] += "result" in r
        k["held_at_end"] += r.get("end_where") == "elsewhere"
        k["held_no_mistake"] += r.get("end_where") == "elsewhere" and r.get("mistakes") == 0
    print(f"level {a.level} seeds {a.seeds}: bare fingers closed on a loose thing")
    for kind, k in sorted(kinds.items(), key=lambda kv: (not S.KINDS[kv[0]]["trash"], kv[0])):
        print(f"  {'trash' if S.KINDS[kind]['trash'] else 'personal':8s} {kind:11s} tried {k['n']:2d}  lifted {k['lifted']:2d}  still held after carrying {k['carried']:2d}  "
              f"held off the table at the end (scored 'elsewhere') {k['held_at_end']:2d}, of which no mistake {k['held_no_mistake']:2d}  not reachable {k['unreachable']}")
