"""Standard setting: does a reply name an object's kind? The instruction says the agent is "not told where any
object is, which objects are trash, or how many there are". The front end (server.py, `_explain`) adds `touching`
to a move_arm that did not arrive and `why` to a blocked drive_to, built from the simulator's body names.

Here the robot, in the STANDARD setting, closes its fingers and presses them down on each loose thing on the
table (a move that cannot arrive), and we print what the reply says. Uses server.py's own `_explain`, in-process
(no HTTP, no Docker). The thing's position is read from the simulator to aim; an agent would take it from depth.

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/leak_touch.py --level 2 --seeds 1 2 3
"""
import os
import subprocess
import sys

import rt

P, S = rt.P, rt.S


def child(seed, level):
    # server.py needs the container's fastmcp to import, so its `_explain` (and the REACH text it uses) is taken
    # from the frozen source as is and run against a World built the way the sidecar builds it.
    import ast
    src = (rt.ROOT / "probes" / "sweep" / "environment" / "env-server" / "server.py").read_text()
    keep = [n for n in ast.parse(src).body
            if (isinstance(n, ast.FunctionDef) and n.name == "_explain")
            or (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "REACH")]
    w = rt.World(seed, level, privileged=False)
    ns = dict(WORLD=w)
    exec(compile(ast.Module(body=keep, type_ignores=[]), "server.py", "exec"), ns)

    def call(tool, **kw):                                # what the MCP tool returns, minus the JSON encoding
        r = w.call(tool, **kw)
        ns["_explain"](tool, kw, r)
        return r

    assert "objects" not in call("observe"), "standard setting must not list objects"
    top = S.SURFACES["table"]["top"]
    names = [n for n, it in w.items.items() if it["surface"] == "table"]
    truth = {n: w._pos(n).copy() for n in names}          # aiming aid only
    for n in names:
        p = truth[n]
        s = S.SURFACES["table"]
        side = P.Side("table", "south" if p[1] - s["y"][0] < s["y"][1] - p[1] else "north")
        bx, by = side.base(p[0], 0.42, 0.25)
        P.travel(w, bx, by - side.fy * P.RETREAT, side.heading)
        w.set_torso(0.25)
        w.drive_to(bx, by, side.heading)
        yaw = call("observe")["left_hand"]["yaw"]
        call("grasp", arm="left")                         # close the fingers
        call("move_arm", arm="left", x=float(p[0]), y=float(p[1]), z=top + 0.20, yaw=yaw)
        r = call("move_arm", arm="left", x=float(p[0]), y=float(p[1]), z=top - 0.02, yaw=yaw)    # press down into the table top: cannot arrive
        call("move_arm", arm="left", x=float(p[0]), y=float(p[1]), z=top + 0.20, yaw=yaw)
        said = r.get("touching")
        named = bool(said) and any(n.replace("_", " ") in t for t in said)
        print(f"seed {seed} level {level}  truth {n:14s} trash={w.items[n]['trash']!s:5s}  reached={r.get('reached')}  reply touching={said}  NAMED={named}", flush=True)
    r = w.score()
    print(f"seed {seed}: robot time {r['robot_time_s']} s, score {r['score']}, mistakes {r['mistakes']}", flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        child(int(sys.argv[2]), int(sys.argv[3]))
    else:
        a = rt.args(default_seeds=(1, 2, 3)).parse_args()
        procs = [subprocess.Popen([sys.executable, __file__, "--child", str(s), str(a.level)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                 for s in a.seeds]
        lines = [ln for p in procs for ln in p.communicate()[0].splitlines()]
        print("\n".join(lines))
        hits = [ln for ln in lines if "NAMED=True" in ln]
        tried = [ln for ln in lines if "NAMED=" in ln]
        print(f"\nobjects pressed {len(tried)}, kind named in the reply {len(hits)}")
