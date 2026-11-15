# Harness notes: what AfterQuery gives us and what Harbor expects

Researched 2026-11-14 from public sources (Harbor docs and source, the Junction
site, the StoreBench paper), then updated the same day with the organisers'
"required stack" post (verbatim at the end of `docs/challenge.md`). There is no
separate starter kit to wait for: **the kit is public Harbor plus the rules
below.** Items marked *unconfirmed* still need a local run or a mentor's answer.

## What AfterQuery provides, and requires

| Item | What we know | Status |
|---|---|---|
| Framework | Harbor, https://github.com/laude-institute/harbor (the same project the docs at https://docs.harborframework.com describe). Our environment must be a Harbor task | Confirmed by organisers |
| Harness | OpenCode: `harbor run -p ./my-task -a opencode -m [provider/model]` | Confirmed ("urged") |
| Reward | The verifier writes **one score between 0 and 1** to `/logs/verifier/reward.txt`; partial credit welcome | Confirmed |
| Scoring skeleton | Nothing beyond the Harbor verifier convention above | Confirmed |
| Model credits | **None from AfterQuery.** Use the Google, OpenAI and Modal credits from the other sponsors. Amounts and models: not recorded yet | Confirmed; budget open |
| Mentors | Two people from AfterQuery's environments team at their booth; one is on the Junction grand jury. They are authors of StoreBench (arXiv 2610.10942), the best available guide to what they consider a good environment (see below) | Public |
| Submission | At least one Harbor run log with its score, a short README (what the agent does, why it is hard, how it is scored), a demo video with a playthrough | Confirmed |
| MCP | The original brief says the agent connects over MCP; the required-stack post does not mention it and lists only `environment/Dockerfile` | Open, see below |

Schedule from the Junction site: submissions open Sat 14 Nov 12:00, **final
submission Sun 15 Nov 10:00**, review from 10:30.

## Consequences of the organisers' post

- **The model is our choice.** With Google and OpenAI credits the candidates
  are the strongest Gemini and GPT models those credits cover. Harbor takes
  `google/<model>` or `openai/<model>` and reads the key from the host
  environment (`harbor run --dry-run` shows what resolves). Pick one as the
  headline "frontier agent", record it in every experiment, and if budget
  allows run a second provider to show the gap is not one model's quirk.
- **Budget decides episode length.** Cost per agent run times (3 runs per
  evaluation times every iteration of the design) has to fit the credits, so
  measure cost on the first toy run before fixing the horizon.
- **Modal is for the post-training experiment**, which the organisers now name
  among the things they are looking for. peter's laptop has only a 4 GB GPU, too
  small to train on.
- **Reward is a single float.** Use `reward.txt`, not `reward.json`: one number,
  clipped to 0..1. Sub-scores go into the log for our analysis, not the reward file.
- **Sidecar or single container is open.** The post lists
  `environment/Dockerfile` only. Harbor also accepts
  `environment/docker-compose.yaml`, which is what a separate MCP server
  container needs, and it runs with the same `harbor run` command on local
  Docker. Unknown: whether the judges' machine or sandbox supports it. Ask
  before building on it. The fallback inside one container: run the simulator
  as a different OS user from the agent (`[agent] user` in `task.toml`) so the
  agent cannot read or write its state, and have the verifier run as root.
  Whoever takes `starter-kit-harness` should test both.

## Confirmed on peter's laptop, 14 Nov (Harbor 0.26.0 from PyPI, source read)

