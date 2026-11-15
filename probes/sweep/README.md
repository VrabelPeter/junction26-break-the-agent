# Living-room sweep (probe, branch `sweep-env`)

A wheeled two-arm robot (PAL TIAGo++ from MuJoCo Menagerie, Apache 2.0) fetches a brush and a bin
from a tool station and gets the trash, and only the trash, from a coffee table and a sofa into the
bin. Physics is MuJoCo 4.0.1 on CPU; 35 s of robot time simulate in about 2 s.

Status, 14 Nov 14:51: the scene, the tools, the scorer and a first scripted controller exist and run
in-process. There is **no Harbor task and no run with a model yet**, so no evidence of a gap.

## Settings (after the Embodied First Exam)

- **standard**: head camera in colour and depth with calibration, wrist cameras, the robot's own joint
  readings, a floor plan. No object positions, no labels, no count of the trash, no resets.
- **privileged**: the same plus position and kind of every object. For ablation and development.

## Score

`score = (trash in the bin at the end / all trash) x 0.5 ^ mistakes`, read from the simulator's
state after the world has been left alone for 2 s. A mistake is a personal item that ends in the bin
or on the floor, or the bin lying on its side. Nothing is paid for reaching or picking up the tools;
those moments are logged as milestones for the failure analysis only.

Levels: 1 = one piece of trash on the table; 2 = four pieces and two personal items; 3 = eight
pieces and four personal items on table and sofa plus a jacket. (Level 0, tools already in the
hands, is defined but not implemented.)

## Run it

Needs `mujoco==4.0.1`, `numpy`, `pillow`; rendering needs `MUJOCO_GL=egl` (or `osmesa`).

```bash
cd probes/sweep/environment/env-server
python -m sweep.run --seeds 1 2 3 --level 1 -v      # do_nothing, stop_early, reference_privileged
```

In-process numbers on `main` d1e3191, 15 Nov 04:34, rooms (seeds) 1 to 30, no model (experiment `1115-0434`,
per-room values in `results/sweep/reference-inprocess-d1e3191-1115-0434.json`).

The reference that judges compare against works from the cameras, as the agent must (**standard** setting;
`reference`, the default oracle): `python -m sweep.run --policy reference --seeds 1 2 3 --level N`

| Level | Mean score | Rooms at 1.0 | Lowest | Rooms with a mistake | Robot time, mean (max) |
|---|---|---|---|---|---|
| 1 | 1.000 | 30 of 30 | 1.0 | 0 | 114 s (158 s) |
| 2 | 0.750 | 8 of 30 | 0.0 (room 13) | 0 | 256 s (320 s) |
| 3 | 0.496 | 0 of 30 | 0.0 (room 25) | 1 (room 25, bin tipped over) | 396 s (522 s) |

The scripted controller told the object positions (**privileged** setting; `reference_privileged`):

| Level | Mean score | Rooms at 1.0 | Lowest | Rooms with a mistake | Robot time, mean (max) |
|---|---|---|---|---|---|
| 1 | 1.000 | 30 of 30 | 1.0 | 0 | 71 s (115 s) |
| 2 | 0.908 | 23 of 30 | 0.0 (room 13) | 0 | 216 s (443 s) |
| 3 | 0.869 | 11 of 30 | 0.3125 (room 19) | 1 (room 19, glasses on the floor) | 364 s (480 s) |

So from the cameras the reference is flawless at level 1 and leaves trash behind at levels 2 and 3, more than when
it is given positions; it makes a mistake in 1 of 90 rooms (the bin tipped over in room 25 at level 3).

Do nothing and fetch-the-tools-then-stop score 0.00 at every level (30 rooms each, same run). What the reference leaves behind is mostly
trash with a personal item so close that no stroke or sideways push is clear of it; it skips those pieces
rather than risk the item. How it works: the docstring of `sweep/policies.py`.

## Run it as a teammate (any model)

Setup once: `python3 -m venv .venv && .venv/bin/pip install "harbor[modal]"`, Docker, and the model key in `.env`
(copy `.env.example`). Then, from the repo root:

```bash
python3 probes/sweep/models.py                                   # the models, and whether their key is set
python3 probes/sweep/smoke.py --model kimi                       # quick checks; must pass before any long run
python3 probes/sweep/run_agent.py --model kimi --seeds 1 2 3 --parallel 3      # full runs (a person starts these)
python3 probes/sweep/run_agent.py --model nemotron --setting privileged --level 2 --seeds 1
python3 probes/sweep/report.py --write                           # table of all recorded runs
python3 eval/run_eval.py --task probes/sweep --level 1 --seeds 1 2 3 [--provider verda|nemotron] [--skip-agent]
```

