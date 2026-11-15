"""Ways to have trash "in the bin" without sweeping it in, with legal moves only.

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/bin_tricks.py --level 2 --seeds 1 2 3 4 5

  press_on_table   fetch the bin, carry it over the table and lower it onto a piece of trash, keep holding it
  press_and_drop   the same, then let go (the bin is left standing or lying on the table)
  drop_from_high   hold the bin high over the table and let it fall on the trash
  tip_bin          fetch the bin, set it at the table edge, then knock it over with the hand (cost of a tipped bin alone)
"""
import rt

P, S = rt.P, rt.S
TOP = S.SURFACES["table"]["top"]


def _bin_over(w, z_hand):
    """Fetch the bin and bring it over the piece of trash nearest the south edge. Returns the hand pose used."""
    P.ROOM = P.Told()
    P.fetch_tools(w, tools=("bin",))
    w.set_torso(0.34)
    trash = [o for o in w.observe()["objects"] if o["trash"] and o["where"] == "on_table"]
    o = min(trash, key=lambda o: o["y"])
    side = P.Side("table", "south")
    h = w.observe()["right_hand"]
    w.move_arm("right", h["x"], h["y"], z_hand, h["yaw"])                 # lift the bin above the table top first
    forward, lateral = P._in_robot_frame(w, "right")
    # held, the bin's centre is 0.22 m to the left of the right hand: put that centre over the piece
    bx, by = o["x"] - side.lx * (lateral + 0.22), o["y"] - forward
    P.travel(w, bx, by - 0.35, side.heading)
    w.drive_to(bx, by, side.heading)
    return o, w.observe()["right_hand"]


def press_on_table(w, drop=False):
    o, h = _bin_over(w, 0.88)
    for z in (0.84, 0.82, 0.80, 0.78):                                     # bin bottom = hand - 0.348: down onto the table top
        w.move_arm("right", h["x"], h["y"], z, h["yaw"])
    if drop:
        w.release("right")


def press_and_drop(w):
    press_on_table(w, drop=True)


def drop_from_high(w):
    o, h = _bin_over(w, 0.88)
    w.release("right")


def tip_bin(w):
    P.ROOM = P.Told()
    P.fetch_tools(w, tools=("bin",))
    b = P.Bin()
    b.set_down(w, P.Side("table", "south"), 0.3)
    h = w.observe()["right_hand"]
    w.drive_to(*b.spot[:3])
    w.move_arm("right", h["x"], h["y"] + 0.02, 0.30, h["yaw"])            # hand down beside the bar, then push the bin over sideways
    h = w.observe()["right_hand"]
    w.move_arm("right", h["x"] - 0.30, h["y"], 0.30, h["yaw"])


POLICIES = dict(press_on_table=press_on_table, press_and_drop=press_and_drop, drop_from_high=drop_from_high, tip_bin=tip_bin)


def one(job):
    name, seed, level = job
    w = rt.World(seed, level, privileged=True)
    err = ""
    try:
        POLICIES[name](w)
    except Exception as e:
        err = repr(e)[:80]
    r = w.score()
    r["error"] = err
    r["bin"] = [round(float(v), 2) for v in w._pos("bin")]
    return name, seed, r


if __name__ == "__main__":
    a = rt.args().parse_args()
    out = rt.pmap(one, [(p, s, a.level) for p in POLICIES for s in a.seeds], a.procs)
    for p in POLICIES:
        rows = [(s, r) for n, s, r in out if n == p]
        if a.v:
            for s, r in rows:
                print(f"  {p} seed {s}: {rt.short(r)}  bin at {r['bin']}  {r['error']}")
        print(f"{p:15s} level {a.level}  mean {rt.mean(r['score'] for _, r in rows):.3f}  " + " ".join(f"{s}:{r['score']:g}" for s, r in rows))
