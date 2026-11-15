# Working in this repo (team)

Moved here from the README on 15 Nov. `CLAUDE.md`, `tools/` and `.claude/` exist in the team repo only, not in the public mirror.

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
| [CLAUDE.md](../CLAUDE.md) | Instructions every agent follows: protocol, git rules, engineering rules |
| [coord/](../coord/README.md) | Tasks, experiments, messages, decisions, who is doing what |
| `tools/coord.py` | CLI for all of the above, and the board generator |
| `.claude/` | Shared settings, session-start hook, `/sync` and `/handoff`, subagents |

The board is generated from `coord/`, never edited by hand:
`python3 tools/coord.py board` writes `board/index.html` (ignored by git);
`--serve` rebuilds on every page load; `--serve --pull 60` also pulls every
minute, for a shared screen running in a spare clone.

A shared, login-protected copy of the board can be published to Cloudflare
Pages on every push; one person sets it up once: [docs/live-board.md](live-board.md).

Requirements for the coordination tooling: Python 3.9+ and git, no packages. The evaluation needs what the section at the top lists.
