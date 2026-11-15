# Breaking the Gym: the living-room sweep

Junction 2026, AfterQuery challenge "Break the Agent". A reinforcement-learning environment, built as a
Harbor task, in which a two-arm robot must sweep the trash, and only the trash, into a bin using nothing but
its own cameras. The score is read from the simulator's final physical state.

- The task: [`probes/sweep`](probes/sweep) (`instruction.md`, `task.toml`, `environment/`, `tests/`, `solution/`)
- Pictures, films and step-by-step replays of the runs: https://junction-board.pages.dev/environment.html
- Every experiment behind a number on this page: [`coord/experiments/`](coord/experiments), named by its id (`1115-0434`)
- The challenge brief and rubric: [`docs/challenge.md`](docs/challenge.md)

## What the agent has to do

A wheeled two-arm robot (PAL TIAGo++, simulated in MuJoCo 4.0.1) stands in a living room. On a coffee table,
and at the highest level on a sofa, lie pieces of trash (crumpled paper, a crushed can, a wrapper, a banana
peel, an apple core) among personal items (a phone, keys, glasses, a mug). A brush and a bin wait at a tool station.

The agent has to fetch the brush and the bin, and get every piece of trash into the bin while leaving the
personal items where they are. It has one attempt: the room is real contact physics and nothing is reset.

The agent is OpenCode under the standard Harbor harness. It drives the robot through an MCP server with eleven
tools (`drive_to`, `move_arm`, `grasp`, `look`, `camera`, ...) and a time limit of 900 seconds of robot time.

| Level | Room |
|---|---|
| 1 | One piece of trash on the table |
| 2 | Four pieces of trash and two personal items |
| 3 | Eight pieces of trash and four personal items on table and sofa, plus a jacket |

Every number on this page names its **setting**:

- **standard** (the task): the agent gets what the robot's sensors give. The head camera in colour and depth
  with its calibration, wrist cameras in colour, and the robot's own joint readings. No object positions, no
  labels, no count of the trash, and no tool that turns a pixel into a position.
- **privileged** (an ablation): the agent is also told the position and kind of every object.

## How it is scored

```
score = (trash in the bin / all trash) x 0.5 ^ mistakes        between 0 and 1
```

- A piece of trash counts when it lies inside the upright bin, on the bin's own floor.
- A mistake is a personal item that ends in the bin or on the floor, or the bin lying on its side. Each one
  halves the score.
- The score is computed from where everything lies after the room has been left alone for 2 seconds. Nothing
  is paid for reaching the tools, picking them up or touching things.
- The verifier reads the score from the simulator, which runs in a separate container, and writes it to
  `/logs/verifier/reward.txt`.

The full rules as the agent reads them: [`probes/sweep/instruction.md`](probes/sweep/instruction.md).

## Run the evaluation

Setup, once (Python 3.12+, Docker):

```bash
python3 -m venv .venv && .venv/bin/pip install "harbor[modal]"
cp .env.example .env        # put VERDA_API_KEY in for the agent runs; not needed for --skip-agent
```

One command runs the reference, three agent runs, the do-nothing baseline and the stop-early baseline, each
as a `harbor run -p probes/sweep -a <agent>`, and prints one row per kind of run and one column per room:

```bash
python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1 2 3
python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1 2 3 --skip-agent    # the same without a model
```

- The agent model defaults to Kimi K3.1 Pro on Verda's OpenAI-compatible endpoint. Another model:
  `--provider nemotron`, or `--model`, `--base-url` and `--api-key-name` (see the top of `eval/run_eval.py`).
- `--level 2` and `--level 3` run the harder rooms; `--seeds` picks the rooms; `--env modal` runs on Modal
  instead of local Docker.
- Results are written to `results/eval-<time>.json`.
- A single run by hand: `harbor run -p probes/sweep -a opencode -m <provider/model>`, with the room and level
  in `SWEEP_SEED` and `SWEEP_LEVEL` (exact lines: [`probes/sweep/README.md`](probes/sweep/README.md), "Under Harbor").

What we have run through this command: the version without a model, on the current build (experiment `1115-0522`;
reference 1.0 / 1.0 / 1.0, both baselines 0.0, file `results/eval-1115-0458.json`). The model runs reported below
were started one room at a time with `probes/sweep/run_agent.py`, which starts the same Harbor task.

## Results

### Reference and baselines

