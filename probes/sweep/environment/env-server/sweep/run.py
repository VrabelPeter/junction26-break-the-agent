"""In-process runner: python -m sweep.run --policy reference_privileged --seeds 1 2 3 --level 1"""
from __future__ import annotations

import argparse
import json
import time

from .policies import POLICIES
from .sim import World


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", nargs="+", default=["do_nothing", "stop_early", "reference_privileged"], choices=list(POLICIES))
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    for name in a.policy:
        scores = []
        for seed in a.seeds:
            w = World(seed, a.level, privileged=(name == "reference_privileged"))      # everything else gets the standard setting
            t = time.time()
            try:
                r = POLICIES[name](w)
            except Exception as e:                      # a controller that gives up still gets scored
                r = w.score()
                r["error"] = repr(e)
            scores.append(r["score"])
            if a.v:
                print(f"  {name} seed {seed}: score {r['score']}  trash {r['trash_in_bin']}/{r['trash_total']}  mistakes {r['mistakes']}  "
                      f"robot time {r['robot_time_s']} s  wall {time.time() - t:.1f} s  {r.get('error', '')}")
                print("    fate", json.dumps(r["fate"]), "milestones", json.dumps(r["milestones"]))
        print(f"{name:22s} level {a.level}  mean {sum(scores) / len(scores):.3f}  {scores}")


if __name__ == "__main__":
    main()
