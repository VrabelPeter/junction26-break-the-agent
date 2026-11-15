"""Tool arguments through World.call: out-of-range, huge, negative, bool, string, NaN, wrong arm, calls after the
score. Prints each reply (shortened), the robot time it cost, whether the simulator state stayed finite, and the
score at the end.

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/fuzz_args.py --level 2 --seeds 1
"""
import math
import time

import numpy as np

import rt

CALLS = [
    ("observe", {}), ("get_task", {}),
    ("drive_to", dict(x=float("nan"), y=0, heading=0)), ("drive_to", dict(x=float("inf"), y=0, heading=0)),
    ("drive_to", dict(x="1", y=0, heading=0)), ("drive_to", dict(x=True, y=False, heading=True)),
    ("drive_to", dict(x=-0.9, y=-1.35, heading=1e9)),
    ("drive_to", dict(x=-0.9, y=-1.35, heading=math.pi / 2)),
    ("drive_to", dict(x=-30.0, y=-1.35, heading=math.pi / 2)),         # through the wall? (30 m away)
    ("drive_to", dict(x=-0.9, y=-1.35, heading=math.pi / 2)),
    ("drive_to", dict(x=-0.9, y=-40.0, heading=math.pi / 2)),
    ("drive_to", dict(x=-0.9, y=-1.35, heading=math.pi / 2)),
    ("move_arm", dict(arm="both", x=0, y=0, z=0.5, yaw=0)), ("move_arm", dict(arm=None, x=0, y=0, z=0.5, yaw=0)),
    ("move_arm", dict(arm="left", x=3.0, y=3.0, z=5.0, yaw=0)),          # far out of reach: refused, free
    ("move_arm", dict(arm="left", x=-1.1, y=-0.85, z=-1.0, yaw=0)),      # below the floor
    ("move_arm", dict(arm="left", x=-1.12, y=-0.85, z=0.56, yaw=1e6)),
    ("can_reach", dict(arm="right", x=20.0, y=0, z=0.5, yaw=0)),
    ("set_torso", dict(height=1e300)), ("set_torso", dict(height=-1e300)), ("set_torso", dict(height=0.25)),
    ("look", dict(pan=1e9, tilt=-1e9)), ("look", dict(pan=0, tilt=-0.55)),
    ("grasp", dict(arm="left")), ("grasp", dict(arm="left")), ("release", dict(arm="left")), ("release", dict(arm="left")),
    ("home_arm", dict(arm="right")),
    ("score", {}), ("place", dict(name="bin", where="start")), ("load", {}), ("camera", dict(name="top")), ("__init__", {}),
]


def brief(r):
    keep = {k: r[k] for k in ("ok", "error", "reached", "moved", "why", "reachable", "took", "released", "time_left_s") if k in r}
    return str(keep)[:150]


def finite(w):
    return bool(np.isfinite(w.d.qpos).all() and np.isfinite(w.d.qvel).all())


if __name__ == "__main__":
    a = rt.args(default_seeds=(1,)).parse_args()
    for seed in a.seeds:
        w = rt.World(seed, a.level, privileged=False)
        start = {n: w._pos(n).copy() for n in w.items}
        for tool, kw in CALLS:
            t0, wall = w.robot_time, time.time()
            try:
                r = brief(w.call(tool, **kw))
            except Exception as e:                    # the MCP front end validates types first; here we see what the core does
                r = "RAISED " + repr(e)[:110]
            print(f"{tool:10s} {str(kw)[:62]:62s} -> {r}  [robot {w.robot_time - t0:.1f} s, wall {time.time() - wall:.1f} s, finite {finite(w)}]")
        moved = {n: round(float(np.linalg.norm(w._pos(n) - start[n])), 3) for n in w.items if np.linalg.norm(w._pos(n) - start[n]) > 0.005}
        base = w.base_pose()
        print("base ended at", np.round(base, 3), "| loose things moved:", moved)
        r = w.score()
        print("score", r["score"], "mistakes", r["mistakes"])
        for tool, kw in [("observe", {}), ("drive_to", dict(x=0, y=-1.5, heading=0)), ("grasp", dict(arm="left")), ("get_task", {})]:
            print("after the score:", tool, "->", brief(w.call(tool, **kw)))
        print("score again:", w.score()["score"])
