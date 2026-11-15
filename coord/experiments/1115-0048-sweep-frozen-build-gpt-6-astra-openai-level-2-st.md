---
title: Sweep, frozen build: GPT-6 Astra (OpenAI), level 2, standard, seeds 2 and 3
status: done
kind: probe
owner: frederik
host: fls
started: 2026-11-15T00:48+01:00
finished: 2026-11-15T01:04+01:00
commit: 3564f98 (task copy at sweep-frozen-1)
command: python3 runs/qwen-task/sweep/run_agent.py --model astra --level 2 --seeds 2 3 --parallel 2 --tag frozen1
headline: GPT-6 Astra (OpenAI), level 2, cameras - seed 2: 1.0 clean (reference 0.75), seed 3: 0.75 when stopped by us at 15 min (reference 1.0). With seed 1 (0.25, stopped) Astra averages 0.67 against the reference 0.75 - no consistent gap at level 2
---

## Hypothesis

GPT-6 Astra scores below the scripted camera reference at level 2 on seeds 2 and 3 (reference under Harbor, 1115-0037: 0.75 and 1.0). **Not supported**: on seed 2 it scored above the reference.

## Setup

As 1114-2242 and 1114-2303 (OpenCode's own OpenAI provider, task copy of `sweep-frozen-1`, commit 3564f98), standard setting, level 2, two runs side by side.

    python3 runs/qwen-task/sweep/run_agent.py --model astra --level 2 --seeds 2 3 --parallel 2 --tag frozen1

## Results

| Seed | Score | Trash in bin | Mistakes | Calls | Robot time | Wall | Cost (OpenCode) | Ended | Reference (Harbor) |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 1.0 | 4 of 4 | none | 94 | 151 s | 7.6 min | 3.48 USD | by itself | 0.75 |
| 3 | 0.75 | 3 of 4 | none | 173 | 227 s | 15.4 min | 10.10 USD | cut off by us | 1.0 |

- Seed 2, clean: brush at 8 s, bin at 10 s, first trash in the bin at 56 s, all four in at 130 s. The brush touched a personal item once (91 s); mug and glasses stayed on the table.
- Seed 3, **not a clean run** (the human asked to end it; agent killed at 15.4 min): three pieces in the bin, one wrapper on the floor, book and remote on the table. It took and set down the bin repeatedly (10 grasp calls, 8 releases). The wrapper on the floor would have kept an uncut run at 0.75 at most unless it brought it back.

All level 2 runs of GPT-6 Astra so far, against the reference under Harbor:

| Seed | Reference | Astra | Astra run |
|---|---|---|---|
| 1 | 0.5 | 0.25 | cut off at 8 min (1114-2303) |
| 2 | 0.75 | 1.0 | clean |
| 3 | 1.0 | 0.75 | cut off at 15 min |
| mean | 0.75 | 0.67 | |

Summaries, details, call logs: `results/sweep/agent-runs/frederik-astra-standard-l2-s{2,3}-1115-0048-frozen1.*`.

## Takeaways

- **No consistent gap at level 2 against GPT-6 Astra.** It is below the reference in two rooms and above it in one; the means differ by 0.08 with two of three agent runs cut off. On the one clean run the agent beats the reference.
- The camera reference at 0.75 is the limit. Told the positions, the same controller scores 1.0 on these three rooms, and Astra reaches 1.0 from the cameras on seed 2. A reference that looks again between strokes should get there too.
- Astra's losses are single pieces swept onto the floor beside the bin; it made no mistake with personal items in any level 2 run.
- Level 3 is untested with Astra (the one attempt died for lack of credits); the camera reference averages 0.35 there in-process, so level 3 cannot show a gap either until the reference improves.
