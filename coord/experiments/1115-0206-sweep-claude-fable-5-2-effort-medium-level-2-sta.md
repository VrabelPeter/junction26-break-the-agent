---
title: Sweep: Claude Fable 5.2 (effort medium), level 2, standard, seeds 1 2 3
status: done
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-15T02:07+02:00
finished: 2026-11-15T02:26+02:00
commit: ebd6f6a
command: python3 probes/sweep/run_agent.py --model fable --setting standard --level 2 --seeds 1 2 3 --parallel 3   (with "variant": "medium" in probes/sweep/models.json, see Setup)
headline: Claude Fable 5.2 (effort medium), level 2, standard (cameras) - 1.0 on all three seeds, clean, no mistakes, 10 to 18 min and 3 to 5 USD each; the camera reference scores 0.5 / 0.75 / 1.0 on the same rooms. No gap at level 2: Fable beats the reference
---

## Hypothesis

Compare a second frontier family with GPT-6 Astra on the same rooms (level 2, seeds 1 2 3, standard setting). Astra scored 0.25 (stopped), 1.0 and 0.75 (stopped) there (experiments 1114-2303 and 1115-0048), against a camera reference of 0.5 / 0.75 / 1.0. Question: is level 2 a gap for the strongest models?

## Setup

- Model: `anthropic/claude-fable-5-2` through OpenCode 1.19.5 under Harbor, local Docker, three runs side by side. **Effort medium** (`--ak variant=medium`, adaptive thinking): confirmed in each trial's `config.json` and in the OpenCode command line (`--variant medium`). Not the "high" the `fable` entry on main says, and not the Embodied First Exam's "high reasoning effort": Peter switched it to medium in his checkout before this run to save cost after an unexplained 30 USD on the key (see 1115-0043). That edit was not committed, which is why the summaries say `commit: d7e0cb9+uncommitted`; `probes/sweep/models.json` is the only file under `probes/sweep` that differed from d7e0cb9 at run time (checked file by file). **To reproduce, set `"variant": "medium"` in the `fable` entry first.**
- Setting: **standard** (cameras: colour, depth, calibration, joint readings). Level 2, seeds 1 2 3.
- Build: main (d7e0cb9 at run time, after the verifier race fix). Astra's level 2 runs were on the older frozen build `sweep-frozen-1` (task copy, 3564f98). Differences that reach the agent: collision messages now say "a loose object" instead of naming trash in the standard setting, and `/log` no longer gives the seed to the agent. Scoring: the "in the bin" test is stricter (a piece pressed under the bin no longer counts). None makes the task easier on main.
- Reference: camera reference (standard), in-process on main, measured 15 Nov about 02:00: `python -m sweep.run --policy reference --seeds 1 2 3 --level 2` -> 0.5, 0.75, 1.0 (mean 0.75).

## Results

| Level 2, standard | Seed 1 | Seed 2 | Seed 3 | Mean |
|---|---|---|---|---|
| Reference (cameras, in-process, main) | 0.5 | 0.75 | 1.0 | 0.75 |
| GPT-6 Astra (frozen1 build) | 0.25, stopped by us at 8.1 min | 1.0 clean | 0.75, stopped by us at 15.4 min | 0.67 (two runs cut off) |
| **Claude Fable 5.2, effort medium (main)** | **1.0 clean** | **1.0 clean** | **1.0 clean** | **1.0** |

Per Fable run (all ended by themselves: the model judged the job done and stopped; no errors):

| Seed | Score | Trash in bin | Mistakes | Robot time | Wall time | Simulator calls | Model steps | Thinking (longest / total) | Cost |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 1.0 | 4 of 4 | none | 194 s | 10.3 min | 678 (450 can_reach) | 52 | 52 s / 344 s | 2.91 USD |
| 2 | 1.0 | 4 of 4 | none | 208 s | 18.1 min | 1168 (930 can_reach) | 80 | 107 s / 546 s | 5.03 USD |
| 3 | 1.0 | 4 of 4 | none | 122 s | 11.6 min | 1458 (1320 can_reach) | 51 | 72 s / 367 s | 3.12 USD |

Milestones (robot time): seed 1 brush 37 s, bin 48 s, first trash in bin 86 s, all in 153 s; seed 2 brush 11 s, bin 17 s, first 88 s, all 176 s; seed 3 bin 56 s, brush 59 s, first 86 s, all 112 s.

Total cost 11.06 USD (prices: 8 / 0.2 cached / 40 / 10 cache write per million tokens; nearly all input was read from cache, 2.7M to 6.5M cached tokens per run).

Summaries, details and commands: `results/sweep/agent-runs/peter-fable-standard-l2-s{1,2,3}-1115-0207.*`. Trials (local, peter's laptop): `runs/sweep/peter-fable-standard-l2-s{1,2,3}-1115-0207/`.

How it played (from the trajectories):
- It drives the robot mostly from its own Python: a small fastmcp client run through `bash` (33 to 46 bash calls per run), not the MCP tools one by one.
- It maps reach before moving: 450 to 1320 `can_reach` calls per run, which cost no robot time.
- It segments the depth image itself (100+ `camera_file` downloads on seeds 1 and 2) and checks results with wrist-camera pictures looking straight down into the bin.
- It ends with a self-check and a report ("All four pieces of trash are in the bin, the bin is standing upright, and both personal items are still on the table, so the expected score is 1.0"), and it stops with most of the robot time unused (seed 3: 778 s left).

## Takeaways

- **Level 2 is no gap for Fable 5.2, even at medium effort**: 1.0 on all three rooms, above the camera reference's 0.75 mean. Together with Astra (no consistent gap at level 2), the gap claim cannot rest on level 2 for current frontier models.
- The reference is the weak side here: on seed 1 it scores 0.5 where Fable scores 1.0. For the rubric the reference has to beat the frontier agent, so either the reference gets stronger (it has the same tools; Fable shows what the tools allow) or the headline moves to level 3, where the reference is also weak (0.5 on seed 1).
- Fable at medium effort is fast and cheap enough for many runs (3 to 5 USD, 10 to 18 min). The earlier 30 USD on the key is not explained by these runs: by the API's own token counts every Fable run so far cost 2.3 to 5 USD.
- Effort medium differs from the Embodied First Exam's "high"; say so whenever these numbers are quoted.
- Next: Fable at level 3 (seed 1 first; the high-effort attempt in 1115-0043 was stopped while planning), and commit the `variant` choice so the command on main reproduces these runs.