- Install without admin rights: `python3 -m venv .venv && .venv/bin/pip install "harbor[modal]"` (needs Python 3.12+). `.venv/` is git-ignored. `harbor run --env-file .env` loads keys.
- **No local Docker is needed if we run on Modal**: `harbor run ... -e modal`. Harbor's Modal backend also runs multi-container tasks (it starts Docker inside the Modal sandbox and runs our compose file there), so the sidecar layout works both locally and on Modal.
- **A timed-out agent is still graded.** `AgentTimeoutError`, a non-zero agent exit and a blown context window all have the policy "do not retry, grade, reward is valid". So whatever state the simulator is in when the agent stops, for any reason, is what gets scored. That is exactly stop-early behaviour, and the reward must handle it.
- `-a nop` really does nothing (empty setup and run), then the verifier runs.
- Gemini keys: Harbor accepts `GOOGLE_API_KEY`, `GEMINI_API_KEY` or `GOOGLE_GENERATIVE_AI_API_KEY`; model string `gemini/<id>` or `google/<id>`.
- The `codex` agent (not `opencode`) can log in with a ChatGPT account file: `CODEX_AUTH_JSON_PATH` pointing at `~/.codex/auth.json`. This matters because the OpenAI sponsor credits are Codex usage credits, not API credits.
- **OpenAI-compatible endpoints (Verda): never name the provider `openai`.** With `-m openai/<model>` OpenCode uses the Responses API and dies with `t.responses is not a function`. Use any other provider name plus the three override flags:
  `-m verda/kimi-k3-1-pro --base-url https://inference.verda.com/v1 --api-key-name VERDA_API_KEY --api-format openai_chat_completions`. Verified end to end on Modal (toy task, reward 1.0).
- **Featherless** (small open models, e.g. Qwen 3) is the same pattern: `-m featherless/Qwen/Qwen3-8B --base-url https://api.featherless.ai/v1 --api-key-name FEATHERLESS_API_KEY --api-format openai_chat_completions`, or simply `python3 eval/run_eval.py --provider featherless`. Featherless ids contain a slash; Harbor and OpenCode split `-m` at the first slash only (checked in Harbor 0.26.0: provider `featherless`, model `Qwen/Qwen3-8B`). Do not name the provider `featherless_ai`: LiteLLM knows that name and Harbor would then take a different key path. Caveats from the Featherless docs (14 Nov): native `tool_calls` only for the Qwen 3 family and Kimi K2, other models will not drive OpenCode; context windows are 4K to 32K on the cheap plan, too small for OpenCode's prompt, so pick a 32K+ model (`python3 eval/featherless_models.py` lists them); concurrency is a unit budget (models up to 16B cost 1 unit, up to 35B cost 2, up to 72B cost 4; the Chat plan has 4 units, over budget is HTTP 429), so keep `--parallel` within it. Not yet verified end to end.
- **Context window vs. OpenCode episode length** (measured on 21 Kimi trajectories, 14 Nov): the first request is 7-9K prompt tokens, full tabletop episodes peak at 30-74K (median about 40K). Harbor registers a custom provider's model with no `limit`, so OpenCode does not compact the history; when the prompt outgrows the window the provider refuses the request, OpenCode exits and Harbor grades the half-done state, which looks like stop-early. `eval/context_check.py` refuses too-small models before a run and flags such runs after it (`python3 eval/context_check.py runs/eval/<job>` for old runs). A 32K Qwen will likely be cut off in most episodes; a 128K variant avoids it.
- OpenCode reports cost 0 for such providers; compute cost from the token counts in `result.json`.
- `harbor view` serves a browser for trajectories: useful for the failure analysis and the demo video.
- Useful flags: `-k` attempts, `-n` concurrency, `-o` jobs dir, `--agent-timeout-multiplier`, `--ak key=value` agent options, `--ek key=value` environment options.

## Harbor in one page

Install: `uv tool install harbor` (or `pip install harbor`), needs Docker.

A task is a directory:

```
task.toml              config: timeouts, resources, MCP servers
instruction.md         the prompt the agent gets
environment/           Dockerfile for the agent container, or docker-compose.yaml for several
solution/solve.sh      what the `oracle` agent runs  -> our reference run
tests/test.sh          the verifier; must write the reward file
```

Run: `harbor run -p <task-dir> -a <agent> -m <provider/model> -k <attempts> -n <concurrent> -o <jobs-dir>`.

The judging protocol maps onto built-in agents:

