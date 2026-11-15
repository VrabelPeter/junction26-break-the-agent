---
title: Sweep, first full runs with depth: Nemotron 3.5 Super VL, standard and privileged, level 1 seed 1
status: done
kind: probe
owner: peter
host: peter-LENOVO
started:
finished: 2026-11-14T17:40+02:00
commit: 121b6a4
command:
headline: Nemotron 3.5 Super VL, level 1 seed 1: 0.0 with cameras and 0.0 when told where everything is (375 calls, never took the brush); our arm action is partly at fault
---

## Hypothesis

Hypothesis: with colour, depth and joint readings (standard) the model does worse than when it is also given object positions (privileged); either way this is the first full run in the final setting and tells us whether level 1 is a usable headline level.

## Setup

Branch sweep-env at 121b6a4 (smoke test passed on this build at 17:08: do-nothing 0, interface check, scripted reference 1.0, Nemotron received the picture and acted). Started by Peter, per the rule that long runs are started by a person:

    cd .claude/worktrees/sweep-env        # or a checkout of branch sweep-env at 121b6a4
    python3 probes/sweep/run_agent.py --model nemotron
    python3 probes/sweep/run_agent.py --model nemotron --setting privileged

Model: verda-nemotron/nemotron-3.5-super-vl through OpenCode, key VERDA_INFERENCE_KEY. Level 1, seed 1, local Docker. Note: the reference-controller branch (sweep-ref) is not merged yet and changes the brush and arm physics, so these two runs are for orientation; the evaluation proper is rerun on the frozen build.

## Results

Written up by a later session from the run summaries (`results/sweep/agent-runs/` on branch `sweep-env`).

| Run | Setting | Score | Milestones reached | Tool calls | Robot time | Wall time | Input tokens |
|---|---|---|---|---|---|---|---|
| nemotron-standard-l1-s1-1701 (earlier build, sweep-depth worktree) | cameras with depth | 0.0, bin tipped over | bin in hand at 102 s | 169 | 117 s | 20.5 min | 22.8M |
| nemotron-standard-l1-s1-1710 (121b6a4) | cameras with depth | 0.0 | none | 268 | 305 s | 12.4 min | 17.0M |
| nemotron-privileged-l1-s1-1710 (121b6a4) | object positions given | 0.0 | bin in hand at 103 s | 375 | 331 s | 28.3 min | 123.4M |

Reference on the same room: 1.0 (scripted, from the cameras). Do-nothing and stop-early: 0.0.

## Takeaways

- The hypothesis (worse with cameras than with positions) is not testable from these runs: both settings score 0.0 and fail before any sweeping starts, at picking up the tools.
- A model that is told where the brush handle is and still cannot take it in 375 calls points at the arm action, not at seeing. Measured afterwards (task `sweep-task-fix-the-arm-action-wrong-documented-r`): only about half of the arm targets inside the documented reach arrive. So these three runs are **not results about the model**; they are rerun after the fix on a frozen build.
- Token use was out of proportion (123M input tokens in one run) because OpenCode resent the whole history every step; a 96k context limit is declared since e4114d3 so that it summarises.
