---
title: Shape board under Harbor: reference, do-nothing, stop-early (no model)
status: done
kind: eval
owner: frederik
host: fls
started: 2026-11-14T11:51+01:00
finished: 2026-11-14T11:53+01:00
commit: 65579fd
command:
headline: Shape board under Harbor: reference 1.0 x3, do-nothing 0.0, stop-early 0.167; no model run yet
reference: 1.0
agent: []
noop: 0.0
stop_early: 0.167
---

## Hypothesis

First run of probes/shapes through the standard harness on local Docker, seeds 1 2 4. Expect what the in-process runner gives: reference 1.0, do-nothing 0.0, stop-early 0.167. Command: python3 eval/run_eval.py --task probes/shapes --skip-agent

## Setup

Host: Frederik's machine, local Docker, code at commit 9f0fc37 (probes/shapes). Seeds 1, 2, 4. No model involved.

    python3 eval/run_eval.py --task probes/shapes --skip-agent --out runs/shapes

In-process check of the same policies on more seeds (no Docker):

    cd probes/shapes/environment/env-server && python -m shapeboard.run --seeds $(seq 1 60)

## Results

Under Harbor (results/eval-1114-1151.json):

| Run | Seed 1 | Seed 2 | Seed 4 | Mean |
|---|---|---|---|---|
| reference (oracle) | 1.000 | 1.000 | 1.000 | 1.000 |
| do-nothing (nop) | 0.000 | 0.000 | 0.000 | 0.000 |
| stop-early | 0.167 | 0.167 | 0.167 | 0.167 |

In-process, 60 seeds, 360 pegs, budget 24 moves per peg:

| Policy | Mean score | Pegs seated |
|---|---|---|
| do_nothing | 0.000 | 0 |
| stop_early | 0.167 | 60 |
| straight_down | 0.042 | 15 |
| blind_search | 0.378 | 136 |
| reference | 1.000 | 360 |

Reference: 7.7 moves per seated peg on average, 16 at most over seeds 101 to 200.

## Takeaways

- The task runs end to end through the standard harness and the Harbor scores match the in-process runner.
- Do-nothing is 0 and stop-early is exactly one peg in six.
- A controller that ignores the force readings (blind spiral) reaches 0.38; trusting the camera reaches 0.04. So the force readings are what the task is about.
- **Not measured: any model.** No model key on this machine yet. Whether a strong model falls short of the reference is the open question, as for probes/insertion.
- The reward has not been red-teamed.
