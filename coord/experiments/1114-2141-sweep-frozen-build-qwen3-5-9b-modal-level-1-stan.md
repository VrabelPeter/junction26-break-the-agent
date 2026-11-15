---
title: Sweep, frozen build: Qwen3.5-9B (Modal), level 1, standard seeds 1 2 3 and privileged seed 1
status: done
kind: eval
owner: frederik
host: fls
started: 2026-11-14T21:41+01:00
finished: 2026-11-14T22:19+01:00
commit: 3564f98 (task copy at sweep-frozen-1)
command: python3 runs/qwen-task/sweep/run_agent.py --model qwen35 --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1 ; same with --setting privileged --seeds 1 (task copy, see Setup)
headline: Qwen3.5-9B (Modal), level 1, smoke test passed - 0.0 in standard seeds 1 2 3 and 0.0 privileged, all four cut off by us at 24 min; the most active open model (130 to 263 calls, 36 grasp attempts) but no tool taken, one bin tipped
reference:
agent: [0.0, 0.0, 0.0]
noop:
stop_early:
---

## Hypothesis

A small open vision model, Qwen3.5-9B, scores below the camera reference (1.0) at level 1. Same seeds and settings as Kimi (1114-1933). It is also the candidate for the fine-tuning experiment, so this is its untrained baseline under Harbor.

## Setup

`Qwen/Qwen3.5-9B` on vLLM 0.33.0, one Modal L40S, window 110,000 tokens, `qwen3_coder` tool-call parser, `qwen3` reasoning parser, thinking at its default (on), `--mm-encoder-tp-mode data` (`serving/qwen_vl_modal.py`, variant `qwen35-9b`). Declared to OpenCode: context 96000, output 12000. Task: the copy of the frozen task (`runs/qwen-task/sweep`, files of tag `sweep-frozen-1` plus the model's entries; summaries carry `commit: 3564f98`). Harbor on local Docker, four runs side by side on the one GPU.

    python3 runs/qwen-task/sweep/smoke.py --model qwen35 --skip-free
    python3 runs/qwen-task/sweep/run_agent.py --model qwen35 --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1
    python3 runs/qwen-task/sweep/run_agent.py --model qwen35 --level 1 --setting privileged --seeds 1 --tag frozen1

**Smoke test passed** (5 calls in 322 s: get_task, camera, depth file, observe, drive_to; the picture reached the model). Modal replaced the container once during the smoke stage, which is why it took 322 s.

## Results

All four are **not clean runs**: we killed the agent at 24 minutes of wall time at the human's request (`error: agent cut off`).

| Run | Setting | Seed | Score | Mistakes | Milestones | Calls | Robot time | Wall | Input tokens |
|---|---|---|---|---|---|---|---|---|---|
| frederik-qwen35-standard-l1-s1-1114-2153-frozen1 | standard | 1 | 0.0 | none | none | 262 | 213 s | 24.1 min | 11.8 M |
| frederik-qwen35-standard-l1-s2-1114-2153-frozen1 | standard | 2 | 0.0 | bin tipped over | none | 263 | 379 s | 24.1 min | 12.0 M |
| frederik-qwen35-standard-l1-s3-1114-2153-frozen1 | standard | 3 | 0.0 | none | none | 130 | 128 s | 24.1 min | 5.0 M |
| frederik-qwen35-privileged-l1-s1-1114-2154-frozen1 | privileged | 1 | 0.0 | none | none | 210 | 139 s | 23.8 min | 9.6 M |

- Over the four runs: 200 arm moves, 199 drives, 185 head turns, 134 reach checks, 80 pictures, 36 grasp calls, 22 shell commands. No grasp took a tool, so there is no milestone in any run.
- It read the measured depth file in two of three standard runs (1 and 7 downloads); the other standard run used pictures only.
- Standard seed 2 knocked the bin over while driving (102 drives).
- Privileged: told where the handles are, 58 arm moves, 81 reach checks and 15 grasp calls still took nothing.
- About 6 to 11 calls a minute, two to three times Qwen3.8-27B.

Separate check (not under Harbor, 14 Nov 22:25): asked directly to point at the trash in the head picture from the reference's table viewpoint, rooms 1 to 8, thinking off: 3 answers unusable, the other 5 off by 0.02 to 0.30 m (4 of them over 0.13 m). The task needs about 0.02 m.

Summaries, details, call logs: `results/sweep/agent-runs/frederik-qwen35-*`.

## Takeaways

- 0.0 in both settings. The model acts a lot and uses the right tools (reach checks, grasp), but its hand never ends within 0.035 m of a handle: the failure is getting positions right, with or without being told them.
- The scores are lower bounds (runs cut off), as for Kimi's standard runs.
- This is the baseline for the fine-tuning task (`training-large-experience-set-and-fine-tune-qwen`): the model moves and chains calls, so teaching it where things are and the exact sequence is a plausible gain.
