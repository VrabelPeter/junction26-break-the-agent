---
title: Training round 2: Qwen3.5-9B LoRA on reference camera episodes with a locate-and-plan script, weighted position tokens, ~600 rooms; then Harbor level 1 seed 1 (standard)
status: running
kind: training
owner: frederik
host: fls
started: 2026-11-15T04:20+01:00
finished:
commit: b2da326
command:
headline:
---

## Hypothesis

Hypothesis: the fine-tuned Qwen3.5-9B of round 1 (experiment 1115-0241: 0.0, both tools taken, swept 65 cm beside the trash) scores above 0 on level 1 seed 1 in the standard setting (cameras only) when the training episodes (a) use a shell script that returns the centre of what stands on the table near the named pixel and prints the numbers the following moves use, (b) state that plan once in text, (c) weight the tokens that differ between rooms 5x, and (d) about 600 rooms are used instead of 232.

## Setup

Model: Qwen/Qwen3.5-9B, thinking off in training. Code: main at 4f74bb6. Training rooms: level 1, seeds 1000-2499, standard setting (cameras only). Evaluation room: level 1, seed 1 (not a training seed).

What changed against round 1 (experiment 1115-0241):

- **The shell script** the model writes after the head picture (training/locate_plan.py) no longer reads one pixel. It looks at the depth image within 80 pixels of the named pixel, takes what stands on the coffee table there, and prints its centre and the steps that sweep it into the bin (the scripted reference's way of working for one piece on the table: which edge, whether to pull it closer first, where to stand, where the bin goes, the strokes). A step can say `right_hand.x`: take it from the last observe reply.
- **The episodes** play exactly those printed steps. All 1,500 rooms score 1.0 this way (537 south edge, 517 north edge, 446 with a gathering pull first).
- **The conversation**: after the script's output the model states where the trash is and which edge it uses, and every call carries "Step n."
- **Training**: number tokens count 5 times in the loss (not the fixed numbers inside the script); the pace is judged again every 30 episodes, so the whole set asked for is used.

Check of the script on 50 rooms not used for training (seeds 2500-2549): with the pixel moved 20 to 50 px off the trash in a random direction, 200 of 200 lookups returned the same centre as with the exact pixel; 185 of 200 are within 2 cm of the true centre in both axes (the others are 2 to 3 cm off in y for the same rooms with the exact pixel: the camera sees the near side of the piece). A pixel far from anything prints an ERROR line (50 of 50).

    MUJOCO_GL=egl .venv/bin/python training/camera_episodes.py --seeds 1000-2499 --level 1 --out runs/training/camera/episodes2_l1.jsonl
    MUJOCO_GL=egl .venv/bin/python training/camera_chats.py --episodes runs/training/camera/episodes2_l1.jsonl --out runs/training/camera/chats2_l1 --instruction runs/qwen-task/sweep/instruction.md
    .venv/bin/modal run training/camera_sft_modal.py --smoke --run smoke3
    .venv/bin/modal run --detach training/camera_sft_modal.py --n 600 --budget-min 75 --lr 2e-4 --run sft-1115-c
    MODEL_VARIANT=qwen35-9b-ft FT_RUN=sft-1115-c .venv/bin/modal deploy serving/qwen_vl_modal.py
    python3 runs/qwen-task/sweep/run_agent.py --model qwen35ft --setting standard --level 1 --seeds 1 --tag sft-c

## Results

(training running since 04:24 CET)

## Takeaways
