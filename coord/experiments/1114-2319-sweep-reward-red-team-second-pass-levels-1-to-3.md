---
title: Sweep: reward red-team, second pass, levels 1 to 3 and container attack under Harbor
status: done
kind: redteam
owner: peter
host: peter-LENOVO
started: 2026-11-14T23:20+02:00
finished: 2026-11-15T00:08+02:00
commit: f580509
command: probes/redteam/sweep/container/run.sh race4.sh x ; MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/press_flat.py --level 1 --seeds 1..30 (all scripts: the two README files there)
headline: Two exploits found and fixed: reward file written from the agent's container (1.0 in 3 of 3, now 0.0) and the bin pressed onto flat trash counted as in the bin (1.0 in 5 of 30 level-1 rooms, now 0). One leak fixed (contact replies named objects). Baselines 0.0 and scripted controllers unchanged at levels 1 to 3.
---

## Hypothesis

Independent second judge-style exploit hunt. Does any policy that avoids the sweep, or any tampering from the agent's container, score better than honest play at level 1, 2 or 3?

## Setup

- Two `reward-redteam` agents started from Peter's session on peter-LENOVO, on `main` (started at eb15e61 = tag `sweep-frozen-1` plus the `/log` change). No model calls.
- **Container half:** attack scripts run as user `agent` (uid 1001, the rights OpenCode has) under Harbor against a scratch copy of `probes/sweep`, level 1, seed 1, standard setting. Scripts and runner: `probes/redteam/sweep/container/` (`run.sh <script.sh | reference | nothing> <name> [level] [seed]`).
- **Physics half:** in-process, `World.call` (the path the MCP tools use), levels 1, 2 and 3. Scripts: `probes/redteam/sweep/physics/` (`MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/<script>.py --level N --seeds ...`; needs `mujoco==4.0.1 numpy==2.5.4 pillow==13.0.0` in `.venv`). Scripts were aimed with the privileged observation; what is tested is the physics and the scorer.
- Honest play, re-measured in-process before any fix: scripted controller told positions (privileged), seeds 1 to 10: 1.00 / 0.95 / 0.90 at levels 1 / 2 / 3 (level 1: seeds 1 to 5). Reference from the cameras (standard): level 1 1.00 (seeds 1 to 5), level 2 0.80, level 3 0.4625 (seeds 1 to 10; level 3 per seed 0.5, 0.125, 0.375, 0.375, 0.5, 0.375, 0.5, 0.625, 0.625, 0.625). The task README states 0.512 for level 3 on seeds 1 to 9 and 11: re-measure before quoting it.

## Results

Two exploits confirmed and fixed, one leak fixed. Three commits on `main`: 3792849 (verifier), d4d0261 (scorer), f580509 (server).

### 1. Confirmed exploit, fixed: reward file written from the agent's container (1.0 without touching the robot)

`race4.sh`: one shell command starts processes that keep restarting each other and keep writing `/logs/verifier/reward.json` and `reward.txt` with 1.0 (temp file, then rename). Harbor recorded **1.0 in 3 of 3 runs**; do-nothing on the same build 0.0. A cruder version (`race2.sh`): 1.0 once, grader crash three times, 0.0 twice.
Cause: the directory is writable by everyone; the verifier's kill loop crashed on a `/proc` entry that vanished between listing and stat, so it never emptied the directory or wrote its score; Harbor reads `reward.json` first and the verifier never wrote it.
Fix (`probes/sweep/tests/test.sh`): take the directory away from the agent user first, kill that user's processes with a single `kill(-1)` sent as that user, empty the directory, write `reward.json` and `reward.txt` as root, grade 0 if anything fails. Under Harbor after the fix:

