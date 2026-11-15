---
title: Sweep, frozen build: GPT-6 Astra (OpenAI), levels 2 and 3, standard, seed 1 (one run each)
status: failed
kind: probe
owner: frederik
host: fls
started: 2026-11-14T22:57+01:00
finished: 2026-11-14T23:00+01:00
commit: 3564f98 (task copy at sweep-frozen-1)
command: python3 runs/qwen-task/sweep/run_agent.py --model astra --level 2 --seeds 1 --tag frozen1 ; same with --level 3
headline: No result - both GPT-6 Astra runs (level 2 and level 3, seed 1) died after 2.7 min and 20 calls because the OpenAI account ran out of credits
---

## Hypothesis

GPT-6 Astra, which solves level 1 from the cameras (1114-2242), scores below the reference at levels 2 and 3 (reference on seed 1: 0.5 and 0.375 in-process).

## Setup

As 1114-2242 (OpenCode's own OpenAI provider, task copy of `sweep-frozen-1`), standard setting, seed 1, one run per level, side by side.

    python3 runs/qwen-task/sweep/run_agent.py --model astra --level 2 --seeds 1 --tag frozen1
    python3 runs/qwen-task/sweep/run_agent.py --model astra --level 3 --seeds 1 --tag frozen1

## Results

**Failed, no result.** Both runs stopped after 2.7 minutes with `ApiUsageLimitError: You have no credits remaining` from OpenAI. The verifier's 0.0 says nothing about the model.

| Level | Calls | Robot time | How far it got | Cost until then |
|---|---|---|---|---|
| 2 | 20 | 11.7 s | 5 pictures, 4 file downloads, 2 grasp calls, no tool held | 0.46 USD |
| 3 | 20 | 12.9 s | 5 pictures, 2 file downloads, brush in hand at 9.2 s | 0.48 USD |

The summaries are kept out of `results/sweep/agent-runs/` so the comparison page does not show them as scores; they are in `runs/sweep/not-results/` on host fls (not committed).

## Takeaways

- Nothing about levels 2 and 3. Rerun the same two commands once the OpenAI account has credits (level 1 cost 2 to 5 USD a run; expect more here).
