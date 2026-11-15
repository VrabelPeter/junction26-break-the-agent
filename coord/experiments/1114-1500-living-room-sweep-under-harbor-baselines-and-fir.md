---
title: Living-room sweep under Harbor: baselines and first Kimi runs, privileged and standard
status: done
kind: eval
owner: peter
host: peter-LENOVO
started: 2026-11-14T15:00+02:00
finished: 2026-11-14T16:25+02:00
commit: d15596f
command: harbor run -p probes/sweep -a <nop|oracle|opencode> (exact lines in Setup); SWEEP_SETTING, SWEEP_LEVEL=1, SWEEP_SEED=1
headline: Sweep level 1 seed 1 under Harbor: nop 0, stop-early 0, scripted reference 1.0; Kimi 0.0 in all four runs (one clean, colour pictures only), the trash always lands beside the bin
reference: 1.0
agent: []
noop: 0.0
stop_early: 0.0
---

## Hypothesis

Hypothesis: under Harbor the sweep task (branch sweep-env, probes/sweep) scores 0 for do-nothing and for fetch-the-tools-then-stop, 1.0 for the scripted privileged reference on level 1 seed 1, and OpenCode + kimi-k3-1-pro does clearly worse in the standard setting (cameras only) than in the privileged setting (object positions given). At most 4 model runs, 8 USD.

## Setup

Branch `sweep-env` (last commit of this experiment: 4f6d752), task directory `probes/sweep`, local Docker, level 1 (one piece of trash, an apple core, on the coffee table), seed 1. Sidecar settings come from the environment: `SWEEP_SEED`, `SWEEP_LEVEL`, `SWEEP_SETTING` (standard or privileged).

```
harbor run -p probes/sweep -a nop -o runs/sweep/nop
SWEEP_SETTING=privileged harbor run -p probes/sweep -a oracle --ae SWEEP_POLICY=stop_early -o runs/sweep/stop_early
SWEEP_SETTING=privileged harbor run -p probes/sweep -a oracle --ae SWEEP_POLICY=reference_privileged -o runs/sweep/reference
SWEEP_SETTING=<standard|privileged> harbor run -p probes/sweep -a opencode -m verda/kimi-k3-1-pro \
  --base-url https://inference.verda.com/v1 --api-key-name VERDA_API_KEY --api-format openai_chat_completions \
  --env-file .env -o runs/sweep/<label> \
  --ak 'opencode_config={"provider":{"verda":{"models":{"kimi-k3-1-pro":{"attachment":true,"modalities":{"input":["text","image"],"output":["text"]}}}}}}'
```

Model: OpenCode 1.19.5 + `verda/kimi-k3-1-pro`. Cost is computed from OpenCode's token log at Verda's prices (input 2, cached input 0.2, output and reasoning 10 USD per million). Summaries and call logs: `results/sweep/` on the branch.

## Results

| Run | Interface the agent had | Score | Status | Cost (USD) |
|---|---|---|---|---|
| nop | - | 0.0 | clean | 0 |
| oracle stop_early (fetches both tools, stops) | privileged | 0.0 | clean | 0 |
| oracle reference_privileged | privileged | 1.0 (35 s of robot time) | clean | 0 |
| kimi_std_s1 | standard: colour pictures + a `depth_at` pixel-to-position tool, first build | 0.0 | tainted by our bugs | 2.89 |
| kimi_priv_s1 | privileged: object positions, colour pictures + `depth_at`, first build | 0.0 | tainted by our bugs, stopped by us at 21 min | 3.85 |
| kimi_std_s1_b | standard plus a pixel-to-position tool (not the task), fixed build | 0.0 | truncated by us at 26 min | 5.22 |
| kimi_pics_s1 | colour pictures and calibration only, no depth in any form, fixed build | 0.0 | clean: the agent stopped by itself after 46 min, 333 s of robot time | 9.17 |
| nop, stop_early, reference again on the fixed build | | 0.0, 0.0, 1.0 | clean | 0 |

Model money spent: 21.13 USD.

In all four model runs the agent fetched both tools (brush and bin in hand after 21 to 127 s of robot time) and touched the trash with the brush; in none did the trash reach the bin. Every time the apple core was swept off the table edge and landed on the floor beside the bin.

- **kimi_pics_s1 (the clean one).** Positions came from ray geometry: Python with numpy in the shell, intersecting pixel rays with planes of known height (shelf top, bar height, table top), then a wrist-camera look to refine. Errors: brush grasp point 2.8 cm from the head camera, 0.5 cm after the wrist view; bin handle 1.4 cm; apple core 0.3 cm. It set the bin against the table edge in line with the core, within about 2 cm. Then it drove the base away with the open left hand still around the bin's handle and dragged the bin 19 cm sideways, did not look again, and swept the core over the edge where the bin had been. The remaining 25 minutes went into lowering the bin over the core on the floor; it ended with the bin standing on top of the core and reported "the apple core inside its walls".
- **kimi_std_s1_b (with `depth_at`).** 90 `depth_at` calls replaced the ray geometry. The bin ended 24 cm from the table edge, turned end-on and 20 cm to the side of the core's path; the core fell beside it.
- **kimi_std_s1, kimi_priv_s1 (first build).** Same pattern (bin 8 cm and 20 cm from where the core fell). Not usable as results: the bin was drawn with a solid lid, so the agent could not see whether the core was inside (in kimi_std_s1 it concluded "likely in bin" and stopped), and in kimi_priv_s1 the left arm was twisted by a collision with the bin handle and could not be recovered.

Other measurements: software rendering (OSMesa) in the sidecar takes 0.22 s per 640x480 colour and depth frame on two cores. A replay of the logged calls in-process reproduces every outcome (milestone times within 0.1 s).

Where the tokens go (kimi_pics_s1, 303 model calls, 37.9 M prompt tokens): OpenCode never compacted, the prompt grew from 10 k to 239 k tokens and is resent on every call. Re-reading the model's own reasoning 19.8 M, pictures 4.6 M (about 430 tokens each), other tool results 1.2 M, the fixed prompt 3.1 M.

## Takeaways

- No evidence yet that the camera-only setting is what stops the model: with colour pictures and the calibration alone it located things to 0.3 to 3 cm. What failed in every run was the manipulation plan (where the bin stands when the piece leaves the table, and noticing that the robot moved the bin).
- Bugs found and fixed on the branch: bin rim drawn as a solid plate (scene.py); no way to bring back a twisted arm (new `home_arm` tool); the stop-early baseline needs the privileged setting. Wording to tighten: "inside the walls of the bin" should say above the bin's floor.
- A run costs 3 to 9 USD because the whole history is resent each step. Options and what they would have saved in kimi_pics_s1: declare a context limit so OpenCode compacts (64 k: about 5.3 USD, changes what the agent remembers); do not resend the model's reasoning (about 3.1 USD); short results from actions with the full state only from `observe` (about 0.85 USD); drop the joint lists (about 0.28 USD); 320x240 pictures (about 0.72 USD, changes what can be seen).
- Not done here: the head camera's depth (a prepared, unapplied change is in `probes/sweep/checks/depth_patch_prepared.py`), a clean privileged run, more seeds.