- **Models** are the entries of `models.json` (now: `kimi` = Kimi K3.1 Pro on Verda, key `VERDA_API_KEY`;
  `nemotron` = Nemotron 3.5 Super VL, key `VERDA_INFERENCE_KEY`). To add one, add an entry, run
  `python3 probes/sweep/models.py --write` (it regenerates the OpenCode config baked into the agent image) and
  smoke test it. Any OpenAI-compatible endpoint that takes pictures works.
- **Run names** start with your coordination handle (`frederik-kimi-standard-l1-s2-1114-1930`), so two people
  can run at the same time. The full Harbor trial stays in `runs/sweep/` (not committed); a summary, the scorer's
  details and the logged tool calls are copied to `results/sweep/agent-runs/`: commit and push those.
- `eval/run_eval.py` is the one-command evaluation: reference, do-nothing, stop-early and three agent runs.

## Under Harbor

The task directory is `probes/sweep`: `instruction.md`, `task.toml`, `environment/` (agent container, and
the simulator with its MCP server in the `env-server` sidecar), `tests/test.sh` (hardened grader: reads
the score from the simulator), `solution/solve.sh` (scripted controllers through MCP).
Seed, level and setting are environment variables read by the sidecar: `SWEEP_SEED` (1), `SWEEP_LEVEL`
(1), `SWEEP_SETTING` (`standard` or `privileged`, default `standard`).

```bash
H=.venv/bin/harbor
$H run -p probes/sweep -a nop -o runs/sweep/nop                                              # do nothing
$H run -p probes/sweep -a oracle --ae SWEEP_POLICY=stop_early -o runs/sweep/stop_early     # fetch the tools, then stop
$H run -p probes/sweep -a oracle -o runs/sweep/reference                                    # scripted reference, from the cameras
SWEEP_SETTING=standard $H run -p probes/sweep -a opencode -m verda/kimi-k3-1-pro \
  --base-url https://inference.verda.com/v1 --api-key-name VERDA_API_KEY \
  --api-format openai_chat_completions --env-file .env -o runs/sweep/kimi \
  --ak 'opencode_config={"provider":{"verda":{"models":{"kimi-k3-1-pro":{"attachment":true,"modalities":{"input":["text","image"],"output":["text"]}}}}}}'
```

The scripted reference and the stop-early baseline work in the standard setting: they look through the head
camera first (`SWEEP_POLICY=reference_privileged` is the variant that reads object positions). The cameras are rendered in software (OSMesa) in the sidecar: 0.22 s for a 640x480
colour and depth frame on two cores. The agent image carries Node and OpenCode, and declares image
input for the Verda model in `/etc/opencode/models.json`.

Checks without Docker: `MUJOCO_GL=egl python -m pytest probes/sweep/checks -q` (or call the functions).
A logged episode can be repeated in-process: `python probes/sweep/viewer/replay_log.py <trial dir>`.
`solution/sweep/` holds copies of `scene.py` and `policies.py`; refresh them after editing the originals.

## Look at it

```bash
MUJOCO_GL=egl python probes/sweep/viewer/dashboard.py -o runs/sweep/dashboard.html
```

One self-contained page: the room at each level and what the head camera returns, a picker of end
states with the scorer's number for each, and one rollout step by step.

## Files

```
environment/env-server/sweep/scene.py     room, tools, objects, robot model (MJCF is generated)
environment/env-server/sweep/sim.py       World: tool calls, cameras, milestones, score
environment/env-server/sweep/policies.py  do_nothing, stop_early, stop_after_one, reference_privileged
environment/env-server/sweep/run.py       in-process runner
environment/env-server/assets/pal_tiago_dual/   the robot model and meshes
viewer/dashboard.py, dashboard.template.html
```

## Deviations from the Menagerie robot file

- The base slides and turns on the floor under position control; the wheels are not simulated.
- The right arm's third joint gets the left arm's range. The file's two ranges are not mirror
  images although the same joint values put the arms in mirrored postures, which left the right
  arm unable to take most palm-down poses.
- A head camera, two wrist cameras and a grasp point between the fingers of each hand were added.

## Simplifications to know about

- Taking a tool is assisted: it attaches when the hand, palm down, closes on the handle. Sweeping
  itself is contact physics.
- Sofa and jacket are rigid.
