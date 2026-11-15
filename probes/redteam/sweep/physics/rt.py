"""Shared helpers for the physics red-team scripts. Nothing here touches probes/sweep.

Every script is run from the repo root:
    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/<script>.py --level 2 --seeds 1 2 3
"""
from __future__ import annotations

import argparse
import math
import os
import sys
from multiprocessing import Pool
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "probes" / "sweep" / "environment" / "env-server"))

from sweep import policies as P          # noqa: E402
from sweep import scene as S             # noqa: E402
from sweep.sim import World              # noqa: E402


class W:
    """The world as an agent has it: every move goes through World.call (the path the MCP tools use)."""

    def __init__(self, seed: int, level: int, privileged: bool = True):
        self.world = World(seed, level, privileged=privileged)
        self.calls = 0

    def __getattr__(self, tool):
        def f(*a, **kw):
            names = dict(drive_to=("x", "y", "heading"), move_arm=("arm", "x", "y", "z", "yaw"), can_reach=("arm", "x", "y", "z", "yaw"),
                         home_arm=("arm",), grasp=("arm",), release=("arm",), look=("pan", "tilt"), set_torso=("height",)).get(tool, ())
            kw.update(dict(zip(names, a)))
            self.calls += 1
            return self.world.call(tool, **kw)
        return f

    def score(self):
        return self.world.score()


def args(default_level=2, default_seeds=(1, 2, 3, 4, 5)):
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=default_level)
    ap.add_argument("--seeds", type=int, nargs="+", default=list(default_seeds))
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("-v", action="store_true")
    return ap


def pmap(fn, jobs, procs=8):
    with Pool(min(procs, 10, max(1, len(jobs)))) as pool:
        return pool.map(fn, jobs)


def short(r: dict) -> str:
    m = ",".join(f"{x['item']}:{x['why'].split()[-1]}" for x in r["mistakes"])
    return f"score {r['score']:.3f}  trash {r['trash_in_bin']}/{r['trash_total']}  mistakes[{m}]  t {r['robot_time_s']:.0f}s"


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")
