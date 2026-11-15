---
title: Sweep, frozen build: GPT-6 Astra (OpenAI), level 2, standard, seed 1 (rerun after credits)
status: done
kind: probe
owner: frederik
host: fls
started: 2026-11-14T23:03+01:00
finished: 2026-11-14T23:12+01:00
commit: 3564f98 (task copy at sweep-frozen-1)
command: python3 runs/qwen-task/sweep/run_agent.py --model astra --level 2 --seeds 1 --tag frozen1
headline: GPT-6 Astra (OpenAI), level 2, cameras, seed 1 - 0.25 when stopped by us at 8.1 min (1 of 4 trash in the bin, 3 swept onto the floor, no mistakes); the reference scores 0.5 on this room in-process
---

## Hypothesis

GPT-6 Astra, which solves level 1 from the cameras (1114-2242), scores below the scripted reference at level 2 (reference on seed 1, in-process for the comparison page: 0.5).

## Setup

As 1114-2242 (OpenCode's own OpenAI provider, task copy of `sweep-frozen-1`, commit 3564f98), standard setting, level 2, seed 1, one run. Rerun of 1114-2257, which died for lack of OpenAI credits.

    python3 runs/qwen-task/sweep/run_agent.py --model astra --level 2 --seeds 1 --tag frozen1

## Results

**Not a clean run**: the human asked to stop it and we killed the agent at 8.1 minutes (`error: agent cut off`), with 154 of 900 s robot time used.

| Score | Trash in bin | Mistakes | Calls | Robot time | Wall | Cost (OpenCode) |
|---|---|---|---|---|---|---|
| 0.25 | 1 of 4 | none | 99 | 154 s | 8.1 min | 3.44 USD |

- Brush in hand at 23.2 s, bin at 25.4 s, first brush contact with trash at 35.7 s, first trash in the bin at 105.7 s.
- End state: paper ball in the bin; both wrappers and the banana peel on the floor; remote and book untouched on the table.
- 13 pictures, 10 depth and calibration downloads, 30 arm moves, 21 drives.

Trash on the floor earns nothing, and nothing in the logged runs so far has brought a piece back from the floor, so 0.25 is likely also what an uncut run would have ended with unless it tipped the bin; that is a judgment, not a measurement.

Summary, details, call log: `results/sweep/agent-runs/frederik-astra-standard-l2-s1-1114-2303-frozen1.*`.

## Takeaways

- First sign of a gap against GPT-6 Astra: 0.25 at level 2 against the reference's 0.5 on the same room. One run, cut off, so it is an indication only.
- The failure is where the trash falls: three of four pieces went over the table edge with no bin underneath. It kept the personal items safe.
- Needed for the gap criterion: three clean runs at level 2 (seeds 1 2 3), and the reference's score on those rooms under Harbor.
