---
title: Plumbing: does an image returned by an MCP tool reach Kimi through OpenCode under Harbor
status: done
kind: probe
owner: peter
host: peter-LENOVO
started: 2026-11-14T14:15+02:00
finished: 2026-11-14T14:33+02:00
commit: da5e16c
command: harbor run -p probes/vision-plumbing -a opencode -m verda/kimi-k3-1-pro (flags and the opencode_config in Setup)
headline: Images reach Kimi through MCP and through read, 9 of 9 shapes correct, but only with the model's image input declared in the OpenCode config (0 of 9 without)
---

## Hypothesis

Hypothesis: with the model's image input declared in the OpenCode config, an image returned by an MCP tool (or read from disk with OpenCode's read tool) reaches kimi-k3-1-pro on Verda. Test: toy MCP server with a tool that returns a generated picture of three coloured shapes; the agent has to write what it sees to a file. Direct API call already works (shapes located to about 10 px).

## Setup

Probe `probes/vision-plumbing` (on branch `sweep-env`): a sidecar MCP server draws three coloured shapes per picture (seed in `VISION_SEED`); the agent has to report colour and shape from left to right for three pictures, one per route. Local Docker, OpenCode 1.19.5, model `verda/kimi-k3-1-pro`, seed 1.

```
harbor run -p probes/vision-plumbing -a opencode -m verda/kimi-k3-1-pro \
  --base-url https://inference.verda.com/v1 --api-key-name VERDA_API_KEY \
  --api-format openai_chat_completions --env-file .env -o runs/vision-plumbing \
  --ak 'opencode_config={"provider":{"verda":{"models":{"kimi-k3-1-pro":{"attachment":true,"modalities":{"input":["text","image"],"output":["text"]}}}}}}'
```

## Results

| Run | MCP tool returns an image | MCP tool returns JSON text and an image | curl to a file, then OpenCode `read` | Score |
|---|---|---|---|---|
| With the image declaration (`--ak opencode_config=...`) | 3 of 3 shapes | 3 of 3 | 3 of 3 | 1.0 |
| Without it | "cannot see" | "cannot see" | "cannot see" | 0.0 |

- Without the declaration OpenCode replaces the picture with `ERROR: Cannot read image (this model does not support image input)`.
- A 320x240 picture costs on the order of 100 tokens; a run cost about 0.03 USD.
- Not tested: larger pictures, several pictures in one result, depth images.

## Takeaways

- Camera images can be given to the agent as MCP tool results. For a custom provider the image input has to be declared in the OpenCode config; models from OpenCode's own registry (Gemini, Claude, GPT) need nothing.
- FastMCP 2.12.4: an image alone is `return Image(data=png, format="png")`. Text plus image needs `@mcp.tool(output_schema=None)` and `ToolResult(content=[TextContent(...), Image(...).to_image_content()])`.
- Harbor downloads Node and OpenCode into the agent container on every run; on the venue network that hit the 360 s setup timeout twice. Preinstalling them for the `agent` user in the task's Dockerfile makes Harbor skip the download (a whole run then takes 39 s). Worth doing in every task.
- Both good runs ended with `NonZeroAgentExitCodeError` (OpenCode printed `EPIPE` after a bash curl call); they were graded normally. Cause not determined.
