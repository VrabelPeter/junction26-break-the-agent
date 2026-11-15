# Full Harbor run logs

Complete trial folders of `harbor run` on the living-room sweep task (frozen build, tag `sweep-frozen-1`), copied from
`runs/sweep/` as Harbor wrote them. Left out: OpenCode's own database and snapshot folders, and Harbor's empty artifacts folder.

| Folder | Run | Reward | Trash in bin | Source run |
|---|---|---|---|---|
| `reference-cameras-l1-s1/` | Scripted reference (Harbor oracle agent), cameras, level 1, seed 1 | 1.0000 | 1 of 1 | reference-l1-s1-rerun |
| `astra-standard-l1-s2/` | GPT-6 Astra (OpenCode), cameras, level 1, seed 2 | 1.0000 | 1 of 1 | frederik-astra-standard-l1-s2-1114-2244-frozen1 |
| `astra-standard-l2-s2/` | GPT-6 Astra (OpenCode), cameras, level 2, seed 2 | 1.0000 | 4 of 4 | frederik-astra-standard-l2-s2-1115-0048-frozen1 |
| `kimi-privileged-l1-s1/` | Kimi K3.1 Pro (OpenCode), told positions, level 1, seed 1 | 1.0000 | 1 of 1 | frederik-kimi-privileged-l1-s1-1114-1934-frozen1 |
| `gemma4-standard-l1-s1/` | Gemma 4 31B (OpenCode), cameras, level 1, seed 1 | 0.0000 | 0 of 1 | frederik-gemma4-standard-l1-s1-1114-2116-frozen1 |

In each folder:

- `result.json`, `config.json`, `trial.log`: Harbor's record of the trial (agent, model, timings, exception if any).
- `verifier/reward.txt`: the score, one number between 0 and 1. `verifier/details.json`: where every object ended and
  which mistakes were counted. `verifier/commands.json`: every call the simulator received, with its reply.
- `agent/opencode.txt`: OpenCode's event log (each step, tool call, reply, token count). `agent/trajectory.json`: the same
  run as a trajectory. For the reference run the agent is Harbor's `oracle`, so the log is `agent/oracle.txt`.

A run can be replayed in the simulator from its call log: `python probes/sweep/viewer/replay_log.py <folder>/verifier/commands.json`.
The model runs were made on a copy of the frozen task whose only change is the model's entry in the model list.
The GPT-6 Astra logs contain OpenAI's encrypted reasoning blobs (long opaque strings); they are not credentials.
