---
title: Sweep on main 55c4fe5 under Harbor, level 1, rooms 1 2 3: reference (standard) and both baselines through the one command
status: done
kind: eval
owner: peter
host: peter-LENOVO
started: 2026-11-15T04:58+02:00
finished: 2026-11-15T05:15+02:00
commit: b8c54f8 or later on main (started by Peter at 04:58; task files unchanged since f580509)
command: python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1 2 3 --skip-agent
headline: Under Harbor on main, level 1, rooms 1 2 3 - reference (standard) 1.0 / 1.0 / 1.0, do nothing 0.0 x3, fetch the tools then stop 0.0 x3
reference: [1.0, 1.0, 1.0]
agent: []
noop: [0.0, 0.0, 0.0]
stop_early: [0.0, 0.0, 0.0]
---

## Hypothesis

Hypothesis: under Harbor on the current main the reference (standard) scores 1.0 and both baselines 0.0, as in-process (1115-0434).

## Setup

Started by Peter on peter-LENOVO, local Docker, Harbor with the `oracle` agent for the reference and scripted agents for the baselines, no model (`--skip-agent`). 9 runs.

    python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1 2 3 --skip-agent

## Results

| Run | Setting | Room 1 | Room 2 | Room 3 | Mean |
|---|---|---|---|---|---|
| reference | standard | 1.0 | 1.0 | 1.0 | 1.000 |
| do nothing | any | 0.0 | 0.0 | 0.0 | 0.000 |
| fetch the tools then stop | any | 0.0 | 0.0 | 0.0 | 0.000 |

File: `results/eval-1115-0458.json`. Trial folders under `runs/eval` on peter-LENOVO.

## Takeaways

- The one command works on the current `main` and reproduces the in-process level 1 numbers of 1115-0434 under Harbor, after the scorer, verifier and server changes of the night.
- Agent runs were skipped; level 1 only.
