---
title: Sweep, frozen build: Nemotron 3.5 Super VL rerun, level 1, rooms 1 2 3 standard and room 1 privileged (complete runs)
status: done
kind: eval
owner: peter
host:
started:
finished: 2026-11-14T22:18+02:00
commit:
command:
headline: Nemotron 3.5 Super VL, complete runs on the frozen build, level 1: 0.0 in rooms 1, 2, 3 from the cameras (reference 1.0) and 0.0 told positions; 152 of 154 grasps closed 9 cm or more from a handle
reference:
agent: []
noop:
stop_early:
---

## Hypothesis

Hypothesis: with complete runs (the first three were cut off by a network failure, experiment 1114-1938) Nemotron 3.5 Super VL still scores well below the camera reference (1.0) at level 1; and told the positions it does better than from the cameras.

## Setup

Started by Peter, task files identical to tag `sweep-frozen-1` (checked with `git diff sweep-frozen-1 <commit> -- probes/sweep/{instruction.md,task.toml,environment,tests,solution}`). Registered after the fact by the session that read the results.

    python3 probes/sweep/run_agent.py --model nemotron --setting privileged --tag frozen1                 # 20:13, commit 7eda2eb
    python3 probes/sweep/run_agent.py --model nemotron --seeds 1 2 3 --parallel 3 --tag frozen1           # 20:50, commit ada6c66

Model: verda-nemotron/nemotron-3.5-super-vl through OpenCode, key VERDA_INFERENCE_KEY, level 1, local Docker. Summaries, scorer details and logged calls: `results/sweep/agent-runs/peter-nemotron-*-1114-2013-frozen1.*` and `*-1114-2050-frozen1.*`.

## Results

| Run | Setting | Room | Score | Trash in bin | Mistakes | Tools taken (robot time) | Tool calls | Robot time | Wall time | Input tokens | How it ended |
|---|---|---|---|---|---|---|---|---|---|---|---|
| peter-nemotron-standard-l1-s1-1114-2050-frozen1 | standard | 1 | 0.0 | 0 of 1 | bin tipped over | brush at 288 s, let go 1 s later | 1071 | 902 s | 20.3 min | 9.2M | robot time used up, model stopped |
| peter-nemotron-standard-l1-s2-1114-2050-frozen1 | standard | 2 | 0.0 | 0 of 1 | none | bin at 228 s, tipped while driving at 260 s, let go | 389 | 328 s | 24.6 min | 17.4M | model stopped by itself |
| peter-nemotron-standard-l1-s3-1114-2050-frozen1 | standard | 3 | 0.0 | 0 of 1 | none | none | 1015 | 899 s | 52.3 min | 48.8M | robot time used up, model stopped |
| peter-nemotron-privileged-l1-s1-1114-2013-frozen1 | privileged | 1 | 0.0 | 0 of 1 | bin tipped over | bin at 579 s (dropped) and 626 s, brush at 843 s | 883 | 898 s | 37.5 min | 30.9M | robot time used up, model stopped |

Reference on the same level: 1.0 under Harbor in room 1 (experiment 1114-1835), 1.0 in-process in rooms 1, 2 and 3. Do-nothing and stop-early: 0.0. Kimi K3.1 Pro in the privileged setting, room 1: 1.0 (experiment 1114-1933).

All four are complete runs: every OpenCode session ended with the model's own final message (finish reason `stop`), no network or server error in the logs. Room 1 standard: Harbor recorded `NonZeroAgentExitCodeError` because OpenCode exited with code 1 after that final message; nothing was cut off, the summary carries a `note` and `error: null`. `run_agent.py` now only reports a cut-off when the session did not end with the model's last word or an error is logged.

Replaying each run's logged calls in a fresh copy of the simulator gives the same score and the same mistakes as the run.

Measured in those replays (a grasp counts when the hand was empty; distance is hand to the nearest free handle at the moment of the grasp):

| Run | Grasps | Took a tool | Failed grasps: hand to handle, min / median / max | `move_arm`: all / refused as out of reach / stopped against something |
|---|---|---|---|---|
| standard, room 1 | 19 | 1 | 35 / 114 / 139 cm | 100 / 19 / 74 |
| standard, room 2 | 25 | 1 | 10 / 42 / 62 cm | 60 / 14 / 22 |
| standard, room 3 | 110 | 0 | 9 / 39 / 128 cm | 301 / 39 / 98 |
| privileged, room 1 | 53 | 3 | 3 / 7 / 216 cm | 186 / 54 / 71 |

## Takeaways

- **Standard setting, level 1: 0.0 in three of three rooms with complete runs, against a reference of 1.0.** The piece of trash never left the table. The hypothesis holds for the gap.
- **From the cameras the model cannot place its hand on a handle.** 154 grasps in three runs, 2 took a tool; the other 152 closed at least 9 cm from the nearest handle, typically 40 cm or more. No failed grasp in the standard runs was within the 3.5 cm the grasp needs, so no sign of a fault in `grasp`.
- **Told the positions it gets much closer and is still far too slow.** In the privileged run the typical failed grasp was 7 cm from the handle instead of 40 cm or more, and it did take both tools, but only after 626 s and 843 s of 900 s, with the bin knocked over three times on the way. One failed grasp there was within 3.5 cm of a handle (3 cm): not yet looked at whether the fingers were along the handle or the palm not level.
- **So for this model it is both: seeing and handling.** Kimi K3.1 Pro with the same tools and the same information scores 1.0 in the privileged setting, which is the evidence that the handling is doable through our interface. The second hypothesis (better when told positions) holds for the process, not for the score.
- A large share of arm moves stopped against something (22 to 74 per run): the model sends the hand sideways or low into the shelf, the brush or the bin instead of coming from above. The bin was knocked over in three of four runs, by the base or an arm, while no hand held it or while driving with it.
- When a tool was finally in a hand it was lost again: room 1 let go of the brush after one second; room 2 tipped the bin while driving with it and released it.
- Cost of a complete run: 20 to 52 minutes and 9 to 49M input tokens.
- Films and step-by-step replays of all four runs: `visuals/sweep/compare.html` on the board.
