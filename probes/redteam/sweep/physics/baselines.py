"""Honest play and the two baselines, per seed, with the repo's own scripted policies.

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/baselines.py --level 2 --seeds 1 2 3 4 5 \
        --policy do_nothing stop_early reference_privileged reference
"""
import rt


def one(job):
    name, seed, level = job
    w = rt.World(seed, level, privileged=(name == "reference_privileged"))
    try:
        r = rt.P.POLICIES[name](w)
    except Exception as e:                       # as in sweep.run: a controller that gives up is still scored
        r = w.score()
        r["error"] = repr(e)
    return name, seed, r


if __name__ == "__main__":
    ap = rt.args()
    ap.add_argument("--policy", nargs="+", default=["do_nothing", "stop_early", "reference_privileged", "reference"])
    a = ap.parse_args()
    out = rt.pmap(one, [(p, s, a.level) for p in a.policy for s in a.seeds], a.procs)
    for p in a.policy:
        rows = [(s, r) for n, s, r in out if n == p]
        if a.v:
            for s, r in rows:
                print(f"  {p} seed {s}: {rt.short(r)} {r.get('error', '')}")
        print(f"{p:22s} level {a.level}  mean {rt.mean(r['score'] for _, r in rows):.3f}  " + " ".join(f"{s}:{r['score']:g}" for s, r in rows))