Scripted, no model. Mean over rooms 1 to 30, in-process (`1115-0434`); level 1 also under Harbor (`1115-0522`).

| Run | Setting | Level 1 | Level 2 | Level 3 |
|---|---|---|---|---|
| **Reference** | standard | 1.00 | 0.75 | 0.50 |
| Scripted controller | privileged | 1.00 | 0.91 | 0.87 |
| Do nothing | - | 0.0 | 0.0 | 0.0 |
| Fetch the tools, then stop | - | 0.0 | 0.0 | 0.0 |

The reference is a scripted controller that works from the same cameras as the agent. It is flawless at
level 1. At levels 2 and 3 it leaves behind trash that lies so close to a personal item that no brush stroke
is clear of it. Per-room values: `results/sweep/reference-inprocess-d1e3191-1115-0434.json`.

### Models, through Harbor and OpenCode

Rooms 1, 2 and 3 unless stated; one run per room.

| Model | Setting | Level 1 | Level 2 | Level 3 | Experiments |
|---|---|---|---|---|---|
| Kimi K3.1 Pro | standard | 0.0 / 0.0 / 0.0 (stopped by us at 40 min) | - | - | `1114-1933` |
| Kimi K3.1 Pro | privileged | 1.0 (room 1) | - | - | `1114-1933` |
| Nemotron 3.5 Super VL | standard | 0.0 / 0.0 / 0.0 | - | - | `1114-2218` |
| Nemotron 3.5 Super VL | privileged | 0.0 (room 1) | - | - | `1114-2218` |
| Gemma 4 31B | standard | 0.0 / 0.0 / 0.0 | - | - | `1114-2116` |
| Gemma 4 31B | privileged | 0.0 (room 1) | - | - | `1114-2116` |
| Qwen3.5-9B | standard | 0.0 / 0.0 / 0.0 (stopped by us at 24 min) | - | - | `1114-2141` |
| Qwen3.8-27B | standard | 0.0 / 0.0 / 0.0 (stopped by us at 25 min) | - | - | `1114-2141` |
| GPT-6 Astra | standard | 1.0 / 1.0 / 0.0 | 0.25 / 1.0 / 0.75 (rooms 1 and 3 stopped by us) | 1.0 (room 1) | `1114-2242`, `1114-2303`, `1115-0048`, `1115-0143` |
| GPT-6 Astra | privileged | 1.0 (room 1) | - | - | `1114-2242` |
| Claude Fable 5.2 (effort medium) | standard | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 0.875 | `1115-0545`, `1115-0206`, `1115-0242` |

Full Harbor trial folders of five of these runs, with the score, the scorer's details, every call the simulator
received and OpenCode's event log: [`results/sweep/harbor-logs/`](results/sweep/harbor-logs). Summaries and call
logs of all runs: `results/sweep/agent-runs/`.

## What the results show, by judging criterion

### The gap

- **Five of the seven models we ran score 0.0 at level 1 in every room, where the reference scores 1.0 in all
  30 rooms.** That holds for Kimi K3.1 Pro, Nemotron 3.5 Super VL, Gemma 4 31B, Qwen3.5-9B and Qwen3.8-27B, three
  rooms each. The reference and both baselines reproduce with the one command.
- **The two strongest models close the gap.** Claude Fable 5.2 scores 1.0 at level 1 and level 2 and 1.0 / 1.0 /
  0.875 at level 3, where the reference has 0.5 / 0.75 / 1.0 (level 2) and 0.5 / 0.125 / 0.375 (level 3) on the
  same rooms. GPT-6 Astra scores 1.0 in four of its seven rooms, among them level 3, room 1. Against these two
  models this environment shows no gap.
- The runs marked "stopped by us" did not end by themselves. For Kimi the trash had already left the table
  without reaching the bin when we stopped, and loose things cannot be picked up again, so 0.0 was final. The
  Qwen scores are lower bounds in the strict sense: no tool was held when we stopped.

### Meaningful difficulty

The difficulty is perception turned into action. Nothing is withheld: the pictures, the depth in metres, the
camera calibration, the formula from a pixel to a point in the room, the floor plan, the tool sizes and a free
`can_reach` check are all in the instruction and the tools.

- **Kimi K3.1 Pro: same model, same tools, 0.0 from the cameras and 1.0 when told the positions** (level 1,
  room 1). What separates failure from success is working out where things are. From the cameras, in all three
  rooms the trash left the table without reaching the bin.
