---
name: Break the Agent
tagline: Junction 2026 · AfterQuery challenge · an RL environment where frontier agents fall short for real reasons
deadline: 2026-11-15T10:00+02:00
---

## Concept

The submission environment is the **living-room sweep, seen through the robot's cameras** (decision
`1114-we-commit-to-the-living-room-sweep-...`). A wheeled two-arm robot (PAL TIAGo++ in MuJoCo) fetches a brush
and a bin from a tool station and gets the trash, and only the trash, from a coffee table and a sofa into the bin.

- **Standard setting:** the agent gets what the robot's sensors give: the head camera in colour and depth with its
  calibration, wrist cameras in colour, and the robot's own joint readings. No object positions, no labels, no
  resets, and no tool that turns a pixel into a position.
- **Privileged setting** (ablation): the agent is also told the position and kind of every object.
- **Levels:** 1 = one piece of trash on the table; 2 = four pieces and two personal items; 3 = eight pieces and
  four personal items on table and sofa, plus a jacket.
- **Score**, from the simulator's final physical state: `trash in the bin / all trash x 0.5 ^ mistakes` (a mistake
  is a personal item in the bin or on the floor, or the bin tipped over). Nothing is paid for milestones.

Code: `probes/sweep` on `main` (read its README). The build is the latest commit on `main` (decision
`1114-no-build-tags-...`). Pictures, films and replays: the Environment page, https://junction-board.pages.dev/environment.html.

## State (15 Nov, 06:00)

Every number below is from a finished experiment in `coord/experiments/`; what is done and what is open is in
"Where it stands" further down this page.

Scripted runs and baselines, rooms 1 to 30 in-process (experiment `1115-0434`); level 1 also under Harbor (`1115-0522`):

| Run | Setting | Level 1 | Level 2 | Level 3 |
|---|---|---|---|---|
| Reference | standard | 1.00 | 0.75 | 0.50 |
| Scripted controller | privileged | 1.00 | 0.91 | 0.87 |
| Do nothing | - | 0.0 | 0.0 | 0.0 |
| Fetch the tools, then stop | - | 0.0 | 0.0 | 0.0 |

Model runs through Harbor and OpenCode, rooms 1 to 3 unless stated:

| Model | Setting | Level 1 | Level 2 | Level 3 | Experiments |
|---|---|---|---|---|---|
| Claude Fable 5.2 (effort medium) | standard | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 0.875 | `1115-0545`, `1115-0206`, `1115-0242` |
| GPT-6 Astra | standard | 1.0 / 1.0 / 0.0 | 0.25 / 1.0 / 0.75 (rooms 1 and 3 stopped by us) | 1.0 (room 1) | `1114-2242`, `1114-2303`, `1115-0048`, `1115-0143` |
| GPT-6 Astra | privileged | 1.0 (room 1) | - | - | `1114-2242` |
| Kimi K3.1 Pro | standard | 0.0 / 0.0 / 0.0 (stopped by us at 40 min, not clean) | - | - | `1114-1933` |
| Kimi K3.1 Pro | privileged | 1.0 (room 1) | - | - | `1114-1933` |
| Nemotron 3.5 Super VL | standard | 0.0 / 0.0 / 0.0 | - | - | `1114-2218` |
| Nemotron 3.5 Super VL | privileged | 0.0 (room 1) | - | - | `1114-2218` |
| Gemma 4 31B | standard | 0.0 / 0.0 / 0.0 | - | - | `1114-2116` |
| Gemma 4 31B | privileged | 0.0 (room 1) | - | - | `1114-2116` |
| Qwen3.5-9B | standard | 0.0 / 0.0 / 0.0 (stopped by us at 24 min) | - | - | `1114-2141` |
| Qwen3.8-27B | standard | 0.0 / 0.0 / 0.0 (stopped by us at 25 min) | - | - | `1114-2141` |

- **The two strongest models solve the task from the cameras at every level they ran**, and score above our
  reference at levels 2 and 3. Against them there is no gap.
- **The other models score 0.0 at level 1**, where the reference scores 1.0.
- **Variant without a shell** (level 1, room 1, standard): GPT-6 Astra 0.0 (stopped by us), Claude Fable 5.2 1.0
  (`1115-0208`, `1115-0513`).
- **Reward integrity:** two red-team passes. The second found two exploits and one leak, all fixed; baselines are
  0.0 after the fixes (`1114-1936`, `1114-2319`).
- **Training a smaller model:** Qwen3.5-9B fine-tuned on 232 reference episodes still scores 0.0 at level 1 room 1
  (standard), but now takes brush and bin on the first grasp; untrained it held no tool (`1115-0241`). Two further
  training runs are running (`1115-0409`, `1115-0448`).

How anyone runs it: `probes/sweep/README.md`, section "Run it as a teammate". Rules: smoke test before any long or
paid run; long runs are started by a person.

## Earlier environments

Dropped because the agent was given exact numbers (positions, forces), and a strong model then reasons its way to
the reference's strategy. Records stay in `coord/experiments/`; the code is in git history.

- Kitchen tabletop with a Franka Panda and Ethernet plug insertion: removed 14 Nov, last commit containing them
  `98c986c` (experiments `1114-0618`, `1114-1240`).
- Metered satellite operations: no gap (experiments `1114-0346`, `1114-0404`), last commit `a1ac3bc`.
- Frederik's shape board (`probes/shapes`) stays in the repo as a second example.

## Links

- Live board (public, updates about a minute after each push to `coord/`): https://junction-board.pages.dev
- Team repo (private): https://github.com/VrabelPeter/hack_junction26
- Public repo for judges: https://github.com/VrabelPeter/junction26-break-the-agent. A mirror of the submission's files on `main` (code, results, experiments, decisions; no team tooling, no git history). Never commit to it; after pushing to `main`, run `python3 tools/publish_public.py --push` (it scans for credentials first and refuses on a hit).

## Required stack and submission (AfterQuery, 14 Nov)

- Environment = a Harbor task; played with `harbor run -p <task> -a opencode -m <provider/model>`; verifier writes one score 0..1 to `/logs/verifier/reward.txt`.
- Submit: at least one Harbor run log with its score, a short README (what the agent does, why it is hard, how it is scored), a demo video with a playthrough.
- AfterQuery gives no model credits. We use the Google, OpenAI and Modal credits from the other sponsors.
- Details: end of `docs/challenge.md`, and `docs/harness-notes.md`.

## Schedule

Submissions open Sat 14 Nov 12:00. Final submission Sun 15 Nov 10:00, review from 10:30.
