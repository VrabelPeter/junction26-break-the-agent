"""Do nothing, and fetch-the-tools-then-stop, on many rooms: one non-zero score is a finding.

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/donothing_many.py --seeds $(seq 1 40)

Also three cheap "a few plausible actions, then quit" variants: drive to the table and stop; fetch only the bin,
stand it at the table edge and stop; fetch the tools and hold the bin under the table edge and stop.
"""
import math

import rt


def fetch_stop(w):
    rt.P.ROOM = rt.P.Told()
    rt.P.fetch_tools(w)


def drive_stop(w):
    w.drive_to(0.3, -1.6, math.pi / 2)


def bin_at_edge_stop(w):
    rt.P.ROOM = rt.P.Told()
    rt.P.fetch_tools(w, tools=("bin",))
    rt.P.Bin().set_down(w, rt.P.Side("table", "south"), 0.3)


POLICIES = dict(do_nothing=lambda w: None, fetch_stop=fetch_stop, drive_stop=drive_stop, bin_at_edge_stop=bin_at_edge_stop)


def one(job):
    name, seed, level = job
    w = rt.World(seed, level, privileged=True)
    POLICIES[name](w)
    return name, level, seed, w.score()


if __name__ == "__main__":
    a = rt.args(default_seeds=range(1, 41)).parse_args()
    jobs = [(p, s, L) for p in POLICIES for L in (1, 2, 3) for s in a.seeds]
    out = rt.pmap(one, jobs, a.procs)
    for p in POLICIES:
        for L in (1, 2, 3):
            rows = [(s, r) for n, l, s, r in out if n == p and l == L]
            nonzero = [(s, r["score"]) for s, r in rows if r["score"] != 0]
            mistakes = [(s, r["mistakes"]) for s, r in rows if r["mistakes"]]
            print(f"{p:18s} level {L}  seeds {len(rows)}  max {max(r['score'] for _, r in rows):g}  non-zero {nonzero}  mistakes {mistakes}")
