# Post-training experiment: does the environment's reward help a smaller model learn?

Serves the tiebreak ("a smaller model that improves after training on experience from the environment").

A small open model, **Qwen3-4B-Instruct-2507** (4.0 B parameters), controls the living-room sweep robot through
the environment's own tool calls, written as text, in the **privileged** setting (object positions in `observe`,
no pictures) at **level 1**. Three arms, all scored by the environment's own score on held-out seeds:

| Arm | Model | Trained on |
|---|---|---|
| A | base model | nothing |
| B | base + LoRA | episodes **selected by the reward**: environment score >= 0.99 |
| C | base + LoRA | the **same number** of episodes drawn at random from the same pool, score not looked at |

If B beats A and C, the reward carried the learning signal: the same model, the same amount of experience from
the same pool, and the only difference is whether the environment's score chose the episodes.

**Status: code written and checked locally without a GPU. No model has been trained or evaluated yet; there is no result.**

## Where the experience comes from

From the environment, not from a language model. `collect.py` runs the repository's scripted privileged reference
(`sweep/policies.py: reference_privileged`) in-process on training seeds (1000 and up), as it is and in damaged
versions (noise on the targets, calls dropped, stopping early, the bin set down beside the right place), so that
scores spread. Every executed call is logged with the simulator's reply and the episode gets the environment's score.

Measured on seeds 1000-1119, level 1 (120 episodes, 14 Nov):

| Variant | n | mean score | score 0 | score 1 |
|---|---|---|---|---|
| reference | 36 | 1.000 | 0 | 36 |
| noise:0.01 | 12 | 0.833 | 2 | 10 |
| noise:0.02 | 12 | 0.500 | 6 | 6 |
| noise:0.04 | 12 | 0.000 | 12 | 0 |
| drop:0.08 | 12 | 0.333 | 8 | 4 |
| drop:0.2 | 12 | 0.000 | 12 | 0 |
| stop | 12 | 0.000 | 12 | 0 |
| binoff:0.14 | 12 | 0.500 | 6 | 6 |
| all | 120 | 0.517 | 58 | 62 |

So about half the pool passes the filter, and arm C trains on a set that is about half failed episodes. Level 1
has one piece of trash, so its scores are 0 or 1; level 2 gives scores in between (20 episodes, seeds 1000-1019:
7 at 0, 9 between, 4 at 1).

## The text interface (`textenv.py`)

- The model writes one flat JSON object per turn, e.g. `{"tool":"drive_to","x":-0.95,"y":-0.6,"heading":3.142}`,
  and `{"tool":"done"}` to stop. Numbers have 3 decimals.
- Each tool reply is shortened by `compact_reply`, **the same function for the training data and for evaluation**:
  `observe` gives base, torso, both hands, every object and both tool handles; a moving tool's reply keeps what that
  move changed (`reached`, the base or the hand, what is held) and the time left. Arm joint angles, finger opening
  and head angles are dropped.
- The system prompt (1,143 Qwen tokens) is a shortened `probes/sweep/instruction.md`: goal, score, tools, room,
  robot, tools at the station. The camera sections are left out (no pictures in this setting).
- A whole level-1 episode is 48 to about 135 calls: **median 6,265 tokens, 90th percentile 9,376, longest 17,225**
  (Qwen tokenizer, system prompt included; 2.48 characters per token).

## Commands, in order

Local Python for steps 1 to 3 needs `mujoco==4.0.1` and `numpy`; step 4 on needs the `modal` CLI, logged in.
Run everything from the repository root. Register the run in `coord/experiments/` before step 5 (`tools/coord.py new exp`).

```bash
PY=<python with mujoco 4.0.1>        # on Peter's machine: /home/peter/.claude/jobs/6b11b2fe/tmp/mj/bin/python

# 1. experience: 480 episodes on training seeds. About 13 minutes on 20 cores (measured: 120 episodes in 191 s). Free.
$PY training/collect.py --seeds 1000-1479 --level 1 --out training/data/episodes_l1.jsonl

# 2. the scripted reference on the evaluation seeds, for the results file. About 1 minute. Free. Optional.
$PY training/collect.py --seeds 1-30 --level 1 --variants reference --out training/data/eval_reference_l1.jsonl

# 3. the two training sets. Seconds.
$PY training/dataset.py --episodes training/data/episodes_l1.jsonl --out-dir training/data

# 4. smoke: 4 episodes, 6 training steps, 1 evaluation seed, 12 calls. Checks image, download, training, adapter, evaluation.
modal run training/modal_app.py --smoke

# 5. the experiment
modal run training/modal_app.py
```

| Step | Time | Modal cost |
|---|---|---|
| 4. smoke | est. 10 to 15 min the first time (image build, 8 GB model download), 5 min after | est. under $1 |
| 5. full run | est. 1.5 to 3 h wall clock; A and the two trainings run side by side | est. $4 to $8 (2 to 4 L40S hours at $1.95) |

The estimates are **not measured**: nothing has run on a GPU yet. Write the real numbers here after the smoke run.
Hard ceiling from the function timeouts: 2 trainings x 2 h + 3 evaluations x 3 h = 13 GPU hours, about $25.
Every GPU function asks for exactly one `L40S`; nothing starts a cluster.

Useful flags of step 5: `--eval-seeds 1-30`, `--epochs 3`, `--lr 2e-4`, `--n 100` (cap on episodes per arm),
`--batch-size 8` (episodes decoded together), `--max-calls`, `--seed`, `--run <name>`, `--level`, `--model-id`.

