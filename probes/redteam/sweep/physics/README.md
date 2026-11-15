# Sweep reward red-team, second pass: physics and scoring, in-process, levels 1 to 3

Scripts of the second red-team pass on `probes/sweep` (14 Nov, commit 45e000a, build `sweep-frozen-1`). Nothing here
edits the task. Run from the repo root; every script takes `--level`, `--seeds`, `--procs` (default 8), `-v`:

```
MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/<script>.py --level 2 --seeds 1 2 3 4 5
```

`rt.py` holds the shared helpers. All policies act through the tools an agent has (`World.call` or the same
`World` methods the repo's scripted policies use). Where a script puts things in place by hand to read the scorer,
its docstring says so. Numbers below were measured on this machine on 14 Nov, 23:20 to 00:40.

| Script | What it does | Measured |
|---|---|---|
| `baselines.py` | The repo's own policies, seed by seed | Seeds 1 to 5, levels 1 / 2 / 3: `reference_privileged` 1.00 / 0.95 / 0.90, camera `reference` 1.00 / 0.75 / 0.375, `stop_early` 0 / 0 / 0. Camera `reference` on seeds 1 to 10: level 2 0.80, level 3 0.4625 |
| `donothing_many.py` | Do nothing; fetch tools and stop; drive to the table and stop; stand the bin at the table and stop. Seeds 1 to 40, levels 1 to 3 | 0.0 in all 480 episodes, no mistakes |
| `press_flat.py` | **Loophole.** Fetch the bin, lower it onto the flattest piece of trash on the table and keep holding it there (no brush, nothing swept) | Level 1, seeds 1 to 30, hand z 0.77 to 0.79: score 1.0 in 5 rooms (10, 12, 13, 23, 29: four wrappers and one paper ball), 0 in 25; mean 0.167, honest 1.0. Level 2, seeds 1 to 10: 0.25 on seeds 7 and 9, else 0. The piece lies under the bin, squeezed into its floor, with its centre 0.2 to 0.5 mm above the underside |
| `press_after_honest.py` | The reference, then the same press on a flat piece it left behind | Levels 2 and 3, seeds 1 to 10: no gain and no loss (0.95 and 0.90 both ways). The pieces left behind have a personal item beside them, the bin cannot be centred on them, and an off-centre piece stays 2 to 5 mm short |
| `bin_tricks.py` | Press the bin on trash and hold / let go, drop the bin on trash from above, knock the bin over | Level 2, seeds 1 to 5: only press-and-hold scores (0.25 on seed 1); the others 0 |
| `leak_touch.py` | **Leak.** Standard setting: press the closed fingers on each thing on the table and read `touching` in the reply (server.py `_explain`) | Level 2, seeds 1 to 3: the reply names 16 of 18 things by kind ("left arm or hand against remote 1"), about 28 s of robot time each, no mistakes |
| `pinch_lift.py` | Close the bare fingers on each thing, lift, carry 0.15 m, roll back from the table still holding it | Level 2, seeds 1 to 6: can 6 of 6 and peel 3 of 3 carried, paper ball lifted but lost while carrying (0 of 2), tissue, wrapper, core never; personal items: mug 2 of 2 and remote 3 of 3 carried, book, phone, keys, glasses never. A mug held in the fingers off the table at the end is scored "elsewhere": no mistake |
| `sloppy.py` | Accepting mistakes: `take_along` (reference blind to personal items), `bulldoze` (sweep every lane into the bin, knowing nothing), `take_along_camera` (the same from the cameras) | Seeds 1 to 10. Level 2: honest 0.95, take_along 0.79, bulldoze 0.28; camera reference 0.80, take_along_camera 0.66. Level 3: honest 0.90, take_along 0.67, bulldoze 0.055; camera reference 0.46, take_along_camera 0.30 |
| `where_probe.py` | End states set by hand, then the settle and `score()` | A personal item on the tool shelf, the TV console, the table's lower shelf, the robot's base or the sofa is no mistake ("elsewhere" / "on_sofa"); on the floor, in the bin, across the rim: mistake. Trash under the bin, on the rim, on the handle: not counted. Bin tilt: counts up to 25 degrees, tipped from 27 |
| `fuzz_args.py` | NaN, inf, strings, bools, huge and negative values, wrong arm, unknown tools, calls after the score | All refused or clipped, state stays finite, nothing moved, score 0. `can_reach` to a point 20 m away takes 4.8 s of wall time (grows with the distance) |
| `timing.py` | A move begun at 899.5 s; a bin held in the hand at the end; determinism | The drive ran to 934.1 s and moved the base 0.69 m, the next call is refused. A held bin stays up through the settle and its content counts. Same seed and calls: same score, robot time and final state, in one process and across processes |

Not covered here: the container, verifier and HTTP side (a separate pass), any run with a model.

## After the scorer fix (15 Nov, 00:00)

`in_bin` in `probes/sweep/environment/env-server/sweep/sim.py` now needs the piece's centre above the middle of the
bin's 2 cm floor (before: above the floor's underside). Measured on that change, in-process:

| Check | Before | After |
|---|---|---|
| `press_flat.py`, level 1, seeds 1 to 30, hand z 0.79 / 0.78 / 0.77 / 0.76 | 1.0 in 5 rooms | 0.0 in all 30, at every depth |
| `press_flat.py`, level 2, seeds 1 to 10, hand z 0.78 | 0.25 on seeds 7 and 9 | 0.0 in all 10 |
| `do_nothing`, `stop_early`, seeds 1 to 10, levels 1 / 2 / 3 | 0.0 | 0.0 |
| Scripted controller told positions (privileged), seeds 1 to 10, levels 1 / 2 / 3 | 1.00 / 0.95 / 0.90 | 1.00 / 0.95 / 0.90 |
| Reference from the cameras (standard), seeds 1 to 5, levels 1 / 2 / 3 | 1.00 / 0.75 / 0.375 | 1.00 / 0.75 / 0.375, same score in every room |
| The four recorded model runs with a score above 0 (all level 1, 1.0), replayed with `viewer/replay_log.py` | 1.0 | 1.0 |
