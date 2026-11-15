---
title: Sweep, frozen build: Nemotron 3.5 Super VL, standard setting, level 1, seeds 1 2 3
status: done
kind: eval
owner: peter
host: peter-LENOVO
started: 2026-11-14T19:39+02:00
finished: 2026-11-14T20:27+02:00
commit: 9793db8
command:
headline: Nemotron on the frozen build, level 1: 0.0 in three rooms, but all three runs were cut off after 16 min by a network failure and the privileged run by the output limit; none counts, rerun needed
reference:
agent: []
noop:
stop_early:
---

## Hypothesis

Hypothesis: on the frozen build (tag sweep-frozen-1, arm fixed) Nemotron 3.5 Super VL scores well below the camera reference (1.0) at level 1 with cameras only, on three rooms.

Command (started by Peter on main, task files identical to tag sweep-frozen-1):

    python3 probes/sweep/run_agent.py --model nemotron --seeds 1 2 3 --parallel 3 --tag frozen1

Model: verda-nemotron/nemotron-3.5-super-vl through OpenCode, key VERDA_INFERENCE_KEY. Standard setting, level 1, seeds 1 2 3, local Docker, three runs side by side. Smoke test passed on this build at 18:32 (message 1114-1832-peter-build-frozen-tag-sweep-frozen-1-on-main-arm-fixe). Summaries go to results/sweep/agent-runs/.

## Results

Started by Peter at 19:40 (three standard runs side by side) and 19:42 (one privileged run, `--setting privileged --tag frozen1`), task files identical to tag `sweep-frozen-1`. Summaries, scorer details and logged calls: `results/sweep/agent-runs/peter-nemotron-*-frozen1.*`.

| Run | Setting | Room (seed) | Score | Trash in bin | Mistakes | Milestones | Tool calls | Robot time | Wall time | Input tokens | How it ended |
|---|---|---|---|---|---|---|---|---|---|---|---|
| peter-nemotron-standard-l1-s1-1114-1940-frozen1 | standard | 1 | 0.0 | 0 of 1 | bin tipped over | none | 459 | 131 s | 16.5 min | 6.2M | cut off: network failure |
| peter-nemotron-standard-l1-s2-1114-1940-frozen1 | standard | 2 | 0.0 | 0 of 1 | bin tipped over | none | 164 | 108 s | 16.5 min | 6.7M | cut off: network failure |
| peter-nemotron-standard-l1-s3-1114-1940-frozen1 | standard | 3 | 0.0 | 0 of 1 | none | none | 163 | 121 s | 16.4 min | 8.2M | cut off: network failure |
| peter-nemotron-privileged-l1-s1-1114-1942-frozen1 | privileged | 1 | 0.0 | 0 of 1 | none | none | 2 | 0 s | 1.7 min | 39k | output limit reached |

Reference on the same level: 1.0 under Harbor in room 1 (experiment 1114-1835) and 1.0 in-process in rooms 1, 2 and 3 (rerun while making the comparison page). Do-nothing and stop-early: 0.0.

Replaying each standard run's logged calls in a fresh copy of the simulator ends with the same score (0.0).

## Takeaways

- **None of the four runs is a clean result; all need a rerun.**
- The three standard runs were ended by our side, not by the model. At 19:56 all three OpenCode sessions failed within four seconds of each other with `getaddrinfo EAI_AGAIN containers.datacrunch.io` (the model's address could not be resolved from the containers, so a network or DNS interruption on the host), and Harbor recorded `NonZeroAgentExitCodeError`. The scorer still ran, which is why a score of 0.0 exists. Only 108 to 131 s of the 900 s robot time had been used.
- Until then no run had reached a milestone (the brush was never in a hand) after 163 to 459 calls, and in two rooms the bin already lay on its side. That is how far the model got in 16 minutes, not a final score.
- The privileged run: after `get_task` and `observe` the model reasoned for 16,000 tokens, hit the output limit declared for it in `models.json`, and OpenCode ended the session (finish reason `length`). The robot never moved. Whether a 16k output limit is fair for a model that reasons this long is open; raising it changes `environment/opencode-models.json`, so it means a new frozen tag.
- `run_agent.py` wrote `error: null` for the cut-off runs because a score existed. It now records Harbor's exception in the summary (`error: agent cut off, not a clean run (...)`); the three summaries here were corrected by hand to the same text. **Check `error` in every summary before quoting a score**, also for the Kimi runs.
- OpenCode did not survive a short DNS failure. Running three sessions against one endpoint was not the cause as far as the logs show (no rate-limit or server errors before the failure).
- Token use is down from 17 to 123M input tokens per run on the earlier builds to 6 to 8M per 16 minutes, as intended by the declared context limit.
- Films of the three runs next to the reference: `visuals/sweep/compare.html` on the board, each marked as cut off.

## Why the tools were never picked up (replay of the three standard runs, 14 Nov 21:00)

Each run's logged calls were replayed in the simulator and, at every `grasp`, the distance from the hand to the nearest handle was measured.

| Room | Grasp attempts | Hand to nearest handle at the grasp | Hand had arrived where the model sent it |
|---|---|---|---|
| 1 | 4 | 19 to 39 cm | 3 of 4 |
| 2 | 21 | 12 to 29 cm | 20 of 21 |
| 3 | 12 | 18 to 53 cm | 12 of 12 |

- All 37 grasps failed with "no handle within 3.5 cm"; the closest was 12 cm. In 35 of 37 the arm had arrived within 2 cm of the commanded point, so the arm did what was asked and the commanded point was wrong: the model mislocated the handles from the pictures and depth.
- Room 1: 35 of 45 `move_arm` calls did not arrive. 14 were refused as out of reach before moving; the rest stopped against the station shelf (`touching` names it), with targets 4 to 20 cm below or beside the handle from a base position where the arms already touched the shelf. The model did not come from above (hover, then descend), which is how the reference takes the tools.
- The bin on its side in rooms 1 and 2 is from the arm or base pushing it while groping.
- Not found: any call where the model commanded a point within 3.5 cm of a handle and the grasp or the arm failed. So no sign here of the old arm fault. Not yet checked: where exactly the model's position estimate goes wrong (its own reasoning shows it struggling to project depth into room coordinates).

Camera use in the same three runs (from the logged calls and the agent's own text):

| Room | Head pictures (tool + downloads) | Wrist pictures | Depth downloads |
|---|---|---|---|
| 1 | 2 + 13 | 2 + 20 | 14 |
| 2 | 23 + 1 | 0 | 20 |
| 3 | 10 + 7 | 7 + 3 | 7 |

- The wrist cameras were used in rooms 1 and 3 and did not help: the model mostly processed pictures as numbers in its shell (colour thresholds, clusters, projections) rather than looking at them, and its geometry was off. Example, room 3: it put the brush's red end at (-1.77, -0.63, 0.50); the brush grasp point is at (-1.62, -0.82, 0.54) and the bin's red bar at (-1.62, -0.36, 0.35). The wrist cameras have no depth, so a wrist pixel only gives a position with an assumed height.
- For attributing the failure to the model, the missing piece is a clean privileged run (handle positions given): if it takes the tools there, the standard failure is perception; if not, it is also the handling. The privileged run here ended on the output limit before moving.

**Superseded, 14 Nov 22:20:** the complete reruns are experiment 1114-2218 (0.0 in three rooms from the cameras, 0.0 told positions). The pattern found here (grasps far from the handles) is the same there.
