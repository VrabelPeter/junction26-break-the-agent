---
title: Sweep reference: camera pipeline accuracy against ground truth (seeds 1 to 40, levels 1 to 3)
status: done
kind: probe
owner: peter
host:
started:
finished: 2026-11-14T17:05+02:00
commit:
command:
headline: Camera pipeline (colour + depth): every item found in 117 test rooms, mean position error 1.7 mm, trash vs personal right 100%; survey needs empty hands
---

## Hypothesis

Hypothesis: a scripted pipeline that sees only what the agent sees in the standard setting (head camera colour + depth + calibration, joint readings, floor plan) can find the things on table and sofa and tell trash from personal items well enough for the reference controller (the brush tolerates about 5 cm sideways).

## Setup

Branch sweep-perc (merged into sweep-env at 121b6a4), probes/sweep/environment/env-server/sweep/perception.py. Classifier examples built from rooms with seeds 1000 and up; evaluation on seeds 1 to 40 per level (level 3: seeds 10, 27 and 34 cannot be generated, 37 rooms). Ground truth is read only in perception_eval.py.

    cd probes/sweep/environment/env-server
    MUJOCO_GL=egl PYTHONPATH=. python -m sweep.perception_eval --eval [--colour-only]
    MUJOCO_GL=egl PYTHONPATH=. python -m sweep.perception_eval --tools [--colour-only]

## Results

| | Colour and depth | Colour only |
|---|---|---|
| Level 1: found, median / 95th-percentile position error | 40 of 40, 0.9 / 2.4 mm | 40 of 40, 2.2 / 6.7 mm |
| Level 2 | 239 of 239, 0.6 / 4.8 mm | 239 of 239, 2.3 / 13.5 mm |
| Level 3 (37 rooms) | 481 of 481, 1.1 / 5.6 mm | 478 of 481, 3.4 / 31 mm |
| Mean error, all | 1.7 mm | 7.5 mm |
| Within the brush's 5 cm | 99.9% | 98.3% |
| False detections per room | 0.01 | 0.36 |
| Trash or personal judged right | 100% | 99.7% |
| Pictures per survey, robot time | 5.5, 47 s | 12, 84 s |

Tool handles at the station (depth mode): found in 27 of 27 cases, error 6 to 7 mm, worst 16 mm.

## Takeaways

- With colour and depth the reference can see as well as it needs to. The information to do the task from the cameras is there.
- Limit: the survey has to be done with empty hands; with brush and bin held, no viewpoint in this room keeps the tools out of the furniture.
- About 4% of the sofa seat at level 3 is hidden behind things that stand up.
- Scene issues found: level 3 cannot be generated for seeds 10, 27, 34 (no room on the table); the jacket's spacing radius is smaller than the jacket.

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

## Takeaways
