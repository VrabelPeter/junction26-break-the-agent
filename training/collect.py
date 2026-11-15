"""Collect experience from the environment: scripted controllers playing the living-room sweep in-process.

    python training/collect.py --seeds 1000-1479 --level 1 --out training/data/episodes_l1.jsonl

Every episode is one JSON line: seed, level, variant, the calls (tool, args, robot time, the simulator's reply:
the same shape as the server's /log and the verifier's commands.json), and the environment's own score.

No language model is involved. The controller is the repository's privileged reference
(sweep/policies.py: reference_privileged) and damaged versions of it, so that the scores spread and
selecting by reward has something to select:

    reference       the reference as it is
    noise:S         Gaussian noise of S metres on the x, y (and z for the arm) of every move
    drop:P          every moving call is skipped with probability P (the controller does not notice)
    stop            the controller stops after K moving calls, K drawn from 3..30 (stop:K fixes K)
    binoff:D        while the bin is carried, the base is driven D metres off in x (sign drawn): the bin ends
                    up beside the place where the trash will fall

The damage is applied between the controller and the simulator; what is logged is what was executed.
Episode i of the seed list gets variant i modulo the number of variants; the random draws of a variant
are seeded by (seed, variant), so a rerun gives the same file.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textenv as T      # noqa: E402

DEFAULT_VARIANTS = "reference,noise:0.01,reference,drop:0.08,noise:0.02,stop,reference,binoff:0.14,noise:0.04,drop:0.2"


class Stopped(RuntimeError):
    """Raised into the controller to end the episode (the reference treats a RuntimeError as 'out of time')."""


class Recorder:
    """Stands between a scripted controller and the World: same method names as the World (the pattern of
    solution/solve.sh's Robot), logs every executed call with its reply, and applies the variant's damage."""

    def __init__(self, world, variant: str = "reference", rng: random.Random | None = None):
        self.w, self.scene = world, world.scene
        self.calls: list[dict] = []
        self.rng = rng or random.Random(0)
        kind, _, val = variant.partition(":")
        self.kind = kind
        self.val = float(val) if val else None
        self.moves = 0
        self.stop_after = None
        if kind == "stop":
            self.stop_after = int(self.val) if self.val is not None else self.rng.randint(3, 30)
        self.bin_sign = self.rng.choice((-1.0, 1.0))
        self._seen = None          # the last observe reply, valid until the next executed move
        if kind not in ("reference", "noise", "drop", "stop", "binoff"):
            raise ValueError(f"unknown variant {variant}")

    # ---- the one path to the simulator ---------------------------------------------------------
    def _call(self, tool: str, **args) -> dict:
        if tool == "observe":
            if self._seen is None:          # the controller asks again and again; nothing changed, so it is one call
                r = self.w.call("observe")
                self.calls.append(dict(tool="observe", args={}, t=round(self.w.robot_time, 2), result=r))
                if not r.get("ok"):
                    raise RuntimeError(r.get("error"))
                self._seen = r
            return self._seen
        if self.stop_after is not None and self.moves >= self.stop_after:
            raise Stopped("stopped early")
        if self.kind == "drop" and self.rng.random() < self.val:
            return self._skipped(tool, args)
        if self.kind == "noise" and tool in ("drive_to", "move_arm"):
            for k in ("x", "y", "z"):
                if k in args:
                    args[k] = args[k] + self.rng.gauss(0.0, self.val)
        if self.kind == "binoff" and tool == "drive_to" and self.w.holding["right"] == "bin":
            args["x"] = args["x"] + self.bin_sign * self.val
        args = T.clean_args(tool, args)
        t0 = round(self.w.robot_time, 2)
        r = self.w.call(tool, **args)
        self.calls.append(dict(tool=tool, args=args, t=t0, result=r))
        self.moves += 1
        self._seen = None
        if not r.get("ok"):
            raise RuntimeError(r.get("error"))
        return r

    def _skipped(self, tool: str, args: dict) -> dict:
        """A dropped call: nothing happens, the controller is handed the present state as if it had."""
        r = dict(self.w.call("observe"))
        r.update(reached=True, error_m=0.0, released=None)
        if "arm" in args:
            r["holding"] = self.w.holding[args["arm"]]
        return r

    def observe(self): return self._call("observe")
    def get_task(self): return self.w.call("get_task")
    def drive_to(self, x, y, heading): return self._call("drive_to", x=x, y=y, heading=heading)
    def move_arm(self, arm, x, y, z, yaw): return self._call("move_arm", arm=arm, x=x, y=y, z=z, yaw=yaw)
    def home_arm(self, arm): return self._call("home_arm", arm=arm)
    def grasp(self, arm): return self._call("grasp", arm=arm)
    def release(self, arm): return self._call("release", arm=arm)
    def look(self, pan, tilt): return self._call("look", pan=pan, tilt=tilt)
    def set_torso(self, height): return self._call("set_torso", height=height)
    def score(self): return self.w.score()


def run_episode(job: tuple) -> dict:
    seed, level, variant = job
    sim, policies, _ = T.import_sweep()
    t = time.time()
    world = sim.World(seed, level, privileged=True)
    rng = random.Random(zlib.crc32(f"{seed}/{level}/{variant}".encode()))
    rec = Recorder(world, variant, rng)
    error = None
    try:
        policies.reference_privileged(rec)
    except Exception as e:                      # a controller that gives up still gets scored
        error = repr(e)
    result = world.score()
    return dict(seed=seed, level=level, setting="privileged", policy="reference_privileged", variant=variant,
                score=result["score"], result=result, milestones=result["milestones"], n_calls=len(rec.calls),
                n_moves=rec.moves, stop_after=rec.stop_after, error=error, wall_s=round(time.time() - t, 1), calls=rec.calls)


def summarise(episodes: list[dict]) -> str:
    by = defaultdict(list)
    for e in episodes:
        by[e["variant"]].append(e)
    lines = [f"{'variant':12s} {'n':>4s} {'mean':>6s} {'=0':>4s} {'mid':>4s} {'>=.99':>5s} {'calls':>6s}  scores"]
    for v, es in sorted(by.items()):
        s = [e["score"] for e in es]
        shown = " ".join(f"{x:g}" for x in s[:14]) + (" ..." if len(s) > 14 else "")
        lines.append(f"{v:12s} {len(s):4d} {sum(s) / len(s):6.3f} {sum(x == 0 for x in s):4d} {sum(0 < x < 0.99 for x in s):4d} "
                     f"{sum(x >= 0.99 for x in s):5d} {sum(e['n_calls'] for e in es) / len(es):6.1f}  {shown}")
    s = [e["score"] for e in episodes]
    lines.append(f"{'all':12s} {len(s):4d} {sum(s) / len(s):6.3f} {sum(x == 0 for x in s):4d} {sum(0 < x < 0.99 for x in s):4d} "
                 f"{sum(x >= 0.99 for x in s):5d} {sum(e['n_calls'] for e in episodes) / len(episodes):6.1f}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="1000-1479", help="e.g. 1000-1479 or 1,2,5-8 (training seeds: keep them away from the evaluation seeds)")
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--variants", default=DEFAULT_VARIANTS, help="comma-separated; episode i gets variant i mod n")
    ap.add_argument("--out", default=str(T.HERE / "data" / "episodes_l1.jsonl"))
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    a = ap.parse_args()

    os.environ.setdefault("MUJOCO_GL", "egl")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    seeds = T.parse_seeds(a.seeds)
    variants = [v for v in a.variants.split(",") if v]
    jobs = [(s, a.level, variants[i % len(variants)]) for i, s in enumerate(seeds)]
    t = time.time()
    if a.workers > 1 and len(jobs) > 1:
        import multiprocessing as mp
        with mp.get_context("spawn").Pool(min(a.workers, len(jobs))) as pool:
            episodes = []
            for i, e in enumerate(pool.imap_unordered(run_episode, jobs), 1):
                episodes.append(e)
                if i % 20 == 0 or i == len(jobs):
                    print(f"  {i}/{len(jobs)} episodes, {time.time() - t:.0f} s", flush=True)
    else:
        episodes = [run_episode(j) for j in jobs]
    order = {j: i for i, j in enumerate(jobs)}
    episodes.sort(key=lambda e: order[(e["seed"], e["level"], e["variant"])])
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for e in episodes:
            f.write(json.dumps(e, separators=(",", ":")) + "\n")
    print(summarise(episodes))
    print(f"wrote {len(episodes)} episodes to {out} ({out.stat().st_size / 1e6:.1f} MB) in {time.time() - t:.0f} s; "
          f"seeds {a.seeds}, level {a.level}, variants {a.variants}")


if __name__ == "__main__":
    main()
