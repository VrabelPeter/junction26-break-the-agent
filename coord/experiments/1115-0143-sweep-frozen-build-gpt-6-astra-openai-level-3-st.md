---
title: Sweep, frozen build: GPT-6 Astra (OpenAI), level 3, standard, seed 1 (rerun after the spend limit)
status: done
kind: probe
owner: frederik
host: fls
started: 2026-11-15T01:43+01:00
finished: 2026-11-15T01:52+01:00
commit: 3564f98 (task copy at sweep-frozen-1)
command: python3 runs/qwen-task/sweep/run_agent.py --model astra --level 3 --seeds 1 --tag frozen1
headline: GPT-6 Astra (OpenAI), level 3, cameras, seed 1 - 1.0 clean: all 8 trash in the bin, 5 personal items untouched, 144 s robot time, 7.6 min, 4.78 USD. The camera reference scores 0.375 on this room in-process - the agent beats the reference
---

## Hypothesis

GPT-6 Astra scores below the reference at level 3, seed 1 (camera reference in-process: 0.375; told positions: 0.875). **Refuted: it scored 1.0.**

## Setup

As 1115-0048 (OpenCode's own OpenAI provider, OpenCode 1.19.5, task copy of `sweep-frozen-1`, commit 3564f98), standard setting, level 3, seed 1, one run. Rerun of 1114-2257 (no credits) and 1115-0138 (spend limit).

    python3 runs/qwen-task/sweep/run_agent.py --model astra --level 3 --seeds 1 --tag frozen1

## Results

Clean run, ended by itself, `error: null`.

| Score | Trash in bin | Mistakes | Calls | Robot time | Wall | Cost (OpenCode) |
|---|---|---|---|---|---|---|
| 1.0 | 8 of 8 | none | 115 | 144 s | 7.6 min | 4.78 USD |

- Milestones: brush in hand 8.3 s, bin in hand 16.4 s, first trash in the bin 40.9 s, all trash in the bin 137.0 s. The brush touched a personal item once (26.4 s); jacket, keys, remote, book and glasses all stayed where they were.
- **How it did it**: it never put the bin down while working. It held the bin by its handle in the right hand at the edge of the surface (hand at z 0.43 at the table, 0.37 to 0.40 at the sofa), swept each piece with the brush in the left hand straight over the edge into the held bin, and moved robot and bin along the edge from piece to piece: table from the near side (three stops), table from the far side (two stops), then the sofa. It set the bin down upright at 140.9 s and stopped.
- 25 pictures, 12 depth and calibration downloads, 45 arm moves, 12 drives.

The scripted reference places the bin on the floor, lets go, sweeps, and fetches the bin again for the next place; on this room it scores 0.375 from the cameras (3 of 8) in 343 s and 0.875 told the positions (7 of 8) in 331 s (in-process, 15 Nov). No reference run under Harbor exists at level 3.

Summary, details, call log: `results/sweep/agent-runs/frederik-astra-standard-l3-s1-1115-0143-frozen1.*`.

## Takeaways

- **GPT-6 Astra beats our reference at level 3**, on the one room tried: 1.0 against 0.375 (cameras) and 0.875 (told positions), in less than half the robot time. With levels 1 and 2 (1114-2242, 1115-0048) there is no level at which the reference is the stronger run against this model.
- Its method is better than the reference's, and legitimate under the rules ("how the trash gets into the bin is up to you"): carrying the bin along removes the bin-placement errors that cost it pieces at level 2 when it had set the bin on the floor.
- One room, one run. Seeds 2 and 3 at level 3 would show whether it repeats.
- For the gap criterion the team has to choose: name the weaker models as the frontier agents, or build a reference that uses the hold-the-bin method (and then needs to beat 1.0, which it cannot), or make the task harder in a way this method does not solve.
