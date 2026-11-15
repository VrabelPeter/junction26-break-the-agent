"""Repeat a logged episode in-process and score it: the simulator is deterministic, so the commands are the recording.

    python probes/sweep/viewer/replay_log.py <trial dir or commands.json> [--until N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "environment" / "env-server"))
from sweep.sim import World  # noqa: E402

MOVING = ("drive_to", "move_arm", "home_arm", "grasp", "release", "look", "set_torso")


def load(path: str) -> dict:
    p = Path(path)
    if p.is_dir():
        p = next(p.rglob("commands.json"))
    d = json.loads(p.read_text())
    return d if isinstance(d, dict) else dict(calls=d, seed=1, level=1, setting="standard")


def replay(log: dict, until: int | None = None, on_step=None) -> World:
    w = World(int(log["seed"]), int(log["level"]), privileged=(log["setting"] == "privileged"))
    for i, c in enumerate(log["calls"]):
        if until is not None and i >= until:
            break
        if c["tool"] in MOVING:
            r = w.call(c["tool"], **c["args"])
            if on_step:
                on_step(i, c, r, w)
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--until", type=int)
    a = ap.parse_args()
    log = load(a.path)
    w = replay(log, a.until)
    r = w.score()
    print(json.dumps({k: r[k] for k in ("score", "trash_in_bin", "trash_total", "mistakes", "fate", "milestones", "robot_time_s")}))


if __name__ == "__main__":
    main()
