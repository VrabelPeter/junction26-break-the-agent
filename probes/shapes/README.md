# Shape board (insertion probe)

A robot arm pushes six shaped pegs (star, rectangle, triangle, square, cross,
hexagon) into their matching holes. The camera's idea of each hole is off by up
to 2 mm, 4 degrees and 0.5 mm in height; the peg fits with 0.2 mm to spare; the
arm has 24 moves per peg. So the hole has to be found by what the wrist feels.
What the agent is told: `instruction.md`.

Status: a probe. Reference and baselines are measured; **no model has played it
yet**, so whether it produces a gap is unknown.

It is a sibling of `probes/insertion` (RJ45 plug, MuJoCo contact physics) with
the same idea and the same kind of tools. The difference: the contact model here
is quasi-static geometry, not a rigid-body engine (see below).

## Layout

```
task.toml, instruction.md          the Harbor task and what the agent is told
environment/env-server/            the simulator container
  shapeboard/sim.py                shapes, contact model, tools, scoring
  shapeboard/policies.py           scripted controllers (reference, blind_search, straight_down, stop_early, do_nothing)
  shapeboard/run.py                in-process runner
  server.py                        MCP front end (get_task, observe, move, next_peg)
  tests/test_sim.py                plain asserts
solution/                          the reference run through MCP (policies.py is a copy; a test checks it)
tests/test.sh                      hardened grader, same as probes/tabletop
viewer/replay.py                   replay page
```

## Run it

In-process, no Docker, no model (needs numpy):

```bash
cd probes/shapes/environment/env-server
python -m shapeboard.run --seeds 1 2 4 -v
python tests/test_sim.py
```

Under Harbor (the eval script sets the seed; `--skip-agent` needs no model key):

```bash
python3 eval/run_eval.py --task probes/shapes --skip-agent --out runs/shapes
python3 eval/run_eval.py --task probes/shapes --out runs/shapes
```

The seed is `SHAPES_SEED` (the compose file also accepts `TABLETOP_SEED`, and
`solve.sh` accepts `TABLETOP_POLICY`, so the shared eval script works unchanged).

## Watch it

```bash
python probes/shapes/viewer/replay.py --policy reference --seed 1 -o replay.html     # a scripted controller
python probes/shapes/viewer/replay.py runs/shapes/<job>/<trial> --seed 1 -o replay.html
```

One self-contained page: calls and readings on the left (with the agent's
reasoning if the trial has a trajectory), the true hole and peg on the right.
The page shows hidden state; it is for people.

## Numbers so far (in-process, 60 seeds, 360 pegs, budget 24)

| Policy | Mean score | Pegs seated |
|---|---|---|
| do_nothing | 0.000 | 0 |
| stop_early (first peg, then stops) | 0.167 | 60 |
| straight_down (trusts the camera) | 0.042 | 15 |
| blind_search (presses on a spiral, ignores the torque) | 0.378 | 136 |
| reference (force-guided) | 1.000 | 360 |

The reference needs 7.7 moves per peg on average, 16 at most (over 100 further
seeds), which is where the budget of 24 comes from: 1.5 times its worst case.

## The contact model, honestly

A peg is a polygon, its hole the same polygon grown by the clearance.

- **On the board**: the peg stands on the board when its outline overhangs the
  hole edge. The reported torque is the press force times the centre of the
  overhanging rim (weighted by overhang, capped at 1 mm).
- **Dropping in**: if no corner overhangs by more than the chamfer, the nearest
  fitting pose is computed exactly (a small quadratic program); the peg drops
  in if the wrist springs can be bent that far by 0.6 times the press force.
  Only at rest or while moving straight down.
- **In the hole**: the peg sits at the fitting pose nearest to where the arm
  wants it; the spring deflection is the side load, which adds friction.

What this is not: there is no tilting, no dynamics, no wedging at depth, and
the support model is a rule, not a pressure solution. It was chosen because
star and cross holes are non-convex and getting them stable in a rigid-body
engine at 0.2 mm clearance was not realistic in the time available. Everything
the agent needs to know about these rules is in `instruction.md`.

One thing the model produces that is worth knowing: for a star or a cross that
is turned as well as offset, the support centre does not point at the hole, and
"slide away from the supported side" circles the hole instead of reaching it.
The reference detects the circle and goes to its centre.
