---
title: Tabletop, Panda with long fingertips: full evaluation, level 2, Kimi
status: done
kind: eval
owner: peter
host: peter-LENOVO
started: 2026-11-14T06:18+02:00
finished: 2026-11-14T06:41+02:00
commit: bf9a12e
command: sg docker -c 'python3 eval/run_eval.py --seeds 1 2 4 --level 2'
headline: Panda with long fingertips, level 2: reference 1.0 x3; Kimi 0.5 / 1.0 / 1.0 (+3 more runs all 1.0); nop 0; stop-early 0.14. Gap in the mean only
reference: 1.0
agent: [0.5, 1.0, 1.0]
noop: 0.0
stop_early: 0.143
---

## Hypothesis

After the plain Panda hand showed no gap: fingertip extensions (fingers 10 cm long, the lowest 6 cm thin) and the rule that a can or bottle only holds when gripped at or below its centre. The fingers now have to go down between neighbouring objects, which is what produced slips with the earlier gantry gripper. One command, seeds 1 2 4, level 2: reference, do-nothing, stop-early and three agent runs (OpenCode + Kimi K3.1 Pro on Verda).

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

## Takeaways

## Setup

`probes/tabletop` at commit `1ab26df` (seeds 1, 2, 4) and `cbb39b8` (seeds 5, 6, 7; adds the basket's floor and wall thickness to the task text, and makes scoring terminal). Franka Panda with fingertip extensions: fingers 0.102 long, the lowest 0.06 only 0.012 thick; cans and bottles only hold when gripped at or below their centre. Level 2: five fruit into the basket in order, two drinks onto coasters. Score = progress x care (halved per damaged object). Local Docker, OpenCode + Kimi K3.1 Pro on Verda.

Command for the first table below: `sg docker -c "python3 eval/run_eval.py --seeds 1 2 4 --level 2"` (result file `results/eval-1114-0618.json`). Seeds 5 to 7 were single `harbor run` calls with `TABLETOP_SEED=<s> TABLETOP_LEVEL=2`.

## Results

| Run | Seed 1 | Seed 2 | Seed 4 | Mean |
|---|---|---|---|---|
| reference (`-a oracle`) | 1.000 | 1.000 | 1.000 | 1.000 |
| do-nothing (`-a nop`) | 0.000 | 0.000 | 0.000 | 0.000 |
| stop-early | 0.130 | 0.150 | 0.150 | 0.143 |
| **agent** | **0.500** | **1.000** | **1.000** | **0.833** |

Three more agent runs: seeds 5, 6, 7: 1.000, 1.000, 1.000. Six agent runs in all: five flawless, one at 0.5. Each run: 53 to 65 tool calls, about 5 minutes, about $0.40.

Reference in-process on 32 level-2 tables: mean 0.980, 30 flawless, no damage; the two imperfect ones are items it declined to pick (it never forces a move).

The one agent failure (seed 1), from its own reasoning and a replay:

1. It set the first fruit (peach) down 4 cm from the basket wall. With the fingers along x there was no room for them to open, so the peach stayed pinched 1 cm above the floor; `release` reported its height truthfully.
2. It read that height as "the basket floor must be at 0.015" and lowered the next fruit (orange) accordingly, pressing it into the real floor: crushed.

The task text did not state the basket's floor thickness at that point (it does now), so this failure is not fully clean: the agent had to infer the floor from the wall height and its own release report.

## Takeaways

- **There is a gap in the mean (1.00 against 0.83 on the evaluated seeds, 0.92 over all six runs) but it is not consistent**: in five of six runs the agent equals the reference.
- The agent's weakness is the same as in every probe: not planning, not geometry, but an occasional single slip that physics makes permanent. At about one slip per six tables, a single table cannot show it reliably.
- The lever that follows from this is episode length under the same scoring: a shift of several tables in one episode, with breakage halving the whole shift. It is implemented in the simulator (`tabletop/shift.py`, `python -m tabletop.run --tables 4 --level 2`) but not yet wired into the MCP server. With one slip per six tables, a four-table shift would be flawless about half the time and a six-table shift about a third; the reference stays near 0.98. This is an estimate from six runs, not a result.
- The honest alternative reading: this environment, as it stands, is within reach of a strong model, and what it measures is reliability over many manipulations.

