---
title: Tabletop with the Franka Panda arm: reference and Kimi, levels 1 and 2
status: done
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-14T05:14+02:00
finished: 2026-11-14T06:10+02:00
commit: f1a7f08
command: TABLETOP_SEED=<s> TABLETOP_LEVEL=<l> sg docker -c '.venv/bin/harbor run -p probes/tabletop -a opencode -m verda/kimi-k3-1-pro --base-url https://inference.verda.com/v1 --api-key-name VERDA_API_KEY --api-format openai_chat_completions --env-file .env -o runs/panda'
headline: Panda tabletop, clean env, level 2: NO gap. Kimi 1.0 / 1.0 / 1.0 (flawless), reference 1.0 x3, nop 0, stop-early 0.14
reference: 1.0
agent: [1.0, 1.0, 1.0]
noop: 0.0
stop_early: 0.143
---

## Hypothesis

The tabletop task with a real arm model (Franka Panda from MuJoCo Menagerie, its own hand and collision meshes, inverse kinematics). The hand is much bulkier than the earlier gantry gripper: a 21 cm housing 4 cm above the fingertips, so far more picks need the right yaw or a blocker moved first. Question: does that widen the gap between Kimi K3.1 Pro and the scripted reference? Level 1 = four fruit, one drink; level 2 = five fruit, two drinks.

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

## Takeaways

## Setup

`probes/tabletop` at commit `a780712` or later: Franka Panda (Menagerie) with its own hand, tools unchanged. Score is now `progress x care`: share of the order delivered, halved for every damaged object. Level 2: all five fruit into the basket in order, both middle-column drinks onto coasters A and B.

Getting to a clean environment took most of the night. Bugs found and fixed before the runs below, each of which would have been an unfair cause of agent failure:

- The workspace first documented was not reachable (front corners at height). Reach is now measured and enforced: 0.80 from the base up to z = 0.2, 0.04 less per 0.1 above.
- Some yaws were unreachable because the last joint hit its stop; `move_to` reported `reached: false` and in one run the half-finished turn knocked a bottle over. Yaw is now taken modulo half a turn and each move is rehearsed kinematically to pick the turn direction that stays off the stop.
- The arm sagged 2 to 3 mm and held yaw 0.03 rad off: a slow integral term now brings it within 2 mm and 0.01 rad on 60 random reachable poses.
- The grasp test missed thin objects (only one finger registered a contact).
- Bottles were tall enough to be hit by the wrist, whose position depends on the arm's posture and cannot be predicted from the tool interface. Bottles are now 0.145 tall, below the wrist at any gripper height.

**Runs before these fixes (Kimi level 1 seeds 1 to 3, level 2 seeds 1, 2, 6) are invalid and not reported**: their trajectories contain 7 to 14 spurious `reached: false` replies each.

## Results

In-process, scripted controllers, after the fixes:

| Level | do-nothing | stop-early | naive straight-down | reference |
|---|---|---|---|---|
| 1 (16 seeds) | 0.00 | 0.18 | 0.01 | 0.973, 15 of 16 flawless, no damage |
| 2 (12 seeds) | 0.00 | 0.14 | 0.02 | 0.964, 10 of 12 flawless, no damage |

Under Harbor, local Docker, level 2 (`python3 eval/run_eval.py --skip-agent`, result in `results/eval-1114-0552.json`): reference 1.0 / 1.0 / 1.0 on seeds 1, 2, 4; do-nothing 0.0; stop-early 0.13 to 0.15.

OpenCode + Kimi K3.1 Pro (Verda), level 2, fixed environment:

| Seed | Score | Damaged | Tool calls | Robot time | Agent time | Cost |
|---|---|---|---|---|---|---|
| 1 | **1.0** | 0 | 63 | 66 s | 9 min | about $0.75 |
| 2 | **1.0** | 0 | 58 | 48 s | 4.5 min | about $0.42 |
| 4 | **1.0** | 0 | 52 | 44 s | 5.5 min | about $0.44 |

Commands and details: `results/panda/kimi-l2-seed*.json`.

## Takeaways

**No gap: on the clean Panda environment Kimi is flawless on all three level-2 seeds, and faster than the reference.**

- The real Panda hand made the task easier, not harder. Its fingers are 4 cm long, so everything is gripped at the top; a can is lifted out of a tight block without the fingers ever going down between its neighbours. Packing the drinks three times tighter does not change the number of blockers the reference has to move.
- What made the earlier gantry version produce slips (one crushed object in two of three Kimi runs) was its 7 cm fingers reaching down between objects, with a palm above them.
- Next attempt on the real arm: fingertip extensions (long thin fingers, common on real Pandas) plus the physical rule that a drink has to be gripped at or below its centre of mass. That brings back the deep-reach geometry.

