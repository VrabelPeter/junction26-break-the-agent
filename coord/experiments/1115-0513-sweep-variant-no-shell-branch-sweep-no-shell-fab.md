---
title: Sweep variant no-shell (branch sweep-no-shell-fable): Claude Fable 5.2 (effort medium), level 1, standard, seed 1
status: done
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-15T05:13+02:00
finished: 2026-11-15T05:19+02:00
commit: bb71e44 (branch sweep-no-shell-fable, a tagged variant, not main)
command: (in the worktree on branch sweep-no-shell-fable) python3 probes/sweep/run_agent.py --model fable --level 1 --seeds 1 --tag noshell
headline: Variant without shell or code - Claude Fable 5.2 (effort medium), level 1, standard (cameras), room 1 - 1.0, clean, 78 calls, 81 s robot time, 6.1 min, 2.17 USD. Taking the shell away does not create a gap for this model
---

## Hypothesis

## Setup

Started by Peter in `.claude/worktrees/fable-sweep`, branch `sweep-no-shell-fable` at bb71e44: the no-shell variant (`sweep-no-shell`, fd61c11: OpenCode permission bash=deny, instruction without Python, code or downloads) plus the Fable entry at effort medium. Local Docker, standard setting, level 1, seed 1. This is a variant; do not mix it with runs on `main`.

    python3 probes/sweep/run_agent.py --model fable --level 1 --seeds 1 --tag noshell

## Results

| Run | Setting | Room | Score | Trash in bin | Mistakes | Milestones (robot s) | Calls | Robot time | Wall | Cost | How it ended |
|---|---|---|---|---|---|---|---|---|---|---|---|
| peter-fable-standard-l1-s1-1115-0513-noshell | standard, no shell | 1 | 1.0 | 1 of 1 | none | brush 9.3, bin 12.5, touched 55.4, in bin 60.0 | 78 | 80.8 s | 6.1 min | 2.17 USD | clean, error null |

Summary, details and calls: `results/sweep/agent-runs/peter-fable-standard-l1-s1-1115-0513-noshell.*` on branch `sweep-no-shell-fable`.

## Takeaways

- Without a shell, looking at the pictures only, Fable 5.2 solves level 1 room 1 in 78 calls. GPT-6 Astra on the same variant and room had 0.0 when stopped by us at 11 min (1115-0208), so the variant separates the two models on one room each; one seed, not a result to headline.
- Not checked in this session: the trajectory (how it located the handles without code).