## What comes out

| File | What |
|---|---|
| `training/data/episodes_l1.jsonl` | one episode per line: seed, level, variant, calls (tool, args, robot time, reply), score, milestones. Not committed (about 16 MB), reproducible from the command |
| `training/data/train_B.jsonl`, `train_C.jsonl` | the two training sets as chats. Not committed |
| `training/data/dataset_meta.json` | pool and per-arm counts, score shares, variant mix, token lengths, seeds, hash of the episode file |
| `results/training/<run>.json` | **the result**: per-seed scores and mean per arm, B-A / B-C / C-A per seed, number of training episodes, model id and revision, seeds, git commit, training loss curve, stop reasons, milestone counts. Written as the run goes, so a crash keeps what finished |
| `runs/training/<run>/dialogues_<arm>.jsonl` | every evaluation dialogue (ignored by git), for explaining failures |
| Modal volume `sweep-training-adapters` | the LoRA adapters at `/<run>/<arm>` |

## Files

| File | What |
|---|---|
| `textenv.py` | call format and parser, reply compaction, system prompt |
| `collect.py` | scripted controllers + damage, in-process, parallel, JSONL out |
| `dataset.py` | episodes to chats; reward-selected set B and unselected set C |
| `policy_loop.py` | a model (messages to text) as the controller; `run_batch` plays many seeds in lockstep; scripted stand-ins |
| `lm.py` | labels on assistant turns only, LoRA training loop, batched greedy decoding |
| `modal_app.py` | Modal app: `prefetch`, `train(arm)`, `evaluate(arm, seeds)`, and the entrypoint that runs the experiment |

## Checks that were run (14 Nov, no GPU)

```bash
MUJOCO_GL=egl $PY training/policy_loop.py --replay training/data/check_l1.jsonl --n 5     # recorded calls, said as text
MUJOCO_GL=egl $PY training/policy_loop.py --text-reference --seeds 1-5 --level 1         # reference reading only the compact replies
python training/lm.py --check training/data/train_B.jsonl <dir with the Qwen tokenizer files>   # needs transformers
```

- Replaying recorded episodes through the text loop gives the recorded score in 13 of 13 episodes tried
  (11 at level 1, 2 at level 2; scores 0, 0.75 and 1 among them).
- The scripted reference, made to write its calls as text and to read only the compact replies, scores 1.0 on
  seeds 1 to 5 at level 1: the compact text carries everything needed to solve the room.
- With the real Qwen tokenizer and chat template, the labelled tokens are exactly the tool calls plus `<|im_end|>`,
  and the prompt used at evaluation is a prefix of the training text.
- `modal run training/modal_app.py --help` loads the app and lists the flags. No Modal function was started.

## Why this model

Qwen3-4B-Instruct-2507: 4.0 B parameters, Apache 2.0, not gated, text-only, a plain causal LM that
`transformers 4.57.1` + `peft 0.17.1` load without special handling, no thinking mode to switch off, fits one L40S
in bf16 with LoRA on 16k-token episodes. The team's earlier proposal was Gemma 4 E4B (also eligible for the Gemma side
challenge). It is not the default because `google/gemma-4-E4B-it` is a multimodal `Gemma4ForConditionalGeneration`
that needs `transformers` 5.x and a different loader, which could not be tested here without a GPU. `lm.load` would
have to change for it; `--model-id` alone only works for text-only causal LMs (for example a smaller Qwen3).

## Honest limitations

- **Privileged, text-only setting.** The model is told where every object is. The headline task (cameras, no
  positions) is not what is trained or evaluated here. In-process, not through Harbor/OpenCode/MCP; the `why` hints
  that the MCP server adds to failed moves are not in these replies.
- **Imitation with reward filtering, not online RL.** The experience is produced by scripted controllers; the reward
  only decides which episodes are imitated (arm B). The model never learns from its own attempts.
- **Level 1.** One piece of trash on the table, tools always at the same place; rooms differ in the kind of trash
  and where it lies. Scores are 0 or 1. A level-2 episode of the reference is about 135 to 145 calls and 23k to 26k tokens
  (measured on 7 episodes), four times level 1. It was not budgeted: the code takes `--level 2` (collect, dataset,
  `modal run ... --level 2 --max-len 32768`), but that path is untested and memory and cost go up several times.
- **A is expected near 0.** An untrained 4 B model is unlikely to chain about 50 exact calls, so B > A mostly says
  the task is learnable from environment experience. **B versus C is the test of the reward.** How sharp that test
  is depends on the pool: here about half of C's episodes are failures made by our own damage variants.
- **Same number of episodes, not of tokens.** B and C hold equally many episodes; on the check batch they also
  came out within 2 % in assistant turns and tokens, but that is not enforced. Episodes over 16,384 tokens lose their tail in training.
- **One training seed, greedy decoding, 30 evaluation seeds.** A difference of a few seeds is within noise; the
  results file gives per-seed scores so this can be judged. Batched decoding pads dialogues, so a score can in
  principle depend on which seeds share a batch.
- **Evaluation limits** (in `policy_loop.py`): 120 calls at level 1, 45,000 characters of dialogue, 8 replies in a
  row that are not tool calls, 900 s robot time. They apply to all arms alike.
- Costs and durations above are estimates until the smoke run.
