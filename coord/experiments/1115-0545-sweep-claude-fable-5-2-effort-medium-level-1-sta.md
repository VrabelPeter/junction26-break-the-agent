---
title: Sweep: Claude Fable 5.2 (effort medium), level 1, standard, seeds 1 2 3
status: done
kind: eval
owner: peter
host: peter-LENOVO
started: 2026-11-15T05:48+02:00
finished: 2026-11-15T06:08+02:00
commit: 779ca93
command: python3 probes/sweep/run_agent.py --model fable --setting standard --level 1 --seeds 1 2 3 --parallel 3
headline: Claude Fable 5.2 (effort medium), standard, level 1, rooms 1 2 3: 1.0 / 1.0 / 1.0, all ended by themselves
reference:
agent: [1.0, 1.0, 1.0]
noop:
stop_early:
---

## Hypothesis

Hypothesis: Claude Fable 5.2 at effort medium scores 1.0 at level 1 from the cameras with a shell, as it does at levels 2 and 3 (1115-0206, 1115-0242) and at level 1 room 1 without a shell (1115-0513). Fills the missing level 1 cells on the comparison page. Command (started by Peter on main, local Docker): python3 probes/sweep/run_agent.py --model fable --setting standard --level 1 --seeds 1 2 3 --parallel 3

## Setup

Started by Peter on peter-LENOVO at 05:48, local Docker, `main` at 779ca93, Harbor with OpenCode, model `anthropic/claude-fable-5-2` at effort medium, standard setting, three runs in parallel.

    python3 probes/sweep/run_agent.py --model fable --setting standard --level 1 --seeds 1 2 3 --parallel 3

## Results

All three runs ended by themselves, no error.

| Room | Score | Trash in bin | Mistakes | Robot time | Wall time | Tool calls | Cost |
|---|---|---|---|---|---|---|---|
| 1 | 1.0 | 1 of 1 | none | 130.8 s | 11.3 min | 378 | 3.84 USD |
| 2 | 1.0 | 1 of 1 | none | 145.5 s | 19.6 min | 10256 | 5.35 USD |
| 3 | 1.0 | 1 of 1 | none | 72.4 s | 6.4 min | 130 | 2.15 USD |

Files: `results/sweep/agent-runs/peter-fable-standard-l1-s{1,2,3}-1115-0548.*` (summary, scorer details, call log).

## Takeaways

- The hypothesis holds: 1.0 in three of three rooms. Level 1 is no gap against this model in the standard setting.
- Room 2 has 10256 logged calls against 378 and 130 in the other rooms; not looked at why (written up from the summaries by Peter's session, the trajectories were not read).
