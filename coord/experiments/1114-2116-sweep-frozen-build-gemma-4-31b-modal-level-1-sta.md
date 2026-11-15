---
title: Sweep, frozen build: Gemma 4 31B (Modal), level 1, standard seeds 1 2 3 and privileged seed 1
status: done
kind: eval
owner: frederik
host: fls
started: 2026-11-14T21:16+01:00
finished: 2026-11-14T21:28+01:00
commit: 3564f98 (task copy at sweep-frozen-1)
command: python3 runs/qwen-task/sweep/run_agent.py --model gemma4 --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1 ; same with --setting privileged --seeds 1 (task copy, see Setup)
headline: Gemma 4 31B (Modal), level 1, four clean runs after a passing smoke test: 0.0 in standard seeds 1 2 3 and 0.0 privileged (it took the bin, then drove for 880 s and tipped it); no brush in any run
reference:
agent: [0.0, 0.0, 0.0]
noop:
stop_early:
---

## Hypothesis

An open 31 B vision model with native tool calls, Gemma 4 31B, scores below the camera reference (1.0) at level 1. Same seeds and settings as Kimi (1114-1933).

## Setup

`google/gemma-4-31B-it` on vLLM 0.33.0, one Modal H200, window 110,000 tokens, vLLM's `gemma4` tool-call and reasoning parsers, thinking left at its default (off) (`serving/qwen_vl_modal.py`, variant `gemma4-31b`). Declared to OpenCode: context 96000, output 12000. Task: the copy of the frozen task (`runs/qwen-task/sweep`: the files of tag `sweep-frozen-1` plus the model's entry in `models.json` and `opencode-models.json`; the summaries carry `commit: 3564f98` and a `task` note). Harbor on local Docker, four runs side by side.

    python3 runs/qwen-task/sweep/smoke.py --model gemma4 --skip-free
    python3 runs/qwen-task/sweep/run_agent.py --model gemma4 --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1
    python3 runs/qwen-task/sweep/run_agent.py --model gemma4 --level 1 --setting privileged --seeds 1 --tag frozen1

**Smoke test passed** (free stages on this copy at 20:23; model stage at 21:16: 5 calls in 34 s, get_task, camera, observe, depth file, drive_to; the picture reached the model). Direct requests to the endpoint: a correct description of a picture, a correct `drive_to` tool call.

## Results

All four ended by themselves, `error: null`.

| Run | Setting | Seed | Score | Mistakes | Milestones | Calls | Robot time | Wall | Input tokens |
|---|---|---|---|---|---|---|---|---|---|
| frederik-gemma4-standard-l1-s1-1114-2116-frozen1 | standard | 1 | 0.0 | none | none | 111 | 176 s | 3.9 min | 2.7 M |
| frederik-gemma4-standard-l1-s2-1114-2116-frozen1 | standard | 2 | 0.0 | none | none | 97 | 83 s | 3.8 min | 2.1 M |
| frederik-gemma4-standard-l1-s3-1114-2116-frozen1 | standard | 3 | 0.0 | none | none | 279 | 429 s | 11.0 min | 13.6 M |
| frederik-gemma4-privileged-l1-s1-1114-2117-frozen1 | privileged | 1 | 0.0 | bin tipped over | bin in hand 25.7 s | 319 | 880 s | 10.9 min | 15.6 M |

What each did (from the logged calls and the agent's last message):

- Standard 1: 15 camera pictures, 9 grasp attempts at the brush between 25 and 159 s, none took it; stopped saying the handle "is not within reach or correctly aligned".
- Standard 2: 26 camera pictures and 43 drives, no arm move; it found "a red object (likely trash) on the coffee table", announced it would fetch the tools, and ended its turn there.
- Standard 3: 5 pictures, 96 arm moves and 66 `home_arm`, no grasp call; still planning how to reach the brush when it stopped.
- Privileged 1: took the bin at 26 s, then 307 drives trying to place the bin "under the coffee table", used 880 of 900 s, never took the brush; the bin ended on its side.

Summaries, details, call logs: `results/sweep/agent-runs/frederik-gemma4-*`. About 15 minutes of one H200.

## Takeaways

- First open model with a passing smoke test and four clean runs: 0.0 everywhere, in both settings, in under 12 minutes a run and at no API cost.
- The failure is earlier than Kimi's: the brush is never taken (wrong hand position at the handle, or no grasp at all), so sweeping is never reached. With positions given it took the bin but misread where the bin goes ("under the table").
- Two standard runs ended after 4 minutes because the model stopped by itself with the task unfinished; that is the model's decision, the time limit was far away.
