---
title: Environment: living-room sweep from the robot's cameras; tabletop and Ethernet insertion dropped
status: proposed
by: peter
date: 2026-11-14T15:26+02:00
---

## Context

Decided by Peter, 14 Nov about 15:05.

**What:** the environment we build towards the submission is the living-room sweep (probes/sweep, branch sweep-env): a wheeled two-arm robot gets the trash, and only the trash, into a bin, working from camera images and its own joint readings. Score = trash in the bin / all trash x 0.5 ^ mistakes, from the final physical state; milestones are logged and never paid. A privileged setting with object positions exists for ablation. The kitchen-tabletop and Ethernet-insertion tasks are removed from the repo.

**Why:** four probes that gave the agent exact numbers showed no consistent gap (experiments 1114-0346, 1114-0618, 1114-1240): a strong model reasons its way to the reference's strategy. The Embodied First Exam reports the same split on 391 tasks (77% with simulator state, 30% from cameras for the best agent; 9% for Kimi 3.1 Pro), and its closest task, sweeping a garage with a broom, is unsolved from cameras by all nine agents.

**Not yet known:** whether Kimi falls short in our room. First runs: experiment 1114-1500. If it does not, this decision is reopened.

**Unaffected:** Frederik's shape board (probes/shapes) continues in parallel.

## Decision

## Consequences
