# Sponsor resources: what we have and how we use it

Reviewed 2026-11-14 from the Junction platform pages and the vendors' public
docs. AfterQuery gives no credits, so everything we run is paid from these.
Prices are per million tokens, input / output. Nothing here has been run end to
end yet; items marked *check* must be verified on first use. Keys go in `.env`
(template: `.env.example`), never in the repo.

## What each sponsor gives

| Sponsor | Grant | Scope | How to claim |
|---|---|---|---|
| Google | Gemini API credits, amount not stated | **Per team**, one person fills the form; 18+ | Form on the Junction platform page |
| Modal | $100 | Per participant | Sign up, redeem, `modal token new` |
| OpenAI | 2,500 Codex usage credits (worth $100), valid 30 days | Per participant, on a personal ChatGPT account. **Not API credits** | Assigned link on the platform |
| Verda | EUR 200 | Stated as "you get EUR 200"; per team or per person not clear | Console sign-up plus a form |
| Exa | $50 search API | Per participant | Coupon on the platform page |
| Featherless | Bare-metal GPU credits | Selected teams only | Talk to them at the booth |

Per-participant grants multiply by team size: every teammate should redeem
Modal and Codex.

## How each one maps onto the work

### Google Gemini: the agent under test

| Model ID | Price | Role |
|---|---|---|
| `gemini-4-carbon` | $2 / $10 until 30 Nov | Headline "frontier agent". No free tier: *check* the credit key can call it |
| `gemini-4-argon` | $2 / $10 | Same price, described as the faster sibling |
| `gemini-4-hydrogen` | $1.50 / $7.50 | |
| `gemini-3.8-flash` | $0.75 / $3.75 | Cheap plumbing and smoke runs |

- Run as `harbor run -p <task> -a opencode -m google/gemini-4-carbon --env-file .env`.
  Harbor accepts `GEMINI_API_KEY`, `GOOGLE_API_KEY` or `GOOGLE_GENERATIVE_AI_API_KEY`.
- Thinking cannot be turned off on these models and is billed as output.
- Rate limits are per project and only visible in AI Studio: *check* before
  running three agents in parallel.
- **Gemini rejects loose MCP tool schemas** and then every request fails. In our
  MCP server give every argument exactly one explicit type: no optional/nullable
  types, no unions, no enum without a type.
- Rough cost of one episode of about 150 tool calls on Carbon: $3 to $10
  depending on how much of the growing context is cached. This is an estimate;
  measure it on the first real run and write it into the experiment file.

### Modal: where things run, and the post-training GPU

- Harbor runs trials in Modal sandboxes with `-e modal`, including our
  two-container layout, so a machine without Docker can still run everything.
  A 2-core 4 GB sandbox is about $0.38/hour: $100 is roughly 260 sandbox-hours.
  Compose images are rebuilt inside the sandbox on every start, so local Docker
  is faster for tight iteration.
- GPUs for fine-tuning: L40S $1.95/h, A10 $1.10/h, A100-80 $2.50/h.
- Modal Dojo (their training library) supports fine-tuning and RL with a custom
  reward on small Qwen models and on Gemma-4-26B. **Set GPU type and count
  explicitly**: one docs example provisions a cluster costing about $57/hour.

### Gemma: the "smaller model" for the post-training experiment

Gemma 4 comes in E2B, E4B, 12B, 26B and 31B. E2B and E4B fine-tune with LoRA on
one 24 GB GPU using the published Unsloth recipe (there is also an RL notebook
for E2B). Training Gemma on Modal with experience from our environment serves
the AfterQuery tiebreak and is eligible for both the "Best Use of Gemma" and the
"Best use of Modal" side challenges. Evaluate it in-process against the
simulator (one action per step), not through Harbor: a 4B model cannot drive
OpenCode.

### Verda: cheap open models, spare GPUs

OpenAI-compatible inference at `https://inference.verda.com/v1` with two models
live, both with tool calling: Kimi K3.1 Pro ($2 / $10) and DeepSeek V4.1 Flash
($0.15 / $0.60). Uses: nearly free plumbing runs, and a second and third model
family to show the gap is not one vendor's quirk. *Check* that OpenCode under
Harbor accepts a custom base URL. Also rents GPUs (A6000 48 GB at $0.88/h) if
Modal credit runs out.

### OpenAI Codex credits: development help, not the benchmark

- These are ChatGPT/Codex usage credits. Harbor's `opencode` agent takes API
  keys only, so **they cannot pay for the OpenCode runs the organisers ask for**.
- Harbor's `codex` agent can use them (`codex login`, then
  `CODEX_AUTH_JSON_PATH`). That is a different harness, OpenAI's docs discourage
  account logins for automation, runs must be serial, and a free ChatGPT account
  may not be allowed the stronger models. Treat it as an optional extra data point.
- Best use: Codex as an independent reward red-teamer and reviewer during
  development. A second model family hunting for exploits is useful on its own,
  and it is what the "Best Use of Codex" side challenge asks for (Codex in the
  development process).

### Exa, Featherless

No role planned. Live web search would make the environment unreproducible.
Featherless can serve a fine-tuned model only as full merged weights and only
if they grant us credits.

## Side challenges that stack on the main one

| Challenge | Prize shown | Fit |
|---|---|---|
| Best Use of Gemma | cut off in our screenshot | Strong: the post-training experiment |
| Best use of Modal | not shown | Strong: Harbor runs and training both on Modal |
| Best Use of Codex | $10k / $5k / $2.5k in API credits | Medium: Codex as red-teamer in our process |
| Best Use of Gemini API | EUR 4,000 + cloud credits / 2,000 / 1,000 | Weak: we show where Gemini fails |

Criteria for these are not published online; get them at the booths before
investing time in any of them.
