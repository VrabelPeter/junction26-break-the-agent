---
title: Sweep, frozen build: Kimi K3.1 Pro, standard setting, level 1, seed 1
status: failed
kind: eval
owner: frederik
host: fls
started: 2026-11-14T18:47+01:00
finished: 2026-11-14T19:28+01:00
commit: 9ffe069
command: python3 probes/sweep/run_agent.py --model kimi --level 1 --seeds 1 --tag sweep-frozen-1
headline: Kimi K3.1 Pro, standard, level 1 seed 1, frozen build: stopped by us after 40.6 min, no verifier score; at the stop the apple core lay on the floor (replayed state scores 0.0), 5.15 USD
reference:
agent: []
noop:
stop_early:
---

## Hypothesis

On the frozen build (tag `sweep-frozen-1`), OpenCode + Kimi K3.1 Pro in the standard setting (cameras, no positions) scores clearly below the camera reference (1.0 under Harbor, experiment 1114-1835) at level 1.

## Setup

Commit 7eda2eb on main; `probes/sweep` and `eval/` identical to tag `sweep-frozen-1`. Local Docker on frederik's machine. Smoke test with Kimi passed on this build and machine at 18:46 (do-nothing 0.0, interface ok, camera reference 1.0, model received the picture and acted).

    python3 probes/sweep/run_agent.py --model kimi --level 1 --seeds 1 --tag sweep-frozen-1

Model `verda/kimi-k3-1-pro` through OpenCode, context limit 96000 declared. Level 1, seed 1, standard setting.

## Results

**Not a scored run: stopped by us (the human asked to stop it) after 40.6 minutes. The verifier never ran, so there is no reward.** Do not count it among the three agent runs.

State at the stop, from the server's call log (saved just before stopping) replayed in-process:

- 385 logged calls (107 move_arm, 82 can_reach, 52 camera, 49 camera files, 29 drive_to, 16 grasp, 13 release), 311 s of the 900 s robot time used.
- Milestones: bin in hand 12.9 s, brush in hand 17.4 s, brush touched the trash 118.7 s. No trash in the bin.
- The apple core lay on the floor near (0.24, -0.98), just off the table's south edge; the bin stood upright near (-0.48, -1.50), about 0.9 m away; the left hand held the brush. Scoring the replayed copy gives 0.0, no mistakes.
- At 18 minutes (198 calls, 217 s) the core was already on the floor at (0.38, -0.99) with the bin at (-0.43, -1.32): the piece left the table where the bin was not, and the remaining time went into working on the core on the floor.
- Tokens: 0.33 M input, 14.4 M cached input, 0.16 M output; 5.15 USD by `run_agent.py`'s price table.

Files: `results/sweep/agent-runs/frederik-kimi-standard-l1-s1-1114-1847-sweep-frozen-1.summary.json` (score null) and `...commands-at-stop.json` (the call log at the stop). Full trial in `runs/sweep/` on frederik's machine.

## Takeaways

- Same failure pattern as the earlier Kimi runs (experiment 1114-1500): tools fetched quickly, the piece swept off the table beside the bin, then a long attempt to recover it from the floor.
- The run was heading for 0 but was not allowed to finish, so it is evidence for the failure analysis only, not a score. The three standard seeds and the privileged run of the task are still to do.
