---
title: Training: Qwen3-4B text-only on reward-selected vs unselected episodes (privileged, level 1), arms A/B/C, eval seeds 1-10, on Frederik's Modal account for Peter
status: running
kind: training
owner: frederik
host: fls
started: 2026-11-15T04:48+01:00
finished:
commit: 779ca93
command:
headline:
---

## Hypothesis

Started by frederik on Peter's request (message 1115-0538). Design, data and code are Peter's: training/modal_app.py, training/README.md, task stretch-train-small-model. Setting: privileged, text only (positions given, no pictures), imitation with reward selection, level 1, evaluated in-process on held-out rooms 1-10. Arms: A untrained Qwen3-4B, B trained on 265 episodes selected by the reward (all 1.0), C trained on 265 episodes drawn without looking at the score (mean 0.61). Smoke run passed at 04:47 CET (path works end to end; A/B/C 0.0 on one seed after 6 steps, as expected for a tiny run). Command: gunzip -k training/data/train_B.jsonl.gz training/data/train_C.jsonl.gz ; .venv/bin/modal run --detach training/modal_app.py --eval-seeds 1-10 --run frederik-4b-abc-1115 . One L40S per function. Result file: results/training/frederik-4b-abc-1115.json (written as it goes). To be stopped at about 09:15 CET if not finished.

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

## Takeaways
