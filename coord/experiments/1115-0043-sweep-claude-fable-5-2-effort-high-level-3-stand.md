---
title: Sweep: Claude Fable 5.2 (effort high), level 3, standard, seed 1
status: failed
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-15T00:45+02:00
finished: 2026-11-15T00:58+02:00
commit: 68f54b6
command: python3 probes/sweep/run_agent.py --model fable --setting standard --level 3 --seeds 1
headline: Claude Fable 5.2 (effort high), level 3, standard (cameras), seed 1 - stopped by us at 12.6 min before Peter left the venue (laptop going offline), still planning; 0.0, not a result
---

## Hypothesis

A second frontier family next to GPT-6 Astra. Astra solved level 1 in both settings and scored 0.25 at level 2 (cut off), so the gap has to show at level 2 or 3. The camera reference scores 0.5 on this room (level 3, seed 1, standard, in-process, measured 15 Nov 00:40).

## Setup

- Model: `anthropic/claude-fable-5-2` through OpenCode 1.19.5 under Harbor (local Docker), `--ak variant=high` (adaptive thinking, effort high). Key `ANTHROPIC_API_KEY` from `.env`.
- Setting: **standard** (cameras: colour, depth, calibration, joint readings). Level 3, seed 1.
- Build: main at 68f54b6 (after the verifier race fix and the merge of the `fable` model entry). Smoke test with `--model fable` passed before the run (runs/sweep/smoke-0032).

## Results

**Failed: not a run that counts.** We stopped the agent at 12.6 min of wall time (killed OpenCode in the agent container, so Harbor still graded): Peter had to leave the venue and the laptop that runs the containers would have been offline for about 30 min, which would have broken the run anyway.

- Score 0.0, trash in bin 0, no mistakes, robot time 12.7 of 900 s, 1393 tool calls, `error: agent cut off, not a clean run (NonZeroAgentExitCodeError)`.
- Cost about 2.33 USD (731K cached tokens read, 70K written, 37K output incl. thinking, 42 uncached input).
- Trial: `runs/sweep/peter-fable-standard-l3-s1-1115-0045/2026-11-15__00-45-52/sweep__xt37Bk2` (local, peter's laptop). Summary: `results/sweep/agent-runs/peter-fable-standard-l3-s1-1115-0045.summary.json` (not committed yet).

What it did before the stop (from the simulator log and `agent/opencode.txt`):
- Looked first: head camera pictures, downloaded depth and calibration, wrote its own scipy segmentation of the depth image, cropped and zoomed parts of the picture to inspect them.
- One `drive_to` and a few `look` calls; no grasp.
- Long thinking turns: one step thought for about 2 min 40 s (00:47:36 to 00:50:19) with no event in the log meanwhile.
- Then wrote a Python client (`rb.py`, fastmcp) that calls the MCP tools directly, and made about 1360 `can_reach` calls in a grid to map where the left arm can reach from the base pose. `can_reach` costs no robot time, so the robot clock stayed at 7.5 s while it did this.

## Takeaways

- Wiring works end to end: pictures reach Fable, it acts, cost is low thanks to caching (about 0.18 USD per minute here).
- At effort high Fable plans for a long time before acting; the binding limit is likely the 1-hour wall-clock agent timeout, not the 900 s of robot time. Rerun in one sitting with a stable connection.
- For the failure analysis: bulk free `can_reach` queries from the agent's own code are within the tools the instruction gives it (not an exploit), but they are a choice worth describing.
- The stop command in an earlier note used the pattern `opencode run`, which does not match (the process line is `opencode --model=... run ...`). Working one: `docker exec <sweep__...-main-1> bash -c 'for p in /proc/[0-9]*; do tr "\0" " " < $p/cmdline 2>/dev/null | grep -q "[o]pencode --model" && kill ${p#/proc/}; done'`.
- Next: rerun the same command (level 3, seed 1) when Peter is back.
