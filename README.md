# Break the Agent

Junction 2026, AfterQuery challenge: a reinforcement-learning environment where
frontier agents fall short for real reasons. Brief and rubric: [docs/challenge.md](docs/challenge.md).

## Run the evaluation

> Draft, 14 Nov. **The environment is being replaced.** The kitchen-tabletop and Ethernet-insertion tasks
> were removed on 14 Nov (neither produced a gap). The environment under construction is the living-room
> sweep on branch `sweep-env` (`probes/sweep`); the command below takes the task directory with `--task`
> until that lands on `main`. The final README text should be written by a person on the team.

Setup, once (Python 3.12+, Docker):

```bash
python3 -m venv .venv && .venv/bin/pip install "harbor[modal]"
cp .env.example .env        # then put the model key in; not needed for --skip-agent
```

One command, standard harness (`harbor run -p <task> -a <agent>` for every run):

```bash
python3 eval/run_eval.py --task probes/shapes                 # reference run, three agent runs, do-nothing, stop-early
python3 eval/run_eval.py --task probes/shapes --skip-agent    # the same without a model
```

It prints one row per kind of run and one column per seed, and writes `results/eval-<time>.json`.
The agent model is set with `EVAL_MODEL` and friends (see the top of `eval/run_eval.py`); the default is
Kimi K3.1 Pro on Verda's OpenAI-compatible endpoint, with the key in `.env` as `VERDA_API_KEY`.
`--provider featherless` runs a small open model (Qwen3-8B by default, `--model featherless/<id>` for another)
on Featherless instead, with the key as `FEATHERLESS_API_KEY`. Runs cut off by a small model's context window are
detected and reported separately, never counted as agent failures (`eval/context_check.py`).
`--env modal` runs everything on Modal instead of local Docker.

Pictures and replays of the environments: the board's Environment tab, https://junction-board.pages.dev/environment (source: `visuals/`).

## Results

> Filled in from the latest eval experiment in `coord/experiments/`. No result is reported here yet:
> see `coord/project.md` for the honest state, including that a gap is not established.

## For the team: working in this repo

Each of us works with our own Claude Code in our own clone. The agents
coordinate through files in `coord/`, which they commit and push; there is no
other channel, so `git pull` is how your agent hears from the others.

```bash
git clone <repo-url> && cd junction_hack
echo yourname > .coord-handle          # short, stable handle (optional: defaults to git user.name)
python3 tools/coord.py status          # what is going on
python3 tools/coord.py board --serve   # live board on http://127.0.0.1:8765
claude                                 # start your agent; it reads CLAUDE.md and the status digest
```

Then tell your agent what to work on, or let it pick from the board. Useful
things to say:

- `/sync` - pull, catch up on what the other agents did and said, suggest what to take.
- `/handoff` - write down state, push everything, so another agent can continue.
- "Claim `<task>` and do it", "Post a message to all: ...", "Register and run the eval".

What lives where:

| Path | What |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Instructions every agent follows: protocol, git rules, engineering rules |
| [coord/](coord/README.md) | Tasks, experiments, messages, decisions, who is doing what |
| `tools/coord.py` | CLI for all of the above, and the board generator |
| `.claude/` | Shared settings, session-start hook, `/sync` and `/handoff`, subagents |

The board is generated from `coord/`, never edited by hand:
`python3 tools/coord.py board` writes `board/index.html` (ignored by git);
`--serve` rebuilds on every page load; `--serve --pull 60` also pulls every
minute, for a shared screen running in a spare clone.

A shared, login-protected copy of the board can be published to Cloudflare
Pages on every push; one person sets it up once: [docs/live-board.md](docs/live-board.md).

Requirements for the coordination tooling: Python 3.9+ and git, no packages. The evaluation needs what the section at the top lists.
