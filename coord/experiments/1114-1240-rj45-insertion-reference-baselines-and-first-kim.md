---
title: RJ45 insertion: reference, baselines and first Kimi runs (go / no-go)
status: done
kind: eval
owner: peter
host: peter-LENOVO
started: 2026-11-14T12:40+02:00
finished: 2026-11-14T12:56+02:00
commit: 2e4dfd4
command: INSERTION_SEED=<s> sg docker -c '.venv/bin/harbor run -p probes/insertion -a oracle|nop|opencode -m verda/kimi-k3-1-pro --base-url https://inference.verda.com/v1 --api-key-name VERDA_API_KEY --api-format openai_chat_completions --env-file .env -o runs/insertion'
headline: RJ45 insertion: NO gap. Kimi 1.0 / 0.9 / 1.0 (29 of 30 ports), reference 1.0, nop 0, stop-early 0.1
reference: 1.0
agent: [1.0, 0.9, 1.0]
noop: 0.0
stop_early: 0.1
---

## Hypothesis

The Ethernet insertion task of docs/env-spec.md with real MuJoCo contact physics (probes/insertion): ten ports per job, port located only to within about 2 mm and 2 degrees, 0.15 mm clearance, 10 s of robot time per port, moves of any size with a force guard. Question: does a strong model under Harbor latch clearly fewer ports than the scripted sweep-search reference?

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

## Takeaways

## Setup

`probes/insertion` at commit `4d7bb83`. Real MuJoCo contact physics: the plug is a free rigid body on a 6-DoF spring (2 N/mm), the port a cavity with a rounded mouth, 0.15 mm clearance per side, 0.25 ms step. Hidden per port: port estimate off by up to 1.5 mm and 1 deg, plug in the fingers off by up to 0.5 mm and 1 deg. Ten ports per job, 10 s of robot time per port, moves of any size with a force guard, score = mean over ports (latched 1, partial depth up to 0.5, damaged 0). Local Docker; OpenCode + Kimi K3.1 Pro on Verda.

## Results

In-process, 20 jobs (200 ports): reference 199 latched, mean score 0.995, 3.2 s per port; straight down on the estimate 0 latched (0.04); stop-early 0.10; do-nothing 0.00.

Under Harbor:

| Run | Seed 1 | Seed 2 | Seed 3 |
|---|---|---|---|
| reference (`-a oracle`) | 1.000 | | |
| do-nothing (`-a nop`) | 0.000 | | |
| stop-early | 0.100 | | |
| **agent (Kimi K3.1 Pro)** | **1.000** | **0.900** | **1.000** |

Agent: 29 of 30 ports latched, 2.8 to 4.2 s of robot time per latched port (the reference: 3.0), 92 to 113 tool calls, 5 to 10 minutes of wall time, $0.64 to $1.11 per job. The one miss ran out of time while searching.

How it did it (seed 1, port 1, from its reasoning): it worked out from the task text that the port had to be found by touch, pressed the plug onto the panel with 3 N, swept it across in rows 0.45 mm apart, noticed the drop, and pushed home with 8 N. That is the same search the scripted reference uses, invented on the first port.

Files: `results/insertion/kimi-seed*.{commands,details}.json`.

## Takeaways

**No-go on the gap: a strong model does this as well as the reference.** Condition 3 of the go / no-go in `docs/env-spec.md` fails.

- This is the fourth design with the same outcome (satellite operations, tabletop with the Panda hand, tabletop with long fingers, insertion): given numbers, a physical description and feedback, Kimi reasons its way to the reference's strategy. Force feedback is enough for it; it does not need to be shown the technique.
- The claim "large models fail at the precision part" is not true for this interface. It may be true when the only input is camera images, which this task does not test, and it is true in wall-clock terms: the model takes 30 to 60 s of thinking per port where a small policy would act in real time. Neither is a gap under the rubric as it stands: images are untested through the harness, and a wall-clock limit is "impossible timing".
- What the insertion task is still good for: it is fast (7 ports per second on one core) and the reference is a simple reactive policy, so it is a good vehicle for the post-training experiment (small model before and after), even though the trained model can at best tie the large one on score.

