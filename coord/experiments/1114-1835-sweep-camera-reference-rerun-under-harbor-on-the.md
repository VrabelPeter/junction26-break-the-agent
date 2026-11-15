---
title: Sweep: camera reference rerun under Harbor on the frozen build, level 1 seed 1
status: done
kind: eval
owner: frederik
host: fls
started: 2026-11-14T18:35+01:00
finished: 2026-11-14T18:38+01:00
commit: 27af146
command: SWEEP_SEED=1 SWEEP_LEVEL=1 SWEEP_SETTING=standard .venv/bin/harbor run -p probes/sweep -a oracle -o runs/sweep/reference-l1-s1-rerun
headline: Camera reference under Harbor on the frozen build, level 1 seed 1: 1.0 (1 of 1 trash in the bin, no mistakes, 100.7 s robot time)
reference: 1.0
agent: []
noop:
stop_early:
---

## Hypothesis

The scripted reference working from the head camera (standard setting, `SWEEP_POLICY=reference`, the oracle default) still scores 1.0 at level 1 seed 1 under Harbor on the frozen build, after the arm fix.

## Setup

Commit 27af146 on main; `probes/sweep` and `eval/` are identical to tag `sweep-frozen-1` (git diff is empty). Local Docker, Harbor 0.26.0, one trial, no model involved.

    SWEEP_SEED=1 SWEEP_LEVEL=1 SWEEP_SETTING=standard .venv/bin/harbor run -p probes/sweep -a oracle -o runs/sweep/reference-l1-s1-rerun

## Results

Reward 1.0 (verifier's reward.txt). 1 of 1 piece of trash in the bin (apple core), no mistakes, setting standard, 100.7 s of robot time, 2 min 9 s wall time. Milestones: brush in hand 57.8 s, bin in hand 61.2 s, trash in bin 96.3 s.

Scorer details and the logged tool calls: `results/sweep/reference-cameras-l1-s1-harbor-1114-1835.{details,commands}.json`. The full trial is in `runs/sweep/reference-l1-s1-rerun/` on frederik's machine (not committed).

An in-process run of the same policy, seed and level on the same commit gave 1.0 with 100.8 s of robot time.

## Takeaways

- The camera reference reproduces at level 1 under Harbor on a second machine (frederik's), on the frozen build.
- Only one seed and only level 1 were run here. Levels 2 and 3 have no Harbor run of the camera reference yet.
