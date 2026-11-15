---
title: Sweep, frozen build: Qwen3.8-27B (Modal), level 1, standard seeds 1 2 3 and privileged seed 1
status: done
kind: eval
owner: frederik
host: fls
started: 2026-11-14T21:41+01:00
finished: 2026-11-14T22:02+01:00
commit: 3564f98 (task copy at sweep-frozen-1)
command: python3 runs/qwen-task/sweep/run_agent.py --model qwen38 --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1 ; same with --setting privileged --seeds 1 (task copy, see Setup)
headline: Qwen3.8-27B (Modal), level 1, smoke test passed - 0.0 in standard seeds 1 2 3 (cut off by us at 25 min, no tool taken) and 0.0 privileged (stopped by itself after two calls, robot never moved)
reference:
agent: [0.0, 0.0, 0.0]
noop:
stop_early:
---

## Hypothesis

A newer open 27 B vision model, Qwen3.8-27B, scores below the camera reference (1.0) at level 1. Same seeds and settings as Kimi (1114-1933).

## Setup

`Qwen/Qwen3.8-27B` on vLLM 0.33.0, one Modal H200, window 110,000 tokens, `qwen3_coder` tool-call parser, `qwen3` reasoning parser, thinking at its default (on), `--mm-encoder-tp-mode data` (`serving/qwen_vl_modal.py`, variant `qwen38-27b`). Declared to OpenCode: context 96000, output 12000. Task: the copy of the frozen task (`runs/qwen-task/sweep`, files of tag `sweep-frozen-1` plus the model's entries; summaries carry `commit: 3564f98`). Harbor on local Docker, four runs side by side on the one GPU.

    python3 runs/qwen-task/sweep/smoke.py --model qwen38 --skip-free
    python3 runs/qwen-task/sweep/run_agent.py --model qwen38 --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1
    python3 runs/qwen-task/sweep/run_agent.py --model qwen38 --level 1 --setting privileged --seeds 1 --tag frozen1

**Smoke test passed** (model stage: picture reached the model, 3.4 s a step).

## Results

| Run | Setting | Seed | Score | Mistakes | Milestones | Calls | Robot time | Wall | Input tokens | Ended |
|---|---|---|---|---|---|---|---|---|---|---|
| frederik-qwen38-standard-l1-s1-1114-2136-frozen1 | standard | 1 | 0.0 | none | none | 69 | 65.5 s | 24.9 min | 3.4 M | cut off by us |
| frederik-qwen38-standard-l1-s2-1114-2136-frozen1 | standard | 2 | 0.0 | none | none | 66 | 45.9 s | 24.9 min | 3.2 M | cut off by us |
| frederik-qwen38-standard-l1-s3-1114-2136-frozen1 | standard | 3 | 0.0 | none | none | 53 | 14.8 s | 24.9 min | 2.6 M | cut off by us |
| frederik-qwen38-privileged-l1-s1-1114-2136-frozen1 | privileged | 1 | 0.0 | none | none | 2 | 0 s | 3.9 min | 25 k | by itself |

- The three standard runs are **not clean**: we killed the agent at 25 minutes of wall time (`error: agent cut off`), with 835 s or more of the robot's 900 s unused. They mostly looked: 3 to 22 camera pictures, 12 to 30 camera files and 9 to 15 `look` calls each, 1 to 8 drives, at most 6 arm moves. One grasp call in total (seed 3), which took nothing.
- Privileged: `get_task` and `observe`, then about 12,000 output tokens of thinking in two steps (6,038 thinking tokens a step, 105 s a step) and the model ended its turn. The robot never moved.
- Speed: about 3 calls a minute in the standard runs. Gemma on the same hardware did about 25.

Summaries, details, call logs: `results/sweep/agent-runs/frederik-qwen38-*`.

## Takeaways

- 0.0 in both settings; no milestone in any run. The model fails before manipulation: it spends its wall time looking and thinking.
- The standard scores are a lower bound of what an uncut run would do, as with Kimi's standard runs; the privileged 0.0 is a clean result.
- Long thinking per step, not the simulator, is what makes this model slow here.