| Judges rerun | Harbor |
|---|---|
| Reference run | `-a oracle`: uploads `solution/` and executes `solve.sh` in the environment |
| Three agent runs | `-a opencode -m <model> -k 3` |
| Do-nothing baseline | `-a nop`: setup and run are both empty, then the verifier runs |
| Stop-early baseline | No built-in. *unconfirmed* how the standard harness does it: ask |

### MCP

Declared in `task.toml`; OpenCode gets it written into `~/.config/opencode/opencode.json` automatically:

```toml
[[environment.mcp_servers]]
name = "env"
transport = "streamable-http"      # default is "sse"; stdio also possible
url = "http://mcp-server:8000/mcp"
```

The server runs as a sidecar in `environment/docker-compose.yaml`. Harbor
reserves the service name `main` for the agent container; other services share
its network and are reached by service name. The upstream example to copy is
`examples/tasks/hello-mcp` (FastMCP, `mcp.run(transport="streamable-http",
host="0.0.0.0", port=8000)`, healthcheck, `main.depends_on` the sidecar).

### Reward

- `tests/` is uploaded after the agent finishes; `test.sh` must write our one
  score, a number from 0 to 1, to `/logs/verifier/reward.txt` (required by the
  organisers). Harbor also knows `reward.json` with named metrics and would
  prefer it if both existed, so do not write it.
- By default the verifier runs **in the agent's container** ("shared").
  `[verifier] environment_mode = "separate"` runs it in a fresh copy instead.
- `harbor-rewardkit` is an optional helper that writes `reward.json`; it does
  not fit the single-number rule, so we do not need it.
- `[agent] timeout_sec` and `[verifier] timeout_sec` are separate. *unconfirmed*:
  whether the verifier still runs and records a reward after an agent timeout.

### Agent under test

OpenCode is installed into `main` with npm and started as
`opencode --model=<provider/model> run --format=json --thinking --dangerously-skip-permissions -- <instruction>`.
Consequences:

- It keeps its built-in tools (shell, file editing) besides our MCP tools, all
  auto-approved. **The agent can write and run code**, including scripts that
  call our MCP server over HTTP in a loop.
- One instruction, one run: the episode ends when OpenCode decides it is done.
- A trajectory is written (`agent/trajectory.json`, ATIF format) with token and
  cost counts. This is our raw material for the failure analysis.
- Model string is LiteLLM style (`anthropic/...`, `openrouter/...`); keys are
  read from the host environment. `harbor run --dry-run` shows what resolves.

## What this means for our design

0. **Tested 14 Nov: with Harbor's defaults the agent can fake any score**, even with the
   state in a sidecar (`coord/experiments/1114-0350-*`). As root it can redirect
   `env-server` in `/etc/hosts` to a fake; as any user it can leave a process
   that overwrites `/logs/verifier/reward.txt` after the grader, or plant
   `reward.json`, which Harbor prefers. The layout that held is in
   `probes/toy-mcp`: `[agent] user = "agent"`, verifier as root, and a `test.sh`
   that first kills the agent's processes (via `/proc`, the slim image has no
   `pkill`), then empties `/logs/verifier`, then reads the score from the
   sidecar. Copy that layout into every task we ship.
1. **State and score must live in the sidecar, never in `main`.** The agent has
   a root shell in `main` and the default verifier runs there afterwards, so
   anything in `main` (files, even the `curl` or `python` the verifier uses) can
   be tampered with. The upstream MCP example grades a file in `main`; do not
   copy that part. The verifier should fetch the final score from the sidecar,
   and we need to test whether a `separate` verifier can still reach it.
2. **The sidecar's HTTP surface is the attack surface.** The agent can call any
   endpoint directly, open parallel sessions, and retry. So: no reset tool, no
   debug or admin routes, one global episode per container, the seed passed by
   environment variable and never shown, scoring endpoint read-only or terminal.
3. **Anything a solver script can crack, the agent can crack**, because it can
   write that script. Difficulty has to survive scripting: metered actions
   (reads cost budget too), hidden state that only play reveals, delayed
   consequences. See the candidate comparison in `coord/tasks/choose-setting.md`.
