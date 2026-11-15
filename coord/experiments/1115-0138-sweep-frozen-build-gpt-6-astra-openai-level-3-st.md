---
title: Sweep, frozen build: GPT-6 Astra (OpenAI), level 3, standard, seed 1
status: failed
kind: probe
owner: frederik
host: fls
started: 2026-11-15T01:38+01:00
finished: 2026-11-15T01:40+01:00
commit: 3564f98 (task copy at sweep-frozen-1)
command: python3 runs/qwen-task/sweep/run_agent.py --model astra --level 3 --seeds 1 --tag frozen1
headline: No result - GPT-6 Astra at level 3 made no call: OpenAI refused the first request (organization spend limit reached)
---

## Hypothesis

GPT-6 Astra scores below the reference at level 3, seed 1 (camera reference in-process: 0.375; told positions: 0.875).

## Setup

As 1115-0048, level 3, seed 1, one run.

    python3 runs/qwen-task/sweep/run_agent.py --model astra --level 3 --seeds 1 --tag frozen1

## Results

**Failed, no result.** The agent exited after 1.7 minutes with 0 calls: `Your organization has reached its configured enforced spend limit` (OpenAI). The verifier's 0.0 says nothing about the model. The summary is kept out of `results/sweep/agent-runs/` (it is in `runs/sweep/not-results/` on host fls).

## Takeaways

- Second level 3 attempt without a result (1114-2257 died for lack of credits). GPT-6 Astra has cost about 30 USD so far over 10 runs.
- Rerun the same command once the organization's spend limit at OpenAI is raised.
