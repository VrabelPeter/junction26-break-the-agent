---
title: Fine-tuned Qwen3.5-9B (sft-1115-b) with thinking switched on at serving time, level 1 seed 1, standard
status: done
kind: eval
owner: frederik
host: fls
started: 2026-11-15T04:21+01:00
finished: 2026-11-15T04:27+01:00
commit: 2b1a7e2
command:
headline: Fine-tuned Qwen3.5-9B with thinking on, level 1 seed 1, standard: 0.0, stopped by us after 6 min - it reasons before every call but leaves the trained sequence at the third call and never takes a tool
reference:
agent: []
noop:
stop_early:
---

## Hypothesis

Hypothesis: the adapter was trained with thinking off only; with thinking on the model still reasons, and we see whether the learned procedure survives after a block of free thinking. Same merged model as experiment 1115-0241 (ft/sft-1115-b), served as variant qwen35-9b-ft-think (no enable_thinking=false), standard setting (cameras only), level 1 seed 1. Command: MODEL_VARIANT=qwen35-9b-ft-think FT_RUN=sft-1115-b .venv/bin/modal deploy serving/qwen_vl_modal.py ; python3 runs/qwen-task/sweep/run_agent.py --model qwen35ftthink --setting standard --level 1 --seeds 1 --tag sft-b-think . Stopped by us if still running after 25 minutes.

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

More rooms, same model and setting (thinking on, level 1, standard, cameras only), command `python3 runs/qwen-task/sweep/run_agent.py --model qwen35ftthink --setting standard --level 1 --seeds 2 3 4 5 --tag sft-b-think` (one after another):

| seed | score | tools taken | calls | minutes | how it ended |
|---|---|---|---|---|---|
| 1 | 0.0 | none | 89 | 6.0 | stopped by us |
| 2 | 0.0 | none | 225 | 17.5 | not stopped by us (OpenCode exited) |
| 3 | 0.0 | none | 122 | 7.7 | not stopped by us (OpenCode exited) |
| 4 | 0.0 | none | 0 | 0.5 | stopped by us at 04:55 CET on the human's request, before its first call: not a result |
| 5 | - | - | - | - | not run: the queue was ended at 04:55 CET, the just-started trial removed |

No thinking-on run took a tool; the same model with thinking off takes both tools on the first grasp in all five rooms (experiment 1115-0241).

## Takeaways

## Results

Run `frederik-qwen35ftthink-standard-l1-s1-1115-0421-sft-b-think`, level 1, seed 1, standard setting (cameras only), thinking on (a mode the adapter was never trained in). **Stopped by us after 6 minutes** (the agent process was ended at 04:27 CET on the human's request; Harbor then graded the room as it stood).

- **Score 0.0**, trash in bin 0 of 1, no tool taken (no milestones), 89 tool calls, 143 s of robot time.
- The thinking mode works after the fine-tune: 87 reasoning blocks, one short sentence before each call.
- The trained procedure did not survive it. With thinking off the same model reproduces the reference's sequence and takes both tools on the first grasp (experiment 1115-0241). With thinking on it left that sequence at the third call (drove up to the table instead of to the viewpoint), touched the table with the left arm, lowered the right arm onto the table several times, took two pictures, and then 62 of its 89 calls were drives; it reached towards the brush once (move_arm above the shelf) but never grasped.
- Reasoning excerpts: "Now I need to drive to the table to look for trash, aiming for the trash on the table." / "The trash on the table is at pixel (477, 203) of the colour picture." (the reference's pixel from its viewpoint is (353, 168); this picture was taken from another pose) / "The trash is on the floor, not the table. I need to look more to the left to find trash on the table."

Result files: results/sweep/agent-runs/frederik-qwen35ftthink-standard-l1-s1-1115-0421-sft-b-think.*.json

More rooms, same model and setting (thinking on, level 1, standard, cameras only), command `python3 runs/qwen-task/sweep/run_agent.py --model qwen35ftthink --setting standard --level 1 --seeds 2 3 4 5 --tag sft-b-think` (one after another):

| seed | score | tools taken | calls | minutes | how it ended |
|---|---|---|---|---|---|
| 1 | 0.0 | none | 89 | 6.0 | stopped by us |
| 2 | 0.0 | none | 225 | 17.5 | not stopped by us (OpenCode exited) |
| 3 | 0.0 | none | 122 | 7.7 | not stopped by us (OpenCode exited) |
| 4 | 0.0 | none | 0 | 0.5 | stopped by us at 04:55 CET on the human's request, before its first call: not a result |
| 5 | - | - | - | - | not run: the queue was ended at 04:55 CET, the just-started trial removed |

No thinking-on run took a tool; the same model with thinking off takes both tools on the first grasp in all five rooms (experiment 1115-0241).

## Takeaways

- Switching thinking on at serving time is not a free way to get reasoning plus the trained behaviour: the thoughts are short and plausible, but the calls drift from the learned sequence within three steps. Reasoning has to be in the training data (thinking on during training) to be kept. One run, one room, stopped early.

