# Living-room sweep under Harbor, 14 Nov (experiment 1114-1500)

Level 1 (one piece of trash, an apple core, on the table), seed 1, local Docker, branch `sweep-env`.
Model runs: OpenCode 1.19.5 + `verda/kimi-k3-1-pro`. Cost from OpenCode's token log at Verda's prices
(input 2, cached input 0.2, output and reasoning 10 USD per million tokens).

| Run | Interface the agent had | Score | Status | Cost (USD) |
|---|---|---|---|---|
| nop | - | 0.0 | clean | 0 |
| oracle, stop_early (fetch both tools, stop) | privileged | 0.0 | clean | 0 |
| oracle, reference_privileged | privileged | 1.0 | clean | 0 |
| kimi_std_s1 | standard, colour pictures + `depth_at` tool, first build | 0.0 | tainted by our bugs | 2.89 |
| kimi_priv_s1 | privileged, colour pictures + `depth_at`, first build | 0.0 | tainted by our bugs, stopped by us at 21 min | 3.85 |
| kimi_std_s1_b | "standard plus a pixel-to-position tool (not the task)": colour + `depth_at`, fixed build | 0.0 | truncated by us at 26 min | 5.22 |
| kimi_pics_s1 | colour pictures and calibration only, no depth in any form, fixed build | 0.0 | clean (the agent stopped by itself after 46 min) | 9.17 |
| nop2, stop_early2, reference2 (fixed build, colour only) | as above | 0.0, 0.0, 1.0 | clean | 0 |

The two bugs: the bin's rim was drawn as a solid plate, so the bin looked closed and no camera could see
into it; and an arm twisted by a collision could not be brought back (there was no `home_arm`).

`*.details.json` is the scorer's output, `*.commands.json` the logged calls; a run can be repeated in-process
with `python probes/sweep/viewer/replay_log.py results/sweep/<run>.commands.json`.