4. **Meter time in actions, not seconds**, and give a generous wall-clock
   timeout. "Impossible timing" scores zero on difficulty, and model latency
   must not change the result.
5. **Keep `main` trivial** (a small image, nothing of ours in it) so builds are
   fast and there is nothing to find there.

## What StoreBench tells us about the judges

StoreBench is a commerce environment by the mentors: an agent runs an online
store through 29 MCP tools for 30 to 365 simulated days. Headline: on the short
tasks no frontier model matched a simple scripted operator (scripted 0.76 mean
score, 97% pass; best model 0.70, 49% pass; human experts 0.71). Design choices
they are likely to look for in ours:

- **Scripted anchors calibrate the score**: do-nothing (0.00), "attends but
  never acts", a naive "does everything, decides nothing" policy, a rule-based
  clerk, a smart heuristic, and an **exploiter** that plays every known exploit
  and must score below every honest policy.
- **Graded from terminal state only**, after a settlement pass that charges for
  everything left undone. Deterministic, no LLM judge. Quitting early does not
  shrink the denominator.
- **Each tool call costs one operation** from a per-period budget, reads
  included; the world advances when the budget is spent.
- **Events arrive on three channels**: announced, rumoured, and silent (only the
  agent's own data reveals it).
- **Exploit loop**: find it, fix it in the world model, pin it with a regression
  test, add it to the exploiter.
- **Reproducibility**: fixed world seeds, three attempts per cell, a manifest
  with commit and image digest; a missing artifact grades as zero.

Failure modes they report, which are the decisions we can design for:
under-investing (26% of trials stocked out; in 60 the agent never placed a
purchase order), declaring the job finished halfway, waiting on a background
process that does not exist, and shell batches acting on stale state.

A caution from the same paper: on the year-long task **without** shocks and
with a coding harness, four frontier models beat the scripted operator. Long
horizon alone did not produce a gap; scarce operations plus hidden events did.

## Questions for the mentors

Answered by the organisers' post: where the kit is (public Harbor), the reward
format (one float in `reward.txt`), credits (none from them).

1. May the task use `environment/docker-compose.yaml` with the simulator in a second container, or must it be a single Dockerfile? Where do the judges run it (local Docker, or a cloud sandbox)?
2. Which model do the judges use for the three agent runs, given that credits now differ per team?
3. How are do-nothing and stop-early run? (`-a nop` exists in Harbor; stop-early has no built-in.)
4. Is the reference run the `oracle` agent executing `solution/solve.sh`, and may it be a scripted policy that uses only the agent's own tools?
5. Are the three agent runs on one seed or several? May the submission be several tasks?
6. Is MCP still expected, or is any Harbor task fine?
7. Which agent timeout do they use?

## Images for a model on a custom endpoint (14 Nov, experiment `1114-1415`)

**Every run with Kimi (or any model reached through `--base-url`) must declare image input, or the model never sees a
camera picture:** OpenCode does not know a custom model's abilities and replaces each image with the text
`ERROR: Cannot read image (this model does not support image input)`. The run then looks like an agent that
ignores its camera. Three places make sure this cannot be forgotten:

1. `eval/run_eval.py` adds the declaration to every agent run with the `verda` preset (`--images auto`).
2. A hand-written `harbor run` needs this flag (single quotes as written):

   ```
   --ak 'opencode_config={"provider":{"verda":{"models":{"kimi-k3-1-pro":{"attachment":true,"modalities":{"input":["text","image"],"output":["text"]}}}}}}'
   ```
3. A task whose tools return pictures carries the declaration in its agent image, so a run started without the
   flag still works. In the agent Dockerfile: `COPY opencode-models.json /etc/opencode/models.json` and
   `ENV OPENCODE_CONFIG=/etc/opencode/models.json`, the file holding the same JSON as in point 2. OpenCode merges it
   over the config Harbor writes. Verified 14 Nov on the plumbing probe: 9 of 9 shapes read with no flag on the command.

Models from OpenCode's own registry (Gemini, Claude, GPT) need nothing. A text-only model must not be declared
as taking images.
