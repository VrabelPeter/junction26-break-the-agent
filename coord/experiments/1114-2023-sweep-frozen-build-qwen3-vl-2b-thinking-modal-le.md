---
title: Sweep, frozen build: Qwen3-VL-2B-Thinking (Modal), level 1, standard seeds 1 2 3 and privileged seed 1
status: done
kind: eval
owner: frederik
host: fls
started: 2026-11-14T20:23+01:00
finished: 2026-11-14T20:42+01:00
commit: d868134
command: python3 runs/qwen-task/sweep/run_agent.py --model qwen --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1 ; same with --setting privileged --seeds 1 (task copy, see Setup)
headline: Qwen3-VL-2B-Thinking (Modal), level 1: 0.0 in all four runs (standard seeds 1 2 3, privileged seed 1); it never reached a tool, 31 to 36 calls were almost all drive_to; the smoke test had failed on the model stage, so these are exploratory
reference:
agent: [0.0, 0.0, 0.0]
noop:
stop_early:
---

## Hypothesis

A 2 B open vision model, Qwen3-VL-2B-Thinking, cannot do level 1 of the sweep in either setting; the runs show how far it gets. Same seeds and settings as the Kimi set (1114-1933).

## Setup

- Model: `Qwen/Qwen3-VL-2B-Thinking` served by vLLM 0.33.0 on one Modal L40S, OpenAI-compatible, tool calls parsed (hermes), thinking returned separately, up to 64 pictures per request, window 65,536 tokens. App: `serving/qwen_vl_modal.py` (committed). Direct requests to the endpoint returned a sensible description of a picture and a correct `drive_to` tool call.
- Task: a copy of `probes/sweep` at the frozen tag (`runs/qwen-task/sweep`, not committed) whose only differences are a `qwen` entry in `models.json` (provider `modal-qwen`, context 60000, output 8000 declared to OpenCode) and the regenerated `environment/opencode-models.json`. The task files are those of `sweep-frozen-1`, as for the Kimi runs; the /log change made later on main is not in it. The summaries' `commit` field shows main's HEAD, which is not what ran.
- Harbor on local Docker, OpenCode, four runs side by side, the task's own limits (900 s robot time, one hour for the agent).

    python3 runs/qwen-task/sweep/smoke.py --model qwen
    python3 runs/qwen-task/sweep/run_agent.py --model qwen --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1
    python3 runs/qwen-task/sweep/run_agent.py --model qwen --level 1 --setting privileged --seeds 1 --tag frozen1

**Smoke test: failed on the model stage** (do-nothing 0.0, interface ok, camera reference 1.0 passed). In the connection test the model called tools without the `robot_` prefix (rejected), never called the camera under its right name, so no picture reached it, and fetched the binary depth file as text, which overflowed its window. By the rule in CLAUDE.md the runs below therefore do not count as results; the human asked for them as a look at the model.

## Results

| Run | Setting | Seed | Score | Milestones | Calls logged by the server | Robot time | Wall | Input tokens | How it ended |
|---|---|---|---|---|---|---|---|---|---|
| frederik-qwen-standard-l1-s1-1114-2028-frozen1 | standard | 1 | 0.0 | none | 36: get_task 1, drive_to 35 | 55 s | 13.1 min | 1.44 M | stopped by itself |
| frederik-qwen-standard-l1-s2-1114-2028-frozen1 | standard | 2 | 0.0 | none | 31: get_task 1, camera 1, drive_to 29 | 96 s | 13.1 min | 1.24 M | stopped by itself |
| frederik-qwen-standard-l1-s3-1114-2028-frozen1 | standard | 3 | 0.0 | none | 2: get_task 1, camera 1 | 0 s | 4.0 min | 0.07 M | stopped by itself |
| frederik-qwen-privileged-l1-s1-1114-2028-frozen1 | privileged | 1 | 0.0 | none | 36: get_task 1, observe 1, drive_to 34 | 54 s | 13.3 min | 1.49 M | stopped by itself |

All four have `error: null` (no cut-off). No run picked up a tool, moved an arm or called grasp. In two of the three standard runs the camera was called once, so one picture pair did go through OpenCode to the model; in standard seed 1 it never looked. Its last message in seed 2: the robot is "consistently blocked by furniture" on the way to the table. The privileged run read the positions once (`observe`) and then only drove.

Summaries, scorer details and call logs: `results/sweep/agent-runs/frederik-qwen-*`. Modal GPU time: about 25 minutes of one L40S.

## Takeaways

- A 2 B model does not get past driving: it does not form the plan fetch tools, place bin, sweep, in either setting. Privileged information does not help it, unlike Kimi (1.0 with positions).
- As a "before" for a post-training experiment it is a floor of 0 with no milestones, which leaves the milestones as the only place to see early improvement.
- If a small open model is wanted in the comparison, a larger one (Qwen3-VL 8B or more) is the next thing to try; the same Modal app serves it by changing the model name.
