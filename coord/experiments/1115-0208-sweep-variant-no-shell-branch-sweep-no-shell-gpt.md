---
title: Sweep variant no-shell (branch sweep-no-shell): GPT-6 Astra, level 1, standard, seed 1, agent without shell or code
status: done
kind: probe
owner: frederik
host: fls
started: 2026-11-15T02:08+01:00
finished: 2026-11-15T02:21+01:00
commit: fd61c11 (branch sweep-no-shell)
command: (on branch sweep-no-shell) python3 probes/sweep/run_agent.py --model astra --level 1 --seeds 1 --tag noshell
headline: Variant without shell or code - GPT-6 Astra, level 1, cameras, seed 1 - 0.0 when stopped by us at 11 min (trash swept onto the floor; brush and bin taken). With a shell the same model scored 1.0 on this room in 7.8 min
---

## Hypothesis

Without a shell (no code, no depth file), GPT-6 Astra scores lower at level 1 than with one (1.0 on seed 1, 1114-2242).

## Setup

Branch `sweep-no-shell`, commit fd61c11. Differences from the frozen task:

- `environment/opencode-models.json` carries `"permission": {"bash": "deny"}` (written by `models.py: opencode_config`); OpenCode 1.19.5 then does not offer the shell tool at all.
- `instruction.md` no longer mentions Python, a shell, `curl` or downloadable files; it says the grey depth picture is all the depth there is. The pixel-to-point formula stays.
- The `camera` tool's description and reply no longer name the depth download.
- `smoke.py`'s model stage no longer asks for the depth download and fails if a shell is used.
- GPT-6 Astra added to `models.json` (OpenCode's own OpenAI provider).

The simulator's HTTP routes are unchanged, so the scripted reference still computes on the depth file. This is an ablation, not a candidate for the submitted task: the agent has less than the reference.

    python3 probes/sweep/smoke.py --model astra
    python3 probes/sweep/run_agent.py --model astra --level 1 --seeds 1 --tag noshell

**Smoke test passed on the branch** (do-nothing 0.0, interface, scripted reference 1.0, model stage: 4 calls in 40 s, picture reached the model, no shell used). Separate check: asked to run a shell command and to list its tools, the model answered "No shell tool is available" and listed apply_patch, glob, grep, read, the MCP resource tools, the 11 robot tools, skill, task, todowrite, webfetch.

## Results

**Not a clean run**: the human asked to end it; agent killed at 11.0 minutes, 178 of 900 s robot time used.

| | No shell (this run) | With shell (1114-2242, same room) |
|---|---|---|
| Score | 0.0 (stopped by us) | 1.0 (clean) |
| Trash | apple core on the floor | in the bin |
| Brush in hand | 12.1 s, third grasp call | 8.7 s |
| Bin in hand | 31.1 s, third grasp call | 11.1 s |
| Calls | 149 | 101 |
| Pictures | 30 | 17, plus 10 depth and calibration downloads |
| Grasp calls | 11 (6 took nothing) | 2 |
| Arm moves | 62 | 26 |
| Wall time / cost | 11.0 min / 6.64 USD | 7.8 min / 3.56 USD |

- Only robot tools were called: no file tool, no webfetch, no sub-agent.
- The brush touched the core at 40.3 s; the core ended on the floor, so the bin was not where it fell. After that the model set the bin down, tried four times to take it again without finding the handle, took it at 98 s and set it down at 107 s.
- With the core on the floor the score could not have risen in an uncut run unless the model got it off the floor, which no run has done.

Summary, details, call log: `results/sweep/agent-runs/frederik-astra-standard-l1-s1-1115-0208-noshell.*` (tagged `noshell`, so the comparison page leaves it out).

## Takeaways

- One run, cut off: without code the model that solves level 1 in 8 minutes loses the room. It still gets both tools, but needs three attempts for each handle and misplaces the bin by enough to miss.
- It confirms what the model comparison suggested: measured depth plus a few lines of arithmetic is what makes positions good enough. From pictures and the grey depth image alone the estimates are a few centimetres off, which is the size of the grasp tolerance (3.5 cm) and of the bin opening.
- As a task design this is only fair if the reference is under the same restriction, or the task offers another route to positions.
