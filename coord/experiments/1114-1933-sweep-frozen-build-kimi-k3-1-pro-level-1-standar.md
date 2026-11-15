---
title: Sweep, frozen build: Kimi K3.1 Pro, level 1, standard seeds 1 2 3 and privileged seed 1
status: done
kind: eval
owner: frederik
host: fls
started: 2026-11-14T19:33+01:00
finished: 2026-11-14T20:14+01:00
commit: 9678971
command: python3 probes/sweep/run_agent.py --model kimi --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1 ; python3 probes/sweep/run_agent.py --model kimi --level 1 --setting privileged --seeds 1 --tag frozen1
headline: Kimi on the frozen build, level 1: privileged seed 1 scores 1.0 (clean); standard seeds 1 2 3 score 0.0 each but were stopped by us at 40 min (trash already on the floor in all three), so they are not clean runs
reference:
agent: [0.0, 0.0, 0.0]
noop:
stop_early:
---

## Hypothesis

On the frozen build, OpenCode + Kimi K3.1 Pro scores clearly below the camera reference (1.0 under Harbor, experiment 1114-1835) at level 1 in the standard setting, and better when it is told where things are (privileged). Same seeds and settings as Peter's Nemotron set (1114-1938).

## Setup

Task files identical to tag `sweep-frozen-1` (commit at start 99765b9+; the only differences in `probes/sweep` were a viewer page and the summary logic of `run_agent.py`). Local Docker on frederik's machine, four runs side by side. Kimi smoke test passed on this build and machine at 18:46. Model `verda/kimi-k3-1-pro`, context limit 96000 declared.

    python3 probes/sweep/run_agent.py --model kimi --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1
    python3 probes/sweep/run_agent.py --model kimi --level 1 --setting privileged --seeds 1 --tag frozen1

## Results

| Run | Setting | Seed | Score | Trash in bin | Mistakes | Milestones (robot s) | Calls | Robot time | Wall | Cost USD | How it ended |
|---|---|---|---|---|---|---|---|---|---|---|---|
| frederik-kimi-privileged-l1-s1-1114-1934-frozen1 | privileged | 1 | **1.0** | 1 of 1 | none | bin 8.9, brush 63.0, touched 153.6, in bin 158.5 | 121 | 166.5 s | 14.3 min | 1.65 | clean: the agent stopped by itself |
| frederik-kimi-standard-l1-s1-1114-1933-frozen1 | standard | 1 | 0.0 | 0 of 1 | bin tipped over | brush 11.7, bin 20.5 | 351 | 330.7 s | 40.4 min | 4.73 | **stopped by us** |
| frederik-kimi-standard-l1-s2-1114-1933-frozen1 | standard | 2 | 0.0 | 0 of 1 | none | brush 10.6, bin 18.5, touched 99.1 | 395 | 433.5 s | 40.4 min | 5.49 | **stopped by us** |
| frederik-kimi-standard-l1-s3-1114-1933-frozen1 | standard | 3 | 0.0 | 0 of 1 | none | brush 53.3, bin 57.3, touched 167.5 | 402 | 346.4 s | 40.4 min | 4.89 | **stopped by us** |

Total 16.76 USD.

**The three standard runs are not clean.** The human asked to stop them at 40 minutes; the OpenCode process was ended inside each agent container, Harbor recorded `NonZeroAgentExitCodeError`, and the verifier then scored the room as it stood (summaries carry `error: agent cut off`). 330 to 434 s of the 900 s robot time had been used.

State when stopped, and at a check 9 minutes earlier (live logs replayed in-process): in all three rooms the piece of trash already lay on the floor, where it earns nothing. Seed 1: apple core on the floor, never touched by the brush, bin on its side. Seed 2: can on the floor about 1 m from the upright bin, both hands empty. Seed 3: apple core on the floor 0.17 m from the upright bin. So the score could only have changed if the agent had got a piece from the floor into the bin.

Replaying each run's logged calls in-process gives the verifier's score and robot time in all four runs. Films (replays, a room camera for people plus the head camera): `runs/sweep/kimi-{privileged,standard}-level1-seed*.mp4` on frederik's machine, not committed.

Reference on the same level: 1.0 under Harbor, seed 1 (1114-1835). An earlier standard run on seed 1, also stopped by us with the core on the floor: 1114-1844.

## Takeaways

- With positions given, Kimi does level 1 (one seed, clean). With cameras only, in three rooms the trash left the table without reaching the bin. That points at working from the cameras as what separates success from failure at level 1, the opposite of the reading in 1114-1500 (which rested on runs before the arm fix).
- Evidence is thin on both sides: one privileged seed, and three standard runs that we cut off. For numbers that count, the standard runs need to end by themselves or by a limit that is part of the task. The agents kept working 25 minutes and more after the trash was lost; a rule that ends the episode when no trash is left on a surface would cut cost by most of that (proposal, not done).
- Why each standard run lost the piece (where the bin stood, what the agent saw) is for the trajectory analysis; the logs are in `results/sweep/agent-runs/`.
