---
title: Toy MCP task: OpenCode with Kimi K3.1 Pro (Verda) on Modal
status: done
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-14T03:40+02:00
finished: 2026-11-14T03:48+02:00
commit: b36ca8f
command: .venv/bin/harbor run -p probes/toy-mcp -a opencode -m openai/kimi-k3-1-pro --base-url https://inference.verda.com/v1 --api-key-name VERDA_API_KEY --api-format openai_chat_completions --env-file .env -e modal -o runs/toy --job-name opencode-kimi-1
headline: OpenCode + Kimi (Verda) on Modal: 1.0 on the toy task; provider must not be named openai
---

## Hypothesis

First model-driven trial. Does OpenCode connect to the MCP sidecar, call the tools, and leave a trajectory? Expect reward 1.0 on the toy counter. Also measures cost and wall time of the agent path.

## Setup

Exact command, seeds, model, env commit - enough for a teammate to rerun it.

## Results

## Takeaways

## Results

- First attempt (`-m openai/kimi-k3-1-pro`): reward 0.0, `NonZeroAgentExitCodeError`. OpenCode died before its first step with `t.responses is not a function`: with the provider named `openai`, OpenCode uses the Responses API, which an OpenAI-compatible endpoint does not offer. Not a model failure.
- Second attempt (`-m verda/kimi-k3-1-pro`, any provider name other than `openai`): reward 1.0. OpenCode connected to the MCP sidecar, called `press` five times and stopped. A trajectory (`agent/trajectory.json`) was written.

Working command (key in `.env` as `VERDA_API_KEY`):

```
.venv/bin/harbor run -p probes/toy-mcp -a opencode -m verda/kimi-k3-1-pro \
  --base-url https://inference.verda.com/v1 --api-key-name VERDA_API_KEY \
  --api-format openai_chat_completions --env-file .env -e modal -o runs/toy
```

## Takeaways

- The full agent path works: OpenCode under Harbor on Modal, model served by Verda, tools on our MCP sidecar, score read from the sidecar.
- For any OpenAI-compatible endpoint, do not call the provider `openai`.
- OpenCode reports cost 0 for this provider, so cost has to be computed from the token counts.
