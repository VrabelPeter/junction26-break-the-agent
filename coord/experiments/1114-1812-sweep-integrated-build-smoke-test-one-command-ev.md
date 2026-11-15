---
title: Sweep, integrated build: smoke test, one-command eval without a model, camera reference per level
status: done
kind: eval
owner: peter
host: peter-LENOVO
started: 2026-11-14T17:54+02:00
finished: 2026-11-14T18:10+02:00
commit: 6d48f5a
command: python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1 2 3 --skip-agent
headline: Sweep under Harbor, level 1, seeds 1-3: reference (from the cameras) 1.0 / 1.0 / 1.0, do-nothing 0, stop-early 0; no agent runs on this build yet
reference: [1.0, 1.0, 1.0]
agent: []
noop: [0.0, 0.0, 0.0]
stop_early: [0.0, 0.0, 0.0]
---

## Hypothesis

On the integrated branch the task still builds and grades, baselines score 0, the camera reference scores 1.0 at level 1 under Harbor, and both models receive pictures and act.

## Setup

Branch `sweep-env`, local Docker, Harbor 0.26.0. Level 1. No model runs here except the two short smoke runs.

    python3 probes/sweep/smoke.py                                    # free checks, commit dbb39c1
    python3 probes/sweep/smoke.py --model kimi nemotron --skip-free   # two short model runs, commit dbb39c1
    python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1 2 3 --skip-agent      # commit 6d48f5a
    cd probes/sweep/environment/env-server && MUJOCO_GL=egl python -m sweep.run --policy reference --seeds 1 2 3 4 5 6 7 8 9 11 --level N   # N = 1, 2, 3; needs mujoco==4.0.1

## Results

| Check | Result |
|---|---|
| Smoke: harness and do-nothing | 0.0 |
| Smoke: interface from inside the agent container | head camera gives colour, depth and calibration; depth file downloads; room cameras 404; no object positions; no pixel-to-position tool |
| Smoke: scripted reference, standard setting | 1.0 |
| Smoke: Kimi K3.1 Pro | received the picture, downloaded the depth, drove (5 calls, 72 s) |
| Smoke: Nemotron 3.5 Super VL | the same (5 calls, 53 s) |
| One-command eval, seeds 1 / 2 / 3: reference | 1.0 / 1.0 / 1.0 |
| One-command eval: do-nothing | 0.0 / 0.0 / 0.0 |
| One-command eval: stop-early (fetch the tools, stop) | 0.0 / 0.0 / 0.0 |

Camera reference in-process, 10 seeds per level: level 1 mean 1.00 (10 of 10 rooms); level 2 mean 0.80 (0.75 in 8 rooms, 1.0 in 2); level 3 mean 0.51 (0.25 to 0.625). No mistakes at any level. Summary file: `results/eval-1114-1803.json` on the branch.

## Takeaways

- The integrated build is sound for the baselines and the reference at level 1. The one-command evaluation works on the sweep.
- The reference from the cameras is much weaker at level 3 (0.51) than the position-fed one was (0.84): if the headline level moves above 1, the reference needs work first.
- Not covered: any full agent run on this build, and the arm fix is not in yet, so this is not the frozen build.