- **Nemotron 3.5 Super VL cannot place its hand on a handle from the cameras.** Of 154 grasps in three runs, 2
  took a tool; the other 152 closed at least 9 cm from the nearest handle, typically 40 cm or more, where the
  grasp needs 3.5 cm. Told the positions, its typical miss shrinks to 7 cm and it takes both tools, but only
  after 626 s and 843 s of the 900 s, with the bin knocked over three times.
- **Gemma 4 31B never takes the brush**, and in two rooms stops by itself after 4 minutes with the task undone.
- **Qwen3.5-9B acts a lot and uses the right tools** (130 to 263 calls, 36 grasp attempts) but its hand never
  ends within 3.5 cm of a handle.

The interface is not the obstacle: the scripted reference solves level 1 in all 30 rooms through the same tools
and the same cameras.

### Reward integrity

- **Doing nothing scores 0.0. Fetching both tools and then stopping scores 0.0.** At every level, 30 rooms
  each (`1115-0434`), and under Harbor (`1115-0522`).
- **Only the end state pays.** There are no milestone payments to collect, and the score has one bounded term.
- **The agent cannot write its own score.** It runs as an unprivileged user in its own container; the simulator
  runs in another. The verifier, as root, first takes the reward directory away from the agent, kills the
  agent's processes, empties the directory, then reads the score from the simulator. If anything fails it
  grades 0.
- **Two red-team passes** (`1114-1936`, `1114-2319`), with attacks that were run, not only code that was read.
  The second pass found three things; all are fixed, and the checks are in `probes/redteam/sweep/`:
  1. A process loop in the agent's container kept writing the reward file and got 1.0 in 3 of 3 runs. After
     the fix: 0.0.
  2. The bin pressed down onto a flat piece of trash counted as "in the bin" in 5 of 30 rooms. After the fix:
     0.0 in all 30.
  3. A blocked move named the object it touched ("against remote 1"), which told the agent what an unseen
     thing was. Now it says "a loose object".
- Known and not covered by the red team: malformed and concurrent MCP calls through a live client, and
  tipping-and-righting or scooping with the bin.

### Craft

- The rules follow the setting: a tidy-up job has a cost for binning someone's keys, a tipped bin spills, and
  loose things pushed off a table fall where the physics puts them.
- Every room is generated from a seed. The same seed, level and calls give the same score and robot time.
- Each run leaves the scorer's details and a call log from which the episode can be replayed in the simulator:
  `python probes/sweep/viewer/replay_log.py <folder>/verifier/commands.json`.
- Simplifications to know about: taking a tool is assisted (it attaches when the hand closes on the handle
  within 3.5 cm, palm down); the sweeping itself is contact physics. The base slides under position control;
  wheels are not simulated. Sofa and jacket are rigid. Details: [`probes/sweep/README.md`](probes/sweep/README.md).

### Training a smaller model (stretch goal)

Qwen3.5-9B fine-tuned for 24 minutes on 232 reference episodes still scores 0.0 at level 1, room 1 (standard),
but now takes the brush and the bin on the first grasp and runs the whole procedure in 3 minutes; untrained it
held no tool (`1115-0241`, one room, one run). Code: [`training/`](training).

## What is in this repo

| Path | What |
|---|---|
| `probes/sweep/` | The Harbor task: instruction, simulator and MCP server, verifier, scripted reference |
| `eval/run_eval.py` | The one-command evaluation |
| `results/` | Result summaries, call logs and five full Harbor trial folders |
| `coord/experiments/`, `coord/decisions/` | The record of every run (also the failed ones) and of each design decision |
| `coord/project.md` | The project's state page |
| `training/`, `serving/` | Fine-tuning a small model on experience from the environment, and serving open models on Modal |
| `probes/redteam/` | The reward attacks and their checks |
| `probes/shapes/`, `probes/toy-mcp/`, `probes/vision-plumbing/` | Earlier and auxiliary tasks, not part of the submission |
| `docs/` | Challenge brief, harness notes, team workflow |

Built with MuJoCo, Harbor, OpenCode and MCP. Open models were served and fine-tuned on Modal; Kimi K3.1 Pro and
Nemotron ran on Verda. The robot model is the PAL TIAGo++ from MuJoCo Menagerie (Apache 2.0).
