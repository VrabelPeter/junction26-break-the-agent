---
title: We commit to the living-room sweep as the submission environment
status: accepted
by: peter
date: 2026-11-14T17:54+02:00
---

## Context

Decided by Peter, 14 Nov 17:50, 16 hours before the deadline. From now on all work goes into the living-room sweep (`probes/sweep`, branch `sweep-env`). No further environment candidates.

## Why this one

- It is the only candidate where the reference does the task and the models do not: the scripted reference, working from the same camera pictures and tools as the agent, scores 1.0 on 10 of 10 rooms at level 1 in-process; Kimi K3.1 Pro and Nemotron 3.5 Super VL score 0.0 in every full run so far (6 runs, level 1, seed 1).
- The earlier candidates (satellite operations, kitchen tabletop, Ethernet insertion) gave the agent exact numbers and showed no gap.
- Baselines hold: do-nothing 0.0 and fetch-the-tools-then-stop 0.0 under Harbor.

## What is not established yet (honest state)

- **The gap is not proven fair yet.** Nemotron scored 0.0 even in the privileged setting (told where every object is): 375 tool calls and it never got the brush. Either the action tools are too hard to use for reasons that are ours, or handling is the real difficulty. Task `sweep-fix-the-action-interface...` settles this before any further paid run.
- No model has three runs on one frozen build. All runs so far are single runs on builds that changed afterwards.
- The camera reference is weaker above level 1: in-process, 10 seeds, level 2 scores 0.80 on average (3 of 4 pieces in most rooms, no mistakes); level 3 not measured yet. Under Harbor only level 1, seed 1 is measured (1.0).
- Reward red-team of this task, failure analysis, README text, demo video: not started.

## What follows

1. Fix the arm action (task `sweep-task-fix-the-arm-action-wrong-documented-r`), smoke test, freeze the build with a tag (task `sweep-freeze-the-build-...`).
2. On the frozen build: three seeds per model in the standard setting plus the privileged ablation. Frederik runs Kimi, Peter runs Nemotron (or any split: `python3 probes/sweep/run_agent.py --model <name>`; models are entries in `probes/sweep/models.json`).
3. Results table (`python3 probes/sweep/report.py`), replays on the board, failure analysis.
4. Post-training on Modal: does a small model improve when trained on experience selected by this reward (task `stretch-train-small-model`).

Fallback if the fixed interface closes the gap at level 1: the headline level moves to 2 or 3 (more trash, personal items in the way), where the reference still scores 0.92 and 0.84 in-process with object positions given.

## Decision

## Consequences
