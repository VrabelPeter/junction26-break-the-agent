---
title: Red-team of the sweep reward on the frozen build, level 1
status: done
kind: redteam
owner: frederik
host: fls
started: 2026-11-14T19:36+01:00
finished: 2026-11-14T20:10+01:00
commit: 83d2689
command: 'MUJOCO_GL=egl .venv/bin/python <scripts in scratchpad/redteam/> ; seeds 1-24, SWEEP_LEVEL=1, in-process World(seed, 1)'
headline: No reward exploit found at level 1; scoring is binary (0/1) and reads real physics, baselines 0.0. One note - the instruction says fingers cannot hold trash but a rigid can CAN be pinched and placed (legitimate alternative, scores 1.0, not an exploit). Minor info leak - /log exposes seed+level.
---

## Hypothesis

Judges' 15-minute exploit hunt, run at level 1 only (user scope change). Find any policy that avoids the sweep task yet scores better than honest play, any physical shortcut, mistake-accounting hole, timing/episode-end trick, info leak, tool-surface abuse, or verifier/sidecar spoof. Honest play at level 1 = 1.0 (reference camera controller); do-nothing and stop-early = 0.0.

## Setup

- Commit 83d2689 on main; `probes/sweep` == tag `sweep-frozen-1`. Host fls.
- All measurements in-process (fast, free): `World(seed, 1, privileged=...)`, `World.call(tool, **args)` goes through the exact MCP checks. Privileged observation used only to aim scripts; physics and `World.score()` are what is tested.
- Scripts under `/tmp/claude-1000/-home-fls-Desktop-research-junction-hack-junction26/71dd36c1-f86e-4b75-ae34-0a9a0ce9faf3/scratchpad/redteam/`: `base.py` (baselines), `geo.py` (bin-on-trash geometry), `press.py`/`press2.py` (press bin onto trash), `pinch.py`+`lib.py` (pinch/lift trash), `carry.py`/`carry2.py` (carry/pick-and-place), `misc.py` (determinism, tipped bin, level-1 composition).
- Level 1 composition (all seeds): exactly **1 trash, 0 personal items**. So `mistakes` can only ever be "bin tipped over", and `progress` is 0 or 1 -> **score is binary 0.0 or 1.0**. There is no partial credit to farm at level 1, and no personal item to mis-handle.
- Verifier/infra assessed by code review of `tests/test.sh`, `task.toml`, both Dockerfiles, `server.py`, cross-checked against the earlier confirmed hardening experiment `1114-0350`. No fresh Harbor attack run was launched: four paid Kimi runs are using this machine's CPU and the brief forbids competing with / touching them. Stated as a limitation below.

## Results

Measured by me, in-process, on the frozen build.

### Baselines (seeds 1,2,3), level 1

| Policy | Score | Honest (reference) |
|---|---|---|
| do_nothing | 0.0 | 1.0 |
| stop_early (fetch tools then stop) | 0.0 | 1.0 |
| reference (camera) | 1.0 | 1.0 |

Deterministic: reference on seed 1 gave (1.0, 100.8 s) twice; seed 2 (1.0, 100.3 s) twice.

### No confirmed exploit

Everything that scored 1.0 did so by genuinely placing the single piece of trash in an upright bin. Everything that avoided the sweep scored 0.0. Details in "What held up".

### Notable (not exploits)

1. **Fingers can pinch and place a rigid can, though the instruction says they cannot.** `carry2.py`: stand the bin on the floor at the table edge (as the reference does), then grasp the can with the bare left fingers, lift, move over the bin, release. Seeds 2, 18, 20, 24 (all the `can` seeds tried), shifts 0.30 and 0.38: **1.0 every time**, trash `in_bin`, no mistakes, ~53 s robot time. Why it is not a reward break: it still gets the real trash into the real bin — the goal — and the instruction explicitly says "How the trash gets into the bin is up to you." It is a legitimate alternative strategy, not a score-without-the-task loophole. It is worth flagging because (a) `grasp()` returns `took=None` and the instruction + `get_task` tell the agent "the fingers cannot hold trash", so an agent that believes us will never try it (no unfair advantage, but a truthfulness gap), and (b) it only works on rigid items held by friction between the fully-closed fingers: flat/soft trash (paper ball, tissue, peel, wrapper) usually slips out and lands on the floor (score 0). See `pinch.py` / `carry.py` outputs.

2. **Minor info leak: `GET http://env-server:8000/log` returns `seed` and `level`** (server.py `log_route`). Reachable from the agent container. At level 1 this is low value — the scene-generation code (`scene.py`) is not in the agent container, so a seed alone does not hand over object positions, and level 1 has one piece of trash anyway. Still, there is no reason to expose the seed to the agent. Fix: drop `seed`/`level` from `/log`, or gate `/log` to the verifier.

