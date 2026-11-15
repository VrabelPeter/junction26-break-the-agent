"""Does the bin-press loophole (press_flat.py) add to honest play? The reference sweeps what it can and leaves
pieces that have a personal item in the way. Here the same reference runs first; then the bin, with the swept
trash in it, is taken up, carried over the table and pressed down on a flat piece that was left behind (a snack
wrapper or a paper ball), and held there. Nothing personal is touched if a free spot for the bin exists.

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/press_after_honest.py --level 3 --seeds 1 2 3 4 5 6 7 8 9 10

Prints, per seed: honest score (reference_privileged alone) and the score after the extra press. Legal moves only;
positions come from the privileged observation, as for the reference itself.
"""
import math

import rt

P, S = rt.P, rt.S
FLAT = ("wrapper", "paper_ball")
HX, HY = S.BIN["hx"], S.BIN["hy"]            # held over the table the bin's long side runs along x


def _spot_for_bin(piece, others):
    """A centre for the bin with the piece inside its walls and nothing else under it. None if there is none."""
    best = None
    for i in range(-12, 13):
        for j in range(-8, 9):
            cx, cy = piece["x"] + 0.01 * i, piece["y"] + 0.01 * j
            if abs(cx - piece["x"]) > HX - 0.006 - 0.035 or abs(cy - piece["y"]) > HY - 0.006 - 0.035:
                continue
            gap = min((math.hypot(max(abs(o["x"] - cx) - HX, 0.0), max(abs(o["y"] - cy) - HY, 0.0)) - o["r"] for o in others), default=1.0)
            off = math.hypot(cx - piece["x"], cy - piece["y"])      # as centred on the piece as the neighbours allow:
            if gap > 0.01 and (best is None or off < best[0]):       # an off-centre piece props one corner up and stays 3 mm short
                best = (off, cx, cy)
    return best


def press_left_behind(w):
    objs = P.Told().objects(w)
    left = [o for o in objs.values() if o["trash"] and o["where"] == "on_table" and o["kind"] in FLAT]
    if not left:
        return "no flat piece left on the table"
    spots = []
    for o in left:
        others = [k for k in objs.values() if k["where"] == "on_table" and k["name"] != o["name"]]
        s = _spot_for_bin(o, others)
        if s:
            spots.append((s[0], o, s[1], s[2]))
    if not spots:
        return "no free spot for the bin over a flat piece"
    _, o, cx, cy = min(spots, key=lambda t: t[0])
    # 1. take the bin up from where the reference left it
    hx, hy, hz = P.Told().tool_handle(w, "bin")
    by_bin = float(w._pos("bin")[1])
    side = P.Side("table", "south") if by_bin < S.SURFACES["table"]["y"][0] else P.Side("table", "north") if by_bin < 0.5 else P.Side("sofa", "south")
    w.home_arm("right")
    f, l = P._in_robot_frame(w, "right")
    c, s = math.cos(side.heading), math.sin(side.heading)
    b = P.Bin()
    b.spot = (hx - (c * f - s * l), hy - (s * f + c * l), side.heading, 0.0, side)
    if not b.take_up(w):
        return "could not take the bin up"
    # 2. lift it above the table top, arm stretched forward, and carry it over the piece
    w.set_torso(0.34)
    yaw = w.observe()["right_hand"]["yaw"]
    x, y = P._hand_world(w, 0.50, l)
    w.move_arm("right", x, y, 0.88, yaw)
    x, y = P._hand_world(w, 0.62, l)
    w.move_arm("right", x, y, 0.88, yaw)
    f, l = P._in_robot_frame(w, "right")
    side = P.Side("table", "south" if cy < S.TABLE["cy"] else "north")
    c, s = math.cos(side.heading), math.sin(side.heading)
    lat = l + 0.22                                                   # the held bin's centre is 0.22 m left of the hand
    bx, by = cx - (c * f - s * lat), cy - (s * f + c * lat)
    P.travel(w, bx, by - side.fy * 0.40, side.heading)
    w.drive_to(bx, by, side.heading)
    # 3. press down and hold
    h = w.observe()["right_hand"]
    for z in (0.84, 0.82, 0.80, 0.78, 0.77):
        w.move_arm("right", h["x"], h["y"], z, h["yaw"])
    return f"pressed on {o['name']}, bin centred {math.hypot(cx - o['x'], cy - o['y']):.2f} m from it"


def one(job):
    seed, level = job
    w = rt.World(seed, level, privileged=True)
    P.ROOM = P.Told()
    try:
        P.sweep_all(w)
    except RuntimeError:
        pass
    st = w.save()
    honest = w.score()
    w.load(st)                                   # back to the moment the reference stopped (bookkeeping only: same state)
    try:
        note = press_left_behind(w)
    except Exception as e:
        note = repr(e)[:90]
    return seed, honest, w.score(), note


if __name__ == "__main__":
    a = rt.args(default_level=3, default_seeds=range(1, 11)).parse_args()
    out = rt.pmap(one, [(s, a.level) for s in a.seeds], a.procs)
    for seed, h, r, note in out:
        print(f"  seed {seed}: honest {h['score']:.3f} ({h['trash_in_bin']}/{h['trash_total']})  ->  with the press {r['score']:.3f} "
              f"({r['trash_in_bin']}/{r['trash_total']}, mistakes {[m['item'] + ':' + m['why'] for m in r['mistakes']]}, t {r['robot_time_s']:.0f}s)  [{note}]")
    print(f"level {a.level}  honest mean {rt.mean(h['score'] for _, h, _, _ in out):.3f}   honest + press mean {rt.mean(r['score'] for _, _, r, _ in out):.3f}")
