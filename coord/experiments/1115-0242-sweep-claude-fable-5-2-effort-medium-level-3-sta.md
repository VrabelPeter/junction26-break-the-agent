---
title: Sweep: Claude Fable 5.2 (effort medium), level 3, standard, seeds 1 2 3
status: done
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-15T02:48+02:00
finished: 2026-11-15T03:06+02:00
commit: 6e3bdb9
command: python3 probes/sweep/run_agent.py --model fable --setting standard --level 3 --seeds 1 2 3 --parallel 3   (fable entry at "variant": "medium")
headline: Claude Fable 5.2 (effort medium), level 3, standard (cameras) - 1.0, 1.0, 0.875 (7 of 8: it reported the banana peel binned, it lay on the floor), all clean, no mistakes, 15 to 17 min and 4 to 5 USD each; the camera reference scores 0.5 / 0.125 / 0.375. No gap at level 3: Fable far above the reference
---

## Hypothesis

Level 3 (8 trash, 4 personal items, table and sofa) is where the camera reference is weak; does the frontier agent fall below it? GPT-6 Astra scored 1.0 on seed 1 (1115-0143).

## Setup

- `anthropic/claude-fable-5-2` through OpenCode 1.19.5 under Harbor, local Docker, three runs side by side, **effort medium** (`--variant medium` in each trial's `config.json`).
- Setting: **standard** (cameras: colour, depth, calibration, joint readings). Level 3, seeds 1 2 3.
- Build: main 25a46e5 at run time; the summaries say `25a46e5+uncommitted` because the medium entry in `probes/sweep/models.json` was not committed yet. Checked file by file: the task files (instruction, task.toml, environment, tests, solution) match 25a46e5; the medium entry is on main since 0119519.
- Reference: camera reference, in-process on main, from the comparison page build (15 Nov 04:20): 0.5, 0.125, 0.375 (mean 0.33). Note: 1115-0143 quotes 0.375 for seed 1, measured on the frozen1 build; on main it is 0.5.

## Results

| Level 3, standard | Seed 1 | Seed 2 | Seed 3 | Mean |
|---|---|---|---|---|
| Reference (cameras, in-process, main) | 0.5 | 0.125 | 0.375 | 0.33 |
| GPT-6 Astra (frozen1 build) | 1.0 clean | - | - | |
| **Claude Fable 5.2, effort medium (main)** | **1.0 clean** | **1.0 clean** | **0.875 clean** | **0.96** |

| Seed | Score | Trash in bin | Mistakes | Robot time | Wall time | Simulator calls | Model steps | Thinking (longest / total) | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1.0 | 8 of 8 | none | 279 s | 16.9 min | 630 (341 can_reach) | 72 | 151 s / 612 s | 5.27 USD |
| 2 | 1.0 | 8 of 8 | none | 280 s | 15.1 min | 467 (167 can_reach) | 80 | 82 s / 512 s | 4.72 USD |
| 3 | 0.875 | 7 of 8 | none | 295 s | 14.5 min | 822 (298 observe) | 67 | 71 s / 492 s | 4.03 USD |

Total 14.02 USD. All three ended by themselves.

Seed 3: the banana peel ended on the floor. The agent's final report lists "the banana peel" among the pieces that went into the bin; its check was a top-down picture into the bin, and it did not look at the floor around the table. The brush also touched a personal item (milestone `brush_touched_personal_item` at 86.9 s), without a mistake.

Summaries, details, commands: `results/sweep/agent-runs/peter-fable-standard-l3-s{1,2,3}-1115-0249.*`. Films on the comparison page (level 3).

## Takeaways

- **Level 3 is no gap for Fable 5.2 at medium effort** either: 0.96 mean against the reference's 0.33. Astra (1.0 on seed 1) agrees. With shell and code available, the frontier agents beat our scripted reference on every level.
- The one miss is a verification mistake (claimed a piece binned that fell to the floor), the kind of failure the difficulty section can use.
- Next: the no-code variant (Frederik's branch `sweep-no-shell`; Astra scored 0.0 there at level 1, seed 1, stopped by us), with Fable at the same level and seed.