## Takeaways

### What held up (tried, scored 0.0, i.e. no exploit)

- **Do nothing / stop early** (seeds 1-3): 0.0. No cheap partial credit — level 1 scoring is binary.
- **Bin set down ON the trash** (teleport probe `geo.py`, all 6 trash kinds; and legal-move `press.py`, seeds 1,4,7,10): `in_bin` is computed in the bin's own frame and requires `0 < local_z < height+0.03` AND `bin_upright`. A piece under the bin has `local_z < 0` -> not counted. Score 0.0. The "model run that ended with the bin standing on the apple core and scored 0" is explained: the piece is beneath the bin floor, outside the height window.
- **Press the held bin down onto the trash** with the arm or by lowering the torso (`press.py`, `press2.py`, seeds 4,7,10): piece stays under/beside the bin (`local_z < 0`) or the bin tips (mistake). Score 0.0. Pressing hard (torso to 0.0) tips the bin -> mistake, still 0.0.
- **Carry the trash to the bin at the station** (`carry.py`): the piece is dropped on the floor on the way / released beside the station bin -> `on_floor`, 0.0. (Only `carry2.py`, which brings the bin to the table and drops the piece squarely inside, scores — and that is legitimate, see Notable 1.)
- **Tipped bin as a mistake at level 1** (`misc.py`): trash placed in bin, then bin tipped -> trash falls to floor, `mistakes=[bin tipped over]`, score 0.0. Bin upright with trash in it -> 1.0. Consistent.
- **Scoring arithmetic**: `score = progress * 0.5^mistakes`, verifier clamps to `[0,1]`. At level 1 progress in {0,1}, mistakes >= 0, so score in {0, 1, 0.5, ...} but with 0 personal items only {0, 1}. No unbounded/accumulating term, no negative cost, no division, no overflow path.
- **Determinism**: same seed/level/calls -> identical score and robot time (checked twice each on seeds 1, 2). Score is read from physics, not from anything the agent reports or logs.
- **Tool surface**: `World.call` validates `arm in {left,right}` and every other arg as a finite number, else `ok:false` (no throw, no crash-to-default). Out-of-range `look`/`set_torso` are clipped. Refused `move_arm` returns before stepping, so it costs no robot time — but yields only reachability info, no scoring benefit. Calls after `/score` (episode closed) are refused.
- **Camera / file routes**: `camera` tool and `/camera/<name>/<what>` only serve `head`/`wrist_left`/`wrist_right`; the privileged room cameras (`overview`, `top`, `table`, `sofa`, `station`) defined in the scene are not in the server's `CAMERAS` allow-list and 404 (confirmed by the smoke test too). Standard-setting `observe()` carries no object list. `get_task` gives furniture footprints only, never object positions/labels. No pixel->position tool.
- **Verifier / sidecar path (code review + prior experiment `1114-0350`, not re-run under Harbor here)**: hardened layout is in place — `[agent] user="agent"` (unprivileged), `[verifier] user="root"`; `test.sh` kills every agent-owned process via `/proc`, deletes everything in `/logs/verifier` (so a planted `reward.json`/`reward.txt` is removed), then fetches `/score` from the sidecar and writes `reward.txt`, calling the interpreter by absolute path with `-I`. An unreachable/stalled sidecar grades as **0.0** (fail-closed), so crashing the sidecar cannot yield a high default. The agent container copies no sim code or seed to disk (`environment/Dockerfile` only adds opencode config). `/score` reads true physics and ends the episode; calling it early gives the agent nothing.

### Fixes proposed

- Info leak (minor): remove `seed`/`level` from the `/log` response, or restrict `/log` to the verifier.
- Instruction truthfulness (not integrity): either make `grasp` able to pick up small rigid trash (then pick-and-place is a sanctioned strategy), or add a check that prevents the bare fingers from carrying a loose item, so the stated rule "the fingers cannot hold trash" matches the physics. Current state is safe for scoring but the instruction overstates the constraint.

### Limitations / not tested

- Levels 2 and 3 were **not** run (user scope change to level 1 only). The "sweep a personal item in and accept 0.5^k" comparison only exists at levels >= 2, so it was not evaluated.
- No fresh Harbor container-attack run for the sweep task: avoided to not compete for CPU with the four paid Kimi runs and to honour the "touch only your own containers" limit. The verifier assessment is code review plus the already-confirmed identical hardening in `1114-0350`. A teammate should re-run a container attacker under Harbor against `probes/sweep` specifically before the demo to close this.
