"""Episode end and time: the 900 s limit, moves that begin just before it, what the settle does to held things,
and determinism.

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/timing.py --level 2 --seeds 3

1. limit: the clock is set by hand to 899.5 s (to save wall time; an agent gets there with ~1100 `look` calls),
   then one legal drive_to to a point 300 m away is started. Does it run past the limit, and for how long?
2. held bin: the bin is fetched with legal moves and held in the air; all trash is then put into it by hand (to
   read the scorer: not an agent move). Does a bin in the hand count, and does the 2 s settle drop it?
3. determinism: the same seed and calls twice in one process and once in another process.
"""
import hashlib
import math

import numpy as np

import rt
import sloppy
import where_probe

P = rt.P


def limit(seed, level):
    w = rt.World(seed, level, privileged=True)
    w.robot_time = 899.5                                    # by hand
    b0 = w.base_pose().copy()
    r = w.call("drive_to", x=b0[0], y=-300.0, heading=math.pi / 2)
    print(f"1. drive_to started at 899.5 s: ok={r['ok']} reached={r.get('reached')}  clock now {w.robot_time:.1f} s "
          f"(limit 900), base moved {np.linalg.norm(w.base_pose()[:2] - b0[:2]):.2f} m")
    r = w.call("drive_to", x=b0[0], y=b0[1], heading=math.pi / 2)
    print(f"   next call: {r}")
    print(f"   score {w.score()['score']}")


def held_bin(seed, level):
    w = rt.World(seed, level, privileged=True)
    P.ROOM = P.Told()
    P.fetch_tools(w, tools=("bin",))
    h = w.observe()["right_hand"]
    w.move_arm("right", h["x"], h["y"], 0.75, h["yaw"])     # bin hanging about 0.4 m above the floor
    z0 = float(w._pos("bin")[2])
    R = w.d.xmat[w.bid["bin"]].reshape(3, 3)
    trash = [n for n, it in w.items.items() if it["trash"]]
    for i, n in enumerate(trash):                           # by hand
        where_probe.put(w, n, *(w._pos("bin") + R @ np.array([(-0.08, 0.0, 0.08)[i % 3], (-0.03, 0.03)[i % 2], 0.05 + 0.04 * (i // 3) + 0.03])))
    r = w.score()
    print(f"2. bin held in the hand at height {z0:.2f} -> after the settle {float(w._pos('bin')[2]):.2f}; upright {w.bin_upright()}; "
          f"score {r['score']} trash {r['trash_in_bin']}/{r['trash_total']} mistakes {r['mistakes']}")


def fingerprint(job):
    seed, level = job
    w = rt.World(seed, level, privileged=True)
    try:
        sloppy.take_along(w)
    except RuntimeError:
        pass
    r = w.score()
    return r["score"], r["robot_time_s"], hashlib.sha1(w.d.qpos.tobytes()).hexdigest()[:12]


if __name__ == "__main__":
    a = rt.args(default_seeds=(3,)).parse_args()
    for seed in a.seeds:
        limit(seed, a.level)
        held_bin(seed, a.level)
        here = [fingerprint((seed, a.level)), fingerprint((seed, a.level))]
        there = rt.pmap(fingerprint, [(seed, a.level)], 1)
        print(f"3. same seed, same calls (score, robot time, hash of the final state): {here[0]} | {here[1]} | other process {there[0]}  "
              f"identical={here[0] == here[1] == there[0]}")