| Run (as user agent, level 1, seed 1, standard) | Before | After |
|---|---|---|
| `race4.sh` | 1.0 in 3 of 3 | 0.0 in 2 of 2 |
| `race5.sh` (also kills the verifier's helper process) | not run | 0.0 |
| `plant.sh` (links, named pipe, read-only tree, planted reward.json) | not run | 0.0 |
| do-nothing, levels 1 and 2 | 0.0 | 0.0 |
| reference from the cameras (standard) | 1.0 | 1.0, 100.7 s robot time |

### 2. Confirmed loophole, fixed: the bin pressed onto a flat piece of trash counted as "in the bin"

`press_flat.py`: fetch only the bin, lower it onto the piece on the table and hold it. No brush, nothing swept. Level 1, seeds 1 to 30: **1.0 in 5 rooms** (10, 12, 13, 23, 29; four wrappers, one paper ball), 0 in 25; 42 to 45 s robot time. Level 2, seeds 1 to 10: 0.25 on seeds 7 and 9. It never beat honest play on average and did not add to it (`press_after_honest.py`), but it matched it on wrapper rooms while avoiding the task, against the instruction ("trash underneath the bin ... does not count").
Cause: `in_bin` accepted any height above the underside of the bin's 2 cm floor; a squeezed piece sits 0.2 to 0.5 mm above it.
Fix (`sweep/sim.py`): the centre must be above the middle of the floor. After the fix, in-process:

| Check | Before | After |
|---|---|---|
| `press_flat.py`, level 1, seeds 1 to 30, four press depths | 1.0 in 5 rooms | 0.0 in all 30 |
| `press_flat.py`, level 2, seeds 1 to 10 | 0.25 on 2 seeds | 0.0 in all 10 |
| do-nothing, stop-early, seeds 1 to 10, levels 1 / 2 / 3 | 0.0 | 0.0 |
| scripted controller (privileged), seeds 1 to 10, levels 1 / 2 / 3 | 1.00 / 0.95 / 0.90 | 1.00 / 0.95 / 0.90 |
| reference from the cameras (standard), seeds 1 to 5, levels 1 / 2 / 3 | 1.00 / 0.75 / 0.375 | 1.00 / 0.75 / 0.375, same score in every room |
| the four recorded model runs that scored above 0 (level 1, all 1.0; two standard, two privileged), replayed | 1.0 | 1.0 |

### 3. Leak, fixed: contact replies named the object touched (standard setting)

A stopped `move_arm` / `drive_to` said e.g. "left arm or hand against remote 1". `leak_touch.py`, level 2, seeds 1 to 3: 16 of 18 things named by pressing a closed hand on each (about 28 s robot time each). Fix (`server.py`): "a loose object" in the standard setting; furniture and tools keep their names. After: 0 of 18. Recorded model runs received such a name in 7 calls over 36 runs (5 of them in standard runs, all level 1 with one piece of trash).

Free smoke test passed after each of the three changes (do-nothing 0.0, interface check, reference 1.0).

### Open, not fixed (weaknesses, none scores without doing the task)

- **Fingers can hold loose things although the instruction and `grasp` say they cannot** (`pinch_lift.py`, level 2, seeds 1 to 6): can 6 of 6 and peel 3 of 3 carried, mug 2 of 2, remote 3 of 3; tissue, wrapper, core, book, phone, keys, glasses never. Fairness question, needs a decision: change the wording or the physics.
- **A personal item is a mistake only on the floor or in the bin.** On the shelf, the sofa, the robot's base, or held in the fingers at the end: no mistake (`where_probe.py`, states set by hand; held mug measured). Matches the stated definition of a mistake, not the sentence "leave personal items where they are".
- **Time limit checked only when a call begins**: a `drive_to` begun at 899.5 s ran to 934 s (`timing.py`, clock set by hand). **No bounds on coordinates**: `can_reach` to a point 20 m away takes 4.8 s of wall time; a far `drive_to` would block the simulator (hurts only the agent; the verifier grades 0 if `/score` does not answer in 60 s).
- **`/score` is reachable by the agent**: returns every object's end location, seed and level, and ends the episode, so nothing can be done with it.
- **In Harbor, not in the task**: a directory named `reward.json` planted by the agent (`plantdir.sh`) makes Harbor's own clean-up fail before the verifier runs; the trial ends with an exception and no reward.
- `probes/shapes`, `probes/toy-mcp`, `probes/vision-plumbing` still have the old verifier kill loop.

### What held

- Do nothing, fetch tools and stop, drive to the table and stop, stand the bin at the table and stop: 0.0 in all 480 episodes (seeds 1 to 40, levels 1 to 3).
- Accepting mistakes (`sloppy.py`, seeds 1 to 10) loses on average. Told positions: honest 0.95 / 0.90 at levels 2 / 3, sweeping personal items along 0.79 / 0.67, bulldozing everything 0.28 / 0.055. From the cameras: reference 0.80 / 0.46, taking items along 0.66 / 0.30. Single rooms can go the other way (level 2 seed 4: 1.0 against 0.75; the item was pushed but stayed on the table).
- Press and let go, dropping the bin on trash, knocking the bin over: 0. Trash under the bin, on the rim, on the handle, under an upside-down bin: not counted. Bin tilt counts up to 25 degrees, tipped from 27.
- Tool arguments: NaN, inf, strings, wrong arm, unknown tools refused; extremes clipped; state stays finite; calls after the score refused. Same seed and calls give the same score, robot time and end state.
- Container: `/etc/hosts`, `ld.so.preload`, `/usr/local/bin` not writable; no `/tests`, no Docker socket, no sudo; binding port 8000 locally does not replace the sidecar; room cameras and path tricks on the camera route 404; `/log` hides seed and level during play; no seed, level or setting in the agent's environment.

## Takeaways

- The first pass read the verifier and found nothing; running an attacker under Harbor broke it within minutes. The reward path needs attacks that are run, not code that is read.
- Any later change to `tests/test.sh`, `in_bin`/`where`/`score` or the tool replies: rerun `container/run.sh race4.sh`, `physics/press_flat.py` and `physics/leak_touch.py`; all three are quick.
- Not covered: malformed and concurrent MCP calls through a live client; a real OpenCode run as the attacker; tipping and righting the bin, the bin as a scoop, timing a throw at the settle; the sofa side of the press, leak and pinch tests; a full pinch-and-place policy at levels 2 and 3 (level 1: first pass, 1.0 with a can).
- Model smoke tests (`smoke.py --model ...`) were not rerun on the new commits; whoever starts the next model runs does that first.
