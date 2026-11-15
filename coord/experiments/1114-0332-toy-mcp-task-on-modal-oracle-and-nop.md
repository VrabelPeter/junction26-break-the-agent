---
title: Toy MCP task on Modal: oracle and nop
status: done
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-14T03:32+02:00
finished: 2026-11-14T03:34+02:00
commit: 3e9a4f9
command: .venv/bin/harbor run -p probes/toy-mcp -a oracle -e modal -o runs/toy  (then -a nop)
headline: oracle 1.0, nop 0.0 on Modal, about 1 min per trial, no local Docker
---

## Hypothesis

Does Harbor run a two-container task on Modal without local Docker, does the oracle reach the MCP sidecar, and does the verifier read the score from the sidecar? Expect oracle 1.0, nop 0.0.

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

## Takeaways

## Results

- `-a oracle`: reward 1.0, 1m09s wall, no exceptions.
- `-a nop`: reward 0.0, 1m02s wall, no exceptions.
- Ran on Modal from a laptop with no Docker installed. Both containers built inside the Modal sandbox; the reference script in `main` reached the MCP server at `http://env-server:8000/mcp`; the verifier read the score from the sidecar's `/score` route and wrote `/logs/verifier/reward.txt`.

Exact commands, from the repo root with `.venv` set up as in `docs/harness-notes.md` and a Modal token in `~/.modal.toml`:

```
.venv/bin/harbor run -p probes/toy-mcp -a oracle -e modal -o runs/toy --job-name oracle-1
.venv/bin/harbor run -p probes/toy-mcp -a nop    -e modal -o runs/toy --job-name nop-1
```

No seeds: the toy is deterministic.

## Takeaways

- The two-container layout works under Harbor on Modal; about one minute of overhead per trial for build and start.
- Not tested yet: a model-driven agent (`-a opencode`) against the sidecar, the `separate` verifier mode, and local Docker.

