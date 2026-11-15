---
title: Probe A (orbital ops): anchors and first agent runs
status: done
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-14T03:46+02:00
finished: 2026-11-14T03:58+02:00
commit: 30dc7e4
command: .venv/bin/harbor run -p probes/orbital -a oracle|nop|opencode -e modal -o runs/orbital (see file)
headline: Probe A v1: NO gap. Kimi K3.1 Pro 2308 vs scripted reference 2056 (nop 0). Too easy; v2 adds learning from noisy delayed feedback
---

## Hypothesis

Throwaway version of candidate A (metered operations, delayed consequences, silent faults) as a Harbor task, seed 101. Scripted anchors in-process and under Harbor (oracle = reference operator, nop), then OpenCode with Kimi K3.1 Pro. Question: does a strong model fall short of the scripted reference, and where does it lose the points?

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

## Takeaways

## Setup

`probes/orbital` at commit of this file: 30 orbits, 5 operations per window, seed 101 (faults: attitude from orbit 4, comms from orbit 6; storm orbit 13; passes 23 and 24 cancelled; eclipse 13 to 18). Score = science value downlinked / par, where par is 1.1 times what the scripted reference earns on the seed.

## Results

In-process, 24 held-out seeds (101 to 124), `cd probes/orbital/environment/env-server && python3 -m orbital.run --seeds ...`:

| Operator | Mean value | Score |
|---|---|---|
| do nothing / attends but never acts | 0 | 0.00 |
| stop after 5 orbits | 334 | about 0.15 |
| greedy, never checks health or mail | 1059 | about 0.45 |
| checklist clerk | 1464 | about 0.74 |
| scripted reference | 1882 | 0.91 |

Under Harbor on Modal, seed 101:

| Run | Reward | Notes |
|---|---|---|
| `-a oracle` (scripted reference through MCP) | 0.9091 | value 2056, 1 min wall |
| `-a nop` | 0.0 | |
| `-a opencode -m verda/kimi-k3-1-pro` | **1.0 (clipped)** | value **2308**, 12% above the reference; 173 tool calls, 6 min of agent time, 3.7M input tokens (98% cached), 6.4k output tokens, about $0.92 |

Replay of the Kimi run: `results/probes/orbital-v1-kimi-1.txt` (made with `python3 probes/orbital/analyze.py results/probes/orbital-v1-kimi-1.commands.json --seed 101`).

## Takeaways

**No gap. Version 1 of probe A is too easy, and its reference is too weak.** This is the result that matters for `choose-setting`.

- Kimi attended all 30 windows, stowed for the storm, booked every pass two orbits ahead, took two observations in almost every orbit (56 against the reference's 48), and fixed both faults early. Its only losses were two downlinks skipped for lack of power in eclipse.
- It ran all four maintenance actions without looking first. Maintenance on a healthy subsystem costs one operation and nothing else, so blanket maintenance is cheap insurance: a loophole in the rules.
- With 5 operations per window, plentiful energy and plentiful downlink, "take the two best targets, book every pass, glance at telemetry" is close to optimal. Nothing forces a hard trade-off, so there is nothing for the agent to get wrong.
- Metered operations, silent faults and announced events on their own do not stop a strong model. What the next version adds: something that has to be learned from noisy, delayed feedback (which instrument mode suits which target class), remedies that cost something so they cannot be applied blindly, energy mistakes that hurt (brown-out instead of a polite skip), and fewer operations.

Note, 14 Nov: the orbital probe code (`probes/orbital`, `probes/orbital2`) was removed from the tree at Peter's request after the change to a robotics environment. It is in git history; the last commit that contains it is `a1ac3bc` (`git checkout a1ac3bc -- probes/orbital probes/orbital2` brings it back).
