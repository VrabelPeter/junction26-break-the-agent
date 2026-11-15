---
title: Training: Qwen3.5-9B LoRA on scripted-reference camera episodes (level 1, standard), then Harbor level 1 seed 1
status: done
kind: training
owner: frederik
host: fls
started: 2026-11-15T03:08+01:00
finished: 2026-11-15T03:53+01:00
commit: d1e3191
command:
headline: Fine-tuned Qwen3.5-9B (232 reference episodes), level 1 seed 1, standard: 0.0 - takes brush and bin on the first grasp and ends itself after 3 min, but sweeps 65 cm beside the trash (untrained: 0.0, no tool held)
---

## Hypothesis

Hypothesis: Qwen3.5-9B (0.0 on level 1 from the cameras, untrained) scores above 0 after supervised fine-tuning on experience from the environment. Data: 1,500 level 1 rooms (seeds 1000-2499), standard setting, the scripted reference's calls planned from one pixel of the head picture (training/camera_episodes.py), all scored 1.0 by the environment; written as OpenCode conversations with the pictures (training/camera_chats.py). Training: training/camera_sft_modal.py on one Modal H100, LoRA on all linear layers, thinking off. Evaluation: the merged model served with vLLM on Modal, Harbor + OpenCode, standard setting, level 1 seed 1 (held out: training seeds start at 1000).

## Setup

Model: Qwen/Qwen3.5-9B, thinking off. Environment: main at d1e3191. Training rooms: level 1, seeds 1000-2499 (standard setting). Evaluation room: level 1, seed 1 (not in the training seeds).

    MUJOCO_GL=egl .venv/bin/python training/camera_episodes.py --seeds 1000-2499 --level 1 --out runs/training/camera/episodes_l1.jsonl
    MUJOCO_GL=egl .venv/bin/python training/camera_chats.py --instruction runs/qwen-task/sweep/instruction.md
    .venv/bin/modal run --detach training/camera_sft_modal.py --n 600 --budget-min 75 --lr 1e-4 --run sft-1115-a
    .venv/bin/modal run --detach training/camera_sft_modal.py --n 600 --budget-min 75 --lr 2e-4 --run sft-1115-b
    MODEL_VARIANT=qwen35-9b-ft FT_RUN=sft-1115-b .venv/bin/modal deploy serving/qwen_vl_modal.py
    python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1 --model qwen35ft     (Harbor + OpenCode, standard setting)

One H100, LoRA r 32 on all linear layers, one pass, 4 episodes per step. The time-budget rule in the script judged the pace from the first 8 (slow) episodes, so each run used about 232 of the 600 rooms asked for (24 minutes of training).

## Results

Training, checked on 16 rooms held out from training (standard setting):

| run | lr | rooms used | final loss | turns reproduced exactly (teacher-forced) | pixel error, free generation (median / max) |
|---|---|---|---|---|---|
| sft-1115-a | 1e-4 | 233 | 0.009 | 89.1% | 13.3 px / 43.5 px |
| sft-1115-b | 2e-4 | 232 | 0.0085 | 91.8% | 17.0 px / 27.2 px |

Harbor run of sft-1115-b, level 1, seed 1, standard setting (cameras only), run `frederik-qwen35ft-standard-l1-s1-1115-0345-sft-b`:

- **Score 0.0.** Trash in bin 0 of 1; no mistakes. The model ended the run itself after 3.0 minutes and 53 tool calls (69 s of robot time) with the sentence "The trash is in the bin." It was not stopped by us. Harbor records `NonZeroAgentExitCodeError` because OpenCode returned exit code 1 after that final message; the summary therefore calls the run "not clean", but the episode was complete.
- Brush in hand at 27.98 s and bin in hand at 31.43 s, each on the first grasp. The untrained model (experiment 1114-2141) made 36 grasp attempts in 24 minutes and never held a tool.
- Why it missed, from the logged calls compared with the scripted reference on the same room:
  1. It named pixel (402, 199); the reference's pixel for this room is (353, 168). Its own depth lookup returned the room point x 0.506, y -0.706; the trash was at x 0.388, y -0.588 (12 cm off in each axis).
  2. It then did not use that point. It set the bin down at x -0.353 and swept along x -0.263; from its own point the reference's rule gives bin x 0.286 and sweep x 0.506. Every other call matches the reference's sequence. So the fixed procedure was learned, the numbers that depend on the trash position were not.
- Film (1920x1080 replay of the logged calls): runs/sweep/qwen35ft-sft-b-standard-level1-seed1-clean.mp4 (not committed).

Result files: results/training/camera-sft-1115-{a,b}.json, results/sweep/agent-runs/frederik-qwen35ft-standard-l1-s1-1115-0345-sft-b.*.json.

Four more rooms with the same model (sft-1115-b, thinking off, level 1, standard setting, cameras only), runs `frederik-qwen35ft-standard-l1-s{2,3,4,5}-1115-0426-sft-b`, command `python3 runs/qwen-task/sweep/run_agent.py --model qwen35ft --setting standard --level 1 --seeds <n> --tag sft-b`. All five rooms: **0.0**, each run 53 calls, ended by the model itself (same OpenCode exit-code flag as seed 1), brush in hand at 27.98 s and bin in hand at 31.43 s on the first grasp.

| seed | score | trash (x, y) | its own measured point (x, y) | line it swept (x) | note |
|---|---|---|---|---|---|
| 1 | 0.0 | 0.388, -0.588 | 0.506, -0.706 | -0.26 | |
| 2 | 0.0 | 0.548, -0.544 | 0.549, -0.574 | 0.42 | can left at the table edge beside the bin |
| 3 | 0.0 | 0.648, -0.803 | 0.607, -0.788 | 0.06 | |
| 4 | 0.0 | 0.260, -0.665 | 0.257, -0.710 | 0.18 | the brush touched the trash (63.08 s) |
| 5 | 0.0 | 0.529, -0.807 | 0.575, -0.788 | 0.03 | |

In four of five rooms the measured point is within 5 cm of the trash; the sweep line is 8 to 65 cm beside it. The failure is not using the measured point, more than the pointing.

## Takeaways

- One 24-minute training on 232 reference episodes moves the 9B model from "never holds a tool" to "takes both tools first try and runs the whole procedure in 3 minutes", but the score stays 0.0: one room, one run.
- Open: carrying the measured point into the drive and arm targets (three additions), and pointing accuracy. Next attempt: more rooms (the budget rule fixed) and the plan numbers stated right after the depth lookup.
