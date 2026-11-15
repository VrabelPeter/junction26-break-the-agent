---
title: One-command eval end to end on main, level 1, room 1: reference, baselines and a Kimi agent run (standard), stopped by us once it was seen to work
status: done
kind: eval
owner: peter
host: peter-LENOVO
started: 2026-11-15T06:34+02:00
finished: 2026-11-15T06:40+02:00
commit: 4537c60
command: python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1
headline: One command end to end, level 1 room 1: reference (standard) 1.0, do-nothing 0.0, stop-early 0.0; Kimi (standard) received pictures and acted, stopped by us after 4 min, no score
reference: [1.0]
agent: []
noop: [0.0]
stop_early: [0.0]
---

## Hypothesis

The README's one command works end to end on the sweep task, including the agent run through `eval/run_eval.py`'s own model settings (so far only run with `--skip-agent`; model runs were started with `probes/sweep/run_agent.py`).

## Setup

Started by Peter on peter-LENOVO at 06:34, local Docker, `main` at 4537c60. Agent: OpenCode with Kimi K3.1 Pro on Verda (the default preset), standard setting, level 1, room (seed) 1.

    python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1

## Results

| Run | Setting | Room 1 |
|---|---|---|
| reference | standard | 1.0 |
| do nothing | - | 0.0 |
| fetch the tools then stop | - | 0.0 |
| Kimi K3.1 Pro | standard | no score: stopped by us after 4 minutes |

The Kimi run in its first 4 minutes (OpenCode's event log, read inside the agent container): 61 tool calls, among them 11 `camera` calls that all came back with the picture attached, 7 `look`, 9 `can_reach`, 9 `move_arm`, 7 `drive_to`, 2 `grasp`, 8 shell commands; no error event and no "cannot read image" reply. Interrupted with Ctrl-C on the `harbor run` process; the eval then finished, printed its table and wrote `results/eval-1115-0634.json` (agent score `null`, "harbor exit 130"). Both containers were removed.

## Takeaways

- The one command starts all four kinds of run on the current build, and the model gets pictures and acts through `run_eval.py`'s settings. It is a plumbing check, not a score for Kimi.
- A full Kimi run through the one command has still not been let run to its end (earlier Kimi runs did not end by themselves; the agent limit in `task.toml` is 60 minutes).
