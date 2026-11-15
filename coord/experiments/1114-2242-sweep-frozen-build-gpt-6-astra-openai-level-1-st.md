---
title: Sweep, frozen build: GPT-6 Astra (OpenAI), level 1, standard seeds 1 2 3 and privileged seed 1
status: done
kind: probe
owner: frederik
host: fls
started: 2026-11-14T22:42+01:00
finished: 2026-11-14T22:54+01:00
commit: 3564f98 (task copy at sweep-frozen-1)
command: python3 runs/qwen-task/sweep/run_agent.py --model astra --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1 ; same with --setting privileged --seeds 1 (task copy, see Setup)
headline: GPT-6 Astra (OpenAI), level 1 - 1.0 from the cameras in rooms 1 and 2 (clean, 5 to 8 min), 0.0 in room 3 (trash was in the bin at 131 s, then it carried the bin away and tipped it; cut off by us at 8.8 min), 1.0 told positions. Level 1 is no gap for this model
---

## Hypothesis

A current frontier model from OpenAI, GPT-6 Astra, scores below the camera reference (1.0) at level 1, like Kimi, Nemotron and the open models did. **Refuted.**

## Setup

`gpt-6-astra` through OpenCode's own OpenAI provider (`harbor run ... -a opencode -m openai/gpt-6-astra --api-key-name OPENAI_KEY`, no `--api-format` and no `--base-url`). The two other routes fail: OpenAI refuses function tools with reasoning on `/v1/chat/completions` for this model, and Harbor's OpenCode agent does not accept `--api-format openai_responses`. Declared to OpenCode: image input, context 200000, output 32000 (a guess; no context error occurred). Task: the copy of the frozen task (`runs/qwen-task/sweep`: the files of tag `sweep-frozen-1` plus the model's entry in `models.json` and `opencode-models.json`, and a `native` branch in the copy's `models.py: harbor_args`; summaries carry `commit: 3564f98`). Harbor 0.26.0 on local Docker, four runs side by side.

    python3 runs/qwen-task/sweep/smoke.py --model astra --skip-free
    python3 runs/qwen-task/sweep/run_agent.py --model astra --level 1 --seeds 1 2 3 --parallel 3 --tag frozen1
    python3 runs/qwen-task/sweep/run_agent.py --model astra --level 1 --setting privileged --seeds 1 --tag frozen1

**Smoke test passed** (model stage at 22:43: 5 calls in 48 s, get_task, camera, depth file, observe, drive_to; the picture reached the model). The first attempt at 22:42 failed before any call because of the unsupported `openai_responses` flag.

## Results

| Run | Setting | Seed | Score | Mistakes | Trash in bin at | Calls | Robot time | Wall | Cost (OpenCode) | Ended |
|---|---|---|---|---|---|---|---|---|---|---|
| frederik-astra-standard-l1-s1-1114-2244-frozen1 | standard | 1 | 1.0 | none | 122.0 s | 101 | 150 s | 7.8 min | 3.56 USD | by itself |
| frederik-astra-standard-l1-s2-1114-2244-frozen1 | standard | 2 | 1.0 | none | 75.0 s | 68 | 105 s | 5.0 min | 2.00 USD | by itself |
| frederik-astra-standard-l1-s3-1114-2244-frozen1 | standard | 3 | 0.0 | bin tipped over | 131.4 s | 121 | 185 s | 8.8 min | 5.09 USD | cut off by us |
| frederik-astra-privileged-l1-s1-1114-2244-frozen1 | privileged | 1 | 1.0 | none | 55.4 s | 55 | 57 s | 4.0 min | 1.45 USD | by itself |

- In all three camera runs it took pictures (13 to 24), downloaded the measured depth and calibration (8 to 10 `camera_file` calls), took the brush within 9 to 22 s and the bin within 11 to 27 s, and swept the trash into the bin.
- Room 3 is **not a clean run**: the human asked to end it and we killed the agent at 8.8 minutes. Before that the model had the apple core in the bin at 131.4 s. It did not stop: it picked the bin up again, drove to the sofa (level 1 has no trash there, and the agent is not told how many pieces exist), pressed the bin against something twice ("the bin it holds against core 1"), released it at 174.5 s, and the bin lay on its side with the core on the floor when we cut it off. Had it stopped at 131 s the score would be 1.0.
- Tokens: 0.9 to 3.3 M cached input per run, under 400 uncached, 4 to 8 k output. Total cost 12.10 USD by OpenCode's price table.

Summaries, details, call logs: `results/sweep/agent-runs/frederik-astra-*`.

## Takeaways

- **Level 1 is not a gap for GPT-6 Astra**: two clean 1.0 from the cameras and one from told positions, each in under 8 minutes. The gap we showed at level 1 holds for Kimi, Nemotron and the open models only.
- The one failure is a decision, not perception or control: with the task done it kept searching for more trash and lost what it had. That fits the task's rule that the number of pieces is not given, and is a candidate for the failure analysis.
- Levels 2 and 3 have not been run with this model. That is where a gap against it would have to be shown.
