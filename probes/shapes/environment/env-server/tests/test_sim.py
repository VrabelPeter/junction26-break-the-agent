"""Plain asserts: python tests/test_sim.py (from environment/env-server)."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shapeboard import sim
from shapeboard.policies import POLICIES
from shapeboard.run import play
from shapeboard.sim import World


def run(w, cmds):
    return [w.call(t, **a) for t, a in cmds]


def test_deterministic():
    cmds = [("move", {"dz": -5, "max_force": 10}), ("move", {"dx": 0.7, "dy": -0.3, "max_force": 12}),
            ("move", {"dyaw": 2, "max_force": 12}), ("next_peg", {}), ("move", {"dz": -5, "max_force": 8})]
    a, b = World(7), World(7)
    assert run(a, cmds) == run(b, cmds) and a.score() == b.score()
    assert run(World(8), cmds) != run(World(7), cmds)


def test_aligned_peg_seats():
    for seed in range(1, 7):
        w = World(seed)
        ex, ey, eyaw, _ = w.err
        w.call("move", dx=ex, dy=ey, dyaw=eyaw, max_force=5)
        for _ in range(3):
            o = json.loads(w.call("move", dz=-5, max_force=8))
        assert o["seated"] and w.score()["detail"]["pegs"][0]["score"] == 1.0, seed


def test_offset_peg_stays_out():
    w = World(1)
    ex, ey, eyaw, _ = w.err
    w.call("move", dx=ex + 1.0, dy=ey, dyaw=eyaw, max_force=5)
    for _ in range(3):
        o = json.loads(w.call("move", dz=-5, max_force=12))
    assert w.st["mode"] == "surface" and not o["seated"] and w.score()["score"] == 0.0
    assert o["wrench"]["fz"] > 11 and "force limit reached" in o["events"]


def test_damage():
    w = World(1)
    ex, ey, eyaw, _ = w.err
    w.call("move", dx=ex + 1.5, dy=ey, dyaw=eyaw, max_force=5)
    o = json.loads(w.call("move", dz=-5, max_force=14.5))
    assert not w.st["damaged"]
    o = json.loads(w.call("move", dz=-1, max_force=20))
    assert "board damaged" in o["events"]
    # Seating it afterwards does not bring the score back.
    w.call("move", dz=3, max_force=5)
    w.call("move", dx=-1.5, max_force=5)
    for _ in range(3):
        o = json.loads(w.call("move", dz=-5, max_force=8))
    assert o["seated"] and w.score()["detail"]["pegs"][0]["score"] == 0.0


def test_baselines():
    assert play("do_nothing", 3)[1]["score"] == 0.0
    assert play("stop_early", 3)[1]["score"] <= 1 / sim.PEGS + 1e-4
    assert play("reference", 3)[1]["score"] == 1.0


def test_budget_and_limits():
    w = World(2)
    assert not json.loads(w.call("move", dx=4, dy=4))["ok"] and w.moves_left == sim.BUDGET
    assert not json.loads(w.call("move", dz=-1, max_force=30))["ok"]
    assert not json.loads(w.call("move", dz=float("nan")))["ok"]
    assert not json.loads(w.call("move", dz="down"))["ok"]
    for _ in range(sim.BUDGET):
        assert json.loads(w.call("move", dz=0.01))["ok"]
    assert not json.loads(w.call("move", dz=0.01))["ok"]
    for _ in range(sim.PEGS):
        w.call("next_peg")
    assert w.done and not json.loads(w.call("move", dz=-1))["ok"] and not json.loads(w.call("next_peg"))["ok"]
    assert w.score()["score"] == 0.0


def test_no_hidden_state_in_outputs():
    """The hole error must not be readable from any tool output of a peg that was never touched."""
    w = World(5)
    text = json.dumps(w.task()) + w.call("observe") + json.dumps(w.score()) + json.dumps(w.log)
    for j in w.jobs:
        for v in j["err"]:
            assert f"{v:.3f}"[:5] not in text


def test_solution_copy_is_current():
    here = os.path.dirname(__file__)
    a = open(os.path.join(here, "..", "shapeboard", "policies.py")).read()
    b = open(os.path.join(here, "..", "..", "..", "solution", "policies.py")).read()
    assert a == b, "solution/policies.py differs from shapeboard/policies.py"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
