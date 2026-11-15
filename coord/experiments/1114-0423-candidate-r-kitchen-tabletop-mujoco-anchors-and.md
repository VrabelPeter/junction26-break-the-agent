---
title: Candidate R (kitchen tabletop, MuJoCo): anchors and first Kimi run
status: done
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-14T04:23+02:00
finished: 2026-11-14T04:46+02:00
commit: b9e73fc
command: sg docker -c '.venv/bin/harbor run -p probes/tabletop -a oracle|nop|opencode -m verda/kimi-k3-1-pro ... -o runs/tabletop' (TABLETOP_SEED=1)
headline: Tabletop level 1: no reliable gap. Kimi 0.875 / 1.0 / 0.875 vs reference about 0.9 to 1.0; nop 0, stop-early 0.19. One crushed object per imperfect run
---

## Hypothesis

First robotics probe: a two-finger gripper on a gantry over a cluttered table (tight 3x2 block of cans and bottles, fruit tucked against it and in a huddle). Put four fruit in the basket in a given order and serve one drink from the middle of the block upright on the coaster, without crushing, dropping, toppling or losing anything. Question: does a strong model fall short of the scripted geometric reference?

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

## Takeaways

## Setup

`probes/tabletop` (gantry gripper, level 1): a tight 3 x 2 block of cans and bottles, five fruit (two against the drinks, three in a huddle). Task: four named fruit into the basket in order, one drink from the middle column upright on the coaster. Score: 1 per fruit in the basket (+0.5 if in turn), 2 for the drink, half for anything dropped, minus 1 per object crushed, knocked over, off the table or wrongly in the basket; divided by 8. All under Harbor with local Docker; model runs are OpenCode with Kimi K3.1 Pro on Verda.

## Results

| Run | Seed 1 | Seed 2 | Seed 3 | Notes |
|---|---|---|---|---|
| `-a nop` | 0.0 | | | |
| stop-early (`-a oracle --ae TABLETOP_POLICY=stop_early`) | 0.188 | | | places one fruit, then stops |
| scripted reference (`-a oracle`) | 1.0 | 1.0 (in-process) | 0.69 to 1.0 (in-process, depends on the reference version) | about 60 to 105 s of robot time |
| OpenCode + Kimi K3.1 Pro | **0.875** | **1.0** | **0.875** | 57 to 70 tool calls, 4 to 6.5 min, about $0.40 to $0.60 each |

In-process over 24 seeds, level 1: do-nothing 0.00, stop-early 0.19, naive straight-down controller 0.11, reference 0.98 (before a later change that cost it seed 3).

Kimi's two imperfect runs each lost exactly one point to one crushed object:

- Seed 1: its very first descent, onto the juice bottle at yaw 0. Its reasoning checked the palm against the neighbouring cider bottle using the centre distance (0.0742 m) and forgot the bottle's radius; the palm is 0.075 m long each way. It then turned the gripper 90 degrees, moved the juice bottle out of the way, and did everything else correctly.
- Seed 3: crushed the banana.

Commands and score details for the three Kimi runs: `results/tabletop/kimi-seed*.{commands,details}.json`. Replay pages (not in git): `python probes/tabletop/viewer/replay.py results/tabletop/kimi-seed1.commands.json --seed 1 -o replay.html`.

## Takeaways

**At level 1 there is no reliable gap: Kimi averages 0.92, my reference between 0.90 and 1.0.** What the runs do show:

- The model plans correctly (moves a blocker aside before reaching into the block, picks a yaw that fits, carries high, sets things down gently) and reasons about clearances with explicit arithmetic.
- Its weakness is reliability, not understanding: about one geometric slip per episode, and with one attempt and real physics a slip is permanent.
- With linear partial credit a slip costs 12%. Scored as "flawless or not", two of three episodes fail while the reference fails about one in ten. How damage is scored decides whether this shows up as a gap, and has to be justified by the setting, not by the number we want.
- Still to try: level 2 (two drinks to serve, five fruit, more fruit against the drinks; reference 0.975 in-process), and the Franka Panda version, whose hand is much bulkier than the gantry gripper and should make clearance errors more likely.
- The reference needs hardening: it gives up on a blocked item in a few seeds.

