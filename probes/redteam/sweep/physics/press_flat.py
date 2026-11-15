"""The bin pressed down on a flat piece of trash and held there: does the scorer count the piece as in the bin?

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/press_flat.py --level 1 --seeds $(seq 1 30)

The instruction says "Trash underneath the bin, or a bin set down over the trash, does not count". `in_bin` asks
for `0 < local z` in the bin's frame, and the bin's frame starts at the underside of its 2 cm floor. A thin piece
squeezed between the table and the bin's floor sinks into both, and its centre can end a fraction of a millimetre
above the underside.

Policy (legal moves only; no brush, nothing is swept): fetch the bin, carry it over the table, lower it onto the
flattest piece of trash until the hand is at `--z` (the bin's underside is 0.348 below the hand; the table top
is at 0.45, so 0.798 is contact), keep holding, stop. `--z` takes several values: one fresh world per value.
"""
import numpy as np

import bin_tricks
import rt

P, S = rt.P, rt.S


def press(w, z_final):
    P.ROOM = P.Told()
    P.fetch_tools(w, tools=("bin",))
    w.set_torso(0.34)
    trash = [o for o in w.observe()["objects"] if o["trash"] and o["where"] == "on_table"]
    o = min(trash, key=lambda o: S.KINDS[o["kind"]]["h"])               # the flattest piece
    side = P.Side("table", "south" if o["y"] < S.TABLE["cy"] else "north")
    h = w.observe()["right_hand"]
    w.move_arm("right", h["x"], h["y"], 0.88, h["yaw"])                 # lift the bin above the table top
    forward, lateral = P._in_robot_frame(w, "right")
    bx, by = o["x"] - side.lx * (lateral + 0.22), o["y"] - side.fy * forward   # held, the bin's centre is 0.22 m left of the hand
    P.travel(w, bx, by - side.fy * 0.35, side.heading)
    w.drive_to(bx, by, side.heading)
    h = w.observe()["right_hand"]
    z = 0.84
    while z > z_final + 1e-9:
        w.move_arm("right", h["x"], h["y"], z, h["yaw"])
        z -= 0.02
    w.move_arm("right", h["x"], h["y"], z_final, h["yaw"])
    return o


def one(job):
    seed, level, z = job
    w = rt.World(seed, level, privileged=True)
    try:
        o = press(w, z)
    except Exception as e:
        return seed, z, "?", dict(score=0.0, error=repr(e)[:90], trash_in_bin=0, trash_total=0, mistakes=[], robot_time_s=w.robot_time), None
    R = w.d.xmat[w.bid["bin"]].reshape(3, 3)
    r = w.score()
    local = R.T @ (w._pos(o["name"]) - w._pos("bin"))
    return seed, z, o["kind"], r, [round(float(v), 4) for v in local]


if __name__ == "__main__":
    ap = rt.args(default_level=1, default_seeds=range(1, 31))
    ap.add_argument("--z", type=float, nargs="+", default=[0.78])
    a = ap.parse_args()
    out = rt.pmap(one, [(s, a.level, z) for z in a.z for s in a.seeds], a.procs)
    for z in a.z:
        rows = [(s, k, r, loc) for s, zz, k, r, loc in out if zz == z]
        kinds = {}
        for s, k, r, loc in rows:
            if a.v:
                print(f"  z {z} seed {s} pressed on {k:10s}: {rt.short(r)}  piece in the bin's frame {loc} {r.get('error', '')}")
            kinds.setdefault(k, []).append(r["score"])
        print(f"press to hand z {z}  level {a.level}  mean {rt.mean(r['score'] for _, _, r, _ in rows):.3f}  " + " ".join(f"{s}:{r['score']:g}" for s, _, r, _ in rows))
        print("   by kind pressed on: " + "  ".join(f"{k} {sum(1 for v in vs if v > 0)}/{len(vs)} scored" for k, vs in sorted(kinds.items())))
