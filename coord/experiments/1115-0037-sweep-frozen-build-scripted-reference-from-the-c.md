---
title: Sweep, frozen build: scripted reference from the cameras under Harbor, level 2, seeds 1 2 3
status: done
kind: probe
owner: frederik
host: fls
started: 2026-11-15T00:37+01:00
finished: 2026-11-15T00:44+01:00
commit: 3564f98 (task copy at sweep-frozen-1)
command: SWEEP_SEED=<1|2|3> SWEEP_LEVEL=2 SWEEP_SETTING=standard .venv/bin/harbor run -p runs/qwen-task/sweep -a oracle -o runs/sweep/reference-l2-s<seed>-harbor
headline: Scripted camera reference under Harbor, level 2 - 0.5, 0.75, 1.0 on seeds 1 2 3 (mean 0.75), no mistakes; identical to the in-process scores
---

## Hypothesis

The scripted camera reference scores the same under Harbor at level 2 as in-process (0.5, 0.75, 1.0 on seeds 1 2 3).

## Setup

Harbor 0.26.0, local Docker, `oracle` agent (the task's `solution/solve.sh`), no model. Task files: the copy of tag `sweep-frozen-1` in `runs/qwen-task/sweep` (identical to the tag except for extra entries in the model list, which the oracle does not use). Three runs side by side.

    SWEEP_SEED=1 SWEEP_LEVEL=2 SWEEP_SETTING=standard .venv/bin/harbor run -p runs/qwen-task/sweep -a oracle -o runs/sweep/reference-l2-s1-harbor
    (same with SWEEP_SEED=2 and SWEEP_SEED=3)

## Results

| Seed | Score | Trash in bin | Mistakes | Robot time | Left behind |
|---|---|---|---|---|---|
| 1 | 0.5 | 2 of 4 | none | 237 s | one wrapper on the floor, the banana peel on the table |
| 2 | 0.75 | 3 of 4 | none | 221 s | one tissue on the table |
| 3 | 1.0 | 4 of 4 | none | 300 s | nothing |

Mean 0.75. Same scores and trash counts as the in-process runs of the same rooms (15 Nov, seeds 1 to 5 in-process: 0.5, 0.75, 1.0, 0.75, 0.75 from the cameras; 1.0, 1.0, 1.0, 0.75, 1.0 told positions). Personal items untouched in all three.

Details and call logs: `results/sweep/reference-cameras-l2-s{1,2,3}-harbor-1115-0037.{details,commands}.json`.

## Takeaways

- At level 2 the camera reference is at 0.75, not 1.0. On seed 1 it scores 0.5 where GPT-6 Astra had 0.25 when stopped (1114-2303): a gap of 0.25 on one room, one cut-off agent run.
- The same controller told the positions scores 1.0 on these three rooms, so what the camera reference loses is in its picture of the room after the first strokes, not in the sweeping.
- For a level 2 gap: three clean GPT-6 Astra runs on these seeds, and a camera reference closer to 1.0.
