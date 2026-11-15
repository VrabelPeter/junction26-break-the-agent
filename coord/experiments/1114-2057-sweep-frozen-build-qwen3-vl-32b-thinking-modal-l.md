---
title: Sweep, frozen build: Qwen3-VL-32B-Thinking (Modal), level 1, standard seeds 1 2 3 and privileged seed 1
status: done
kind: eval
owner: frederik
host: fls
started: 2026-11-14T20:57+01:00
finished: 2026-11-14T21:23+01:00
commit: c1330c4
command: python3 runs/qwen-task/sweep/run_agent.py --model qwen32 --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1 ; same with --setting privileged --seeds 1 (task copy, see Setup)
headline: Qwen3-VL-32B-Thinking (Modal), level 1: 0.0 in all four runs, stopped by us at 25 min; it moved arms and tried to grasp (up to 11 times) but never took a tool; smoke stage had failed, so exploratory
reference:
agent: [0.0, 0.0, 0.0]
noop:
stop_early:
---

## Hypothesis

A 32 B open vision model gets further than the 2 B one (1114-2023) at level 1 but does not finish the task. Same seeds and settings as Kimi (1114-1933).

## Setup

`Qwen/Qwen3-VL-32B-Thinking` on vLLM 0.33.0, one Modal H200, window 110,000 tokens, tool calls (hermes parser), thinking returned separately (`serving/qwen_vl_modal.py`, variant `qwen-32b`). Declared to OpenCode: context 96000, output 12000. Task: the copy of the frozen task described in 1114-2023 (`runs/qwen-task/sweep`, files of `sweep-frozen-1` plus the model entry). Harbor on local Docker, four runs side by side.

    python3 runs/qwen-task/sweep/smoke.py --model qwen32 --skip-free
    python3 runs/qwen-task/sweep/run_agent.py --model qwen32 --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1
    python3 runs/qwen-task/sweep/run_agent.py --model qwen32 --level 1 --setting privileged --seeds 1 --tag frozen1

**Smoke stage failed**: tool names were right and the picture reached the model, but after describing the table (wrongly: "crumpled paper and a crushed drink can"; the room has an apple core) it ended its turn, skipping three of the five steps. The runs are exploratory.

## Results

**All four were stopped by us after 25 minutes** (the human asked; OpenCode was ended in each container, Harbor recorded `NonZeroAgentExitCodeError`, the verifier scored the room as it stood). Not clean runs.

| Run | Setting | Seed | Score | Milestones | Calls | Robot time | Input tokens |
|---|---|---|---|---|---|---|---|
| frederik-qwen32-standard-l1-s1-1114-2057-frozen1 | standard | 1 | 0.0 | none | 134 | 212 s | 5.9 M |
| frederik-qwen32-standard-l1-s2-1114-2057-frozen1 | standard | 2 | 0.0 | none | 107 | 44 s | 5.4 M |
| frederik-qwen32-standard-l1-s3-1114-2057-frozen1 | standard | 3 | 0.0 | none | 79 | 69 s | 2.5 M |
| frederik-qwen32-privileged-l1-s1-1114-2058-frozen1 | privileged | 1 | 0.0 | none | 169 | 202 s | 8.8 M |

At a check two minutes before the stop: standard seed 1 had made 5 grasp attempts, seed 3 4, the privileged run 11, none of which took a tool; seed 2 had made 72 arm moves and no grasp attempt. So unlike the 2 B model it uses the arms and tries to pick the tools up, and fails at the grasp (hand not on the handle, or not across it).

Summaries, details and call logs: `results/sweep/agent-runs/frederik-qwen32-*`. About 45 minutes of one H200; the Modal app was stopped afterwards.

## Takeaways

- Size helps a little (arms, grasp attempts) but no milestone was reached in 25 minutes in either setting; with positions given it still could not take a tool, where Kimi finished the task in 14 minutes.
- Why the grasps failed is in the call logs (the `why` of each grasp reply) and is worth a look for the failure analysis: it is the first step of the task.
