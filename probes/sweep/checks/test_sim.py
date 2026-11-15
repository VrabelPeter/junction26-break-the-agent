"""Checks that run in-process, no Docker:  MUJOCO_GL=egl python -m pytest probes/sweep/checks -q"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "environment" / "env-server"))
from sweep import policies as P  # noqa: E402
from sweep.sim import World  # noqa: E402


def test_pixel_point_finds_a_known_object():
    w = World(1, 1, privileged=True)
    w.drive_to(0.3, -1.6, np.pi / 2)
    w.look(0.0, -0.8)
    name = next(iter(w.items))
    p = w._pos(name)
    cal = w.camera("head", 640, 480, depth=False)["calibration"]
    loc = np.array(cal["cam_rot"]).T @ (p - np.array(cal["cam_pos"]))
    u = cal["cx"] + cal["f"] * loc[0] / -loc[2]
    v = cal["cy"] - cal["f"] * loc[1] / -loc[2]
    got = w.pixel_point("head", u, v)
    assert np.linalg.norm(np.array([got["x"], got["y"], got["z"]]) - p) < 0.03       # the object's surface, a little in front of its centre


def test_errors_come_back_as_data():
    w = World(1, 1)
    assert w.call("move_arm", arm="middle", x=0.0, y=0.0, z=0.5, yaw=0.0)["ok"] is False
    assert w.call("drive_to", x=float("nan"), y=0.0, heading=0.0)["ok"] is False
    assert w.call("fly")["ok"] is False
    assert "objects" not in w.call("observe")                                        # standard setting: no object positions
    w.score()
    assert w.call("drive_to", x=0.0, y=0.0, heading=0.0) == dict(ok=False, error="the episode is over", time_left_s=900.0)
    assert w.call("observe")["ok"] is False


def test_baselines_and_reference():
    assert P.do_nothing(World(1, 1, privileged=True))["score"] == 0.0
    assert P.stop_early(World(1, 1, privileged=True))["score"] == 0.0
    r = P.reference_privileged(World(1, 1, privileged=True))
    assert r["score"] == 1.0 and r["milestones"]["first_trash_in_bin"] > 0
