"""In-process runner: python -m shapeboard.run --policy reference --seeds 1 2 3 [-v] [--budget 30]"""
import argparse
import json
import statistics

from .policies import POLICIES
from .sim import BUDGET, World


def play(policy: str, seed: int, budget: int = BUDGET):
    w = World(seed, budget=budget)
    POLICIES[policy](lambda tool, **a: json.loads(w.call(tool, **a)), w.task())
    return w, w.score()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", nargs="+", default=list(POLICIES))
    ap.add_argument("--seeds", nargs="+", type=int, default=list(range(1, 11)))
    ap.add_argument("--budget", type=int, default=BUDGET)
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    for p in a.policy:
        res = [play(p, s, a.budget)[1] for s in a.seeds]
        sc = [r["score"] for r in res]
        pegs = sum(r["pegs"] for r in res)
        used = [d["moves_used"] for r in res for d in r["detail"]["pegs"] if d["outcome"] == "seated"]
        print(f"{p:14s} mean {statistics.mean(sc):.3f}  min {min(sc):.3f}  max {max(sc):.3f}  seated {sum(r['seated'] for r in res)}/{pegs}"
              f"  damaged {sum(r['damaged'] for r in res)}  moves per seated peg {statistics.mean(used) if used else 0:.1f} (max {max(used) if used else 0})")
        if a.v:
            for s, r in zip(a.seeds, res):
                print(f"   seed {s}: {r['score']:.3f}  " + "; ".join(f"{d['shape']} {d['outcome']} ({d['moves_used']})" for d in r["detail"]["pegs"]))
