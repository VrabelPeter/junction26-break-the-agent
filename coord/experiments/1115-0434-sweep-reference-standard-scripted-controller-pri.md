---
title: Sweep: reference (standard), scripted controller (privileged) and both baselines rerun in-process on main d1e3191, levels 1 to 3, rooms 1 to 30
status: done
kind: eval
owner: peter
host: peter-LENOVO
started: 2026-11-15T04:06+02:00
finished: 2026-11-15T04:34+02:00
commit: d1e3191
command: cd probes/sweep/environment/env-server && MUJOCO_GL=egl python -m sweep.run -v --policy <reference|reference_privileged|do_nothing|stop_early> --seeds <1..30> --level <1|2|3>
headline: On main d1e3191, in-process, rooms 1 to 30 - reference (standard) 1.000 / 0.750 / 0.496 at levels 1 / 2 / 3; scripted controller (privileged) 1.000 / 0.908 / 0.869; do nothing and fetch-then-stop 0.0 in all 180 rooms
reference:
agent: []
noop:
stop_early:
---

## Hypothesis

Hypothesis: the scorer and server changes since the arm fix (piece under the bin, reward-file race, contact names, /log) leave every scripted score as recorded before.

## Setup

Why: the last in-process tables were from before the scorer change `d4d0261` (a piece squeezed under the bin is not in the bin) and the server changes `3792849`, `f580509`, `9b7b98c`; only seeds 1 to 5 had been rechecked. The one worktree (`.claude/worktrees/fable-sweep`) is clean and its branch is fully merged into `main`, so it holds no code that affects the reference.

In-process (no Harbor, no model), one room per process, 18 at a time, on peter-LENOVO, `main` at d1e3191, mujoco 4.0.1. 4 policies x 3 levels x seeds 1 to 30 = 360 rooms, 28 minutes.

    cd probes/sweep/environment/env-server
    MUJOCO_GL=egl python -m sweep.run -v --policy <policy> --seeds <seed> --level <level>

Per-room scores, trash counts, mistakes and robot time: `results/sweep/reference-inprocess-d1e3191-1115-0434.json`.

## Results

| Controller | Setting | Level | Rooms | Mean | Min | Rooms at 1.0 | Rooms with a mistake | Robot time, mean (max) |
|---|---|---|---|---|---|---|---|---|
| reference | standard | 1 | 30 | 1.000 | 1.0 | 30 | 0 | 114 s (158 s) |
| reference | standard | 2 | 30 | 0.750 | 0.0 (room 13) | 8 | 0 | 256 s (320 s) |
| reference | standard | 3 | 30 | 0.496 | 0.0 (room 25) | 0 | 1 (room 25: bin tipped over) | 396 s (522 s) |
| scripted controller | privileged | 1 | 30 | 1.000 | 1.0 | 30 | 0 | 71 s (115 s) |
| scripted controller | privileged | 2 | 30 | 0.908 | 0.0 (room 13) | 23 | 0 | 216 s (443 s) |
| scripted controller | privileged | 3 | 30 | 0.869 | 0.3125 (room 19) | 11 | 1 (room 19: glasses on the floor) | 364 s (480 s) |
| do nothing | - | 1, 2, 3 | 90 | 0.000 | 0.0 | 0 | 0 | 0 s |
| fetch the tools then stop | - | 1, 2, 3 | 90 | 0.000 | 0.0 | 0 | 0 | 67 to 85 s |

Reference (standard), rooms 1 to 30 in order:

- Level 2: 0.5 0.75 1 0.75 0.75 0.75 0.75 0.75 1 1 1 0.75 0 0.75 0.75 1 0.5 0.75 0.75 0.75 0.5 0.5 0.75 0.75 0.5 1 1 0.75 0.75 1
- Level 3: 0.5 0.125 0.375 0.375 0.5 0.375 0.5 0.625 0.625 0.625 0.625 0.5 0.5 0.125 0.375 0.625 0.375 0.625 0.375 0.75 0.75 0.625 0.375 0.5 0 0.375 0.625 0.875 0.875 0.375

## Takeaways

- **Nothing moved.** Level 1 is 1.0 in 30 of 30 rooms for both scripted controllers; rooms 1 to 3 at level 2 (0.5, 0.75, 1.0) match the Harbor runs of experiment 1115-0037; level 2 and 3 means match the earlier tables (0.80 and 0.51 on 10 rooms, 0.917 and 0.841 told positions) within what the larger room set explains.
- **Baselines hold after the scorer change:** 0.0 in all 180 rooms.
- **The reference (standard) is only a reference at level 1.** At level 2 it is at 1.0 in 8 of 30 rooms; at level 3 in none, and in room 25 it tips the bin (score 0). Room 13 at level 2 scores 0 for both controllers: not looked at.
- **Not rerun here:** the reference under Harbor on this commit (this session has no Docker access). The last Harbor runs of the reference: level 1 after `3792849` (1.0, in that commit's message), level 2 on the task copy at `sweep-frozen-1` (1115-0037). `f580509` changed only the wording of contact replies in the standard setting; the in-process runs do not go through `server.py`, so a Harbor run of the oracle on d1e3191 is still owed: `python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1 2 3 --skip-agent`.
