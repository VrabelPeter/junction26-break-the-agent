"""Accepting mistakes versus honest play (levels 2 and 3), seed by seed.

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/sloppy.py --level 2 --seeds 1 2 3 4 5

Policies (all moves are the agent's own tool calls; the strokes are the reference's, from sweep/policies.py):

  honest        the repo's reference_privileged (told where things are, never risks a personal item)
  take_along    the same controller, but blind to personal items: it sweeps every piece of trash and takes
                along whatever personal item lies in the stroke (a mistake each, knowingly accepted)
  bulldoze      knows nothing about the room: sweeps the whole table lane by lane into the bin, then (level 3)
                the sofa seat, until the robot time is used up
  bulldoze_table  the same, table only
  take_along_camera  take_along in the STANDARD setting: the reference's own camera pipeline finds the things,
                and the personal items it reports are thrown away before planning. Compare with the camera
                reference (`baselines.py --policy reference`), which is what judges see as honest play.
"""
import rt

P, S = rt.P, rt.S


class Careless(P.Told):
    """Told where things are, but personal items are left out of the planning: nothing blocks a stroke."""

    def objects(self, w):
        return {n: o for n, o in super().objects(w).items() if o["trash"]}


def honest(w):
    P.ROOM = P.Told()
    P.sweep_all(w)


def take_along(w):
    P.ROOM = Careless()
    try:
        P.sweep_all(w)
    finally:
        P.ROOM = P.Told()


def take_along_camera(w):
    class CarelessSeen(P.Seen):
        def objects(self, w):
            return {n: o for n, o in super().objects(w).items() if o["trash"]}
    try:
        P.ROOM = CarelessSeen(w)
        P.sweep_all(w)
    finally:
        P.ROOM = P.Told()


def _lanes(surface):
    s = S.SURFACES[surface]
    margin = P.HEAD_HALF + (0.015 if surface == "sofa" else 0.0)
    x, out = s["x"][0] + margin, []
    while x < s["x"][1] - margin:
        out.append(round(x, 3))
        x += 0.20
    out.append(round(s["x"][1] - margin, 3))
    return out


def _bulldoze(w, surfaces):
    P.ROOM = P.Told()                         # only used for the tool handles at the station
    P.fetch_tools(w, tools=("brush",))
    for surface in surfaces:                  # pull everything towards the front edge, no bin in the way
        side = P.Side(surface, "south")
        for x in _lanes(surface):
            P.gather(w, side, x, P.GATHER_REACH)
    P.fetch_tools(w, tools=("bin",))
    bin_ = P.Bin()
    for surface in surfaces:                  # then every lane over the edge into the bin
        side = P.Side(surface, "south")
        for x in _lanes(surface):
            if bin_.spot is not None and not bin_.take_up(w):
                return
            bin_.set_down(w, side, x)
            P.into_bin(w, side, x, P.FINAL_REACH)


def bulldoze(w):
    _bulldoze(w, ("table", "sofa") if w.level >= 3 else ("table",))


def bulldoze_table(w):
    _bulldoze(w, ("table",))


POLICIES = dict(honest=honest, take_along=take_along, bulldoze=bulldoze, bulldoze_table=bulldoze_table, take_along_camera=take_along_camera)


def one(job):
    name, seed, level = job
    w = rt.World(seed, level, privileged=not name.endswith("_camera"))
    err = ""
    try:
        POLICIES[name](w)
    except RuntimeError as e:                 # out of robot time: what is in the bin by now counts
        err = str(e)
    except Exception as e:
        err = repr(e)
    r = w.score()
    r["error"] = err
    return name, seed, r


if __name__ == "__main__":
    ap = rt.args()
    ap.add_argument("--policy", nargs="+", default=["honest", "take_along", "bulldoze"], choices=list(POLICIES))
    a = ap.parse_args()
    out = rt.pmap(one, [(p, s, a.level) for p in a.policy for s in a.seeds], a.procs)
    for p in a.policy:
        rows = [(s, r) for n, s, r in out if n == p]
        if a.v:
            for s, r in rows:
                print(f"  {p} seed {s}: {rt.short(r)}  {r['error']}")
        print(f"{p:15s} level {a.level}  mean {rt.mean(r['score'] for _, r in rows):.3f}  " + " ".join(f"{s}:{r['score']:g}" for s, r in rows))
