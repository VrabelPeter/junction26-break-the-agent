#!/usr/bin/env python3
"""The models that can play the sweep task, in one place: probes/sweep/models.json.

    python3 probes/sweep/models.py             # list them and say whose key is set in .env
    python3 probes/sweep/models.py --write     # regenerate environment/opencode-models.json after editing models.json

To add a model: add an entry to models.json (any OpenAI-compatible endpoint that takes pictures), run
`--write`, put its key into .env, then `python3 probes/sweep/smoke.py --model <name>`.

  provider, model     what OpenCode is given as `-m provider/model`. The provider name must not be `openai`
                      (OpenCode would use the Responses API, see docs/harness-notes.md).
  base_url, key       the endpoint and the NAME of the variable in .env that holds its key (never the key).
                      base_url null means a provider OpenCode knows natively (e.g. `anthropic`): no endpoint
                      or API-format override is passed.
  variant             optional OpenCode variant, i.e. the reasoning effort (`--ak variant=...`). For Claude
                      models OpenCode 1.19 maps it to adaptive thinking with output_config.effort.
  context, output     token limits declared to OpenCode, so it compacts the history before the window is full.
  usd_per_million     [input, cached input, output] prices, optionally a 4th: cache writes; null when not known.

environment/opencode-models.json is baked into the agent image: it declares picture input for every model
here, otherwise OpenCode replaces each picture with an error text. smoke.py refuses to run when it is stale.
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=HERE, capture_output=True, text=True).stdout.strip()
# In a Claude Code worktree the virtualenv, .env and .coord-handle live in the main checkout.
MAIN = os.path.dirname(os.path.dirname(os.path.dirname(ROOT))) if "/.claude/worktrees/" in ROOT else ROOT
HARBOR = os.path.join(MAIN, ".venv", "bin", "harbor")
ENV_FILE = os.path.join(MAIN, ".env")
BAKED = os.path.join(HERE, "environment", "opencode-models.json")
ALIASES = {"verda": "kimi"}          # the name used before 14 Nov evening

REGISTRY = json.load(open(os.path.join(HERE, "models.json")))


def names():
    return sorted(REGISTRY) + sorted(ALIASES)


def get(name):
    return REGISTRY[ALIASES.get(name, name)]


def canonical(name):
    return ALIASES.get(name, name)


def harbor_args(name):
    """The `harbor run` flags that select this model for the OpenCode agent."""
    m = get(name)
    args = ["-a", "opencode", "--env-file", ENV_FILE, "-m", f"{m['provider']}/{m['model']}"]
    if m.get("base_url"):
        args += ["--api-format", "openai_chat_completions", "--base-url", m["base_url"], "--api-key-name", m["key"]]
    if m.get("variant"):
        args += ["--ak", f"variant={m['variant']}"]
    return args


def opencode_config():
    cfg = {}
    for m in REGISTRY.values():
        cfg.setdefault(m["provider"], {"models": {}})["models"][m["model"]] = {
            "attachment": True, "modalities": {"input": ["text", "image"], "output": ["text"]},
            "limit": {"context": m["context"], "output": m["output"]}}
    return {"provider": cfg}


def baked_is_current():
    return os.path.exists(BAKED) and json.load(open(BAKED)) == opencode_config()


def keys_set():
    """Names of the variables that have a value in .env. Values are never read into anything else."""
    found = set()
    if os.path.exists(ENV_FILE):
        for line in open(ENV_FILE):
            name, eq, value = line.strip().partition("=")
            if eq and not name.startswith("#") and value.strip().strip("\"'"):
                found.add(name.strip().removeprefix("export ").strip())
    return found


def handle():
    """Who is running: the coordination handle, so two people's runs never share a name."""
    p = os.path.join(MAIN, ".coord-handle")
    if os.path.exists(p):
        return open(p).read().strip() or "anon"
    who = subprocess.run(["git", "config", "user.name"], cwd=HERE, capture_output=True, text=True).stdout.strip()
    return "".join(c for c in who.lower() if c.isalnum()) or "anon"


def docker_wrap(cmd):
    """Run `cmd` so that it can reach Docker. On a machine where the shell is not yet in the `docker` group
    (peter's laptop) the command goes through `sg docker`; everywhere else it runs as it is."""
    if subprocess.run(["docker", "ps"], capture_output=True).returncode == 0:
        return cmd
    return ["sg", "docker", "-c", " ".join("'" + c.replace("'", "'\\''") + "'" for c in cmd)]


if __name__ == "__main__":
    if "--write" in sys.argv:
        json.dump(opencode_config(), open(BAKED, "w"), indent=1)
        print("wrote", os.path.relpath(BAKED, ROOT), "- the agent image rebuilds on the next run")
        sys.exit(0)
    have = keys_set()
    for n in sorted(REGISTRY):
        m = REGISTRY[n]
        price = "price not known" if not m["usd_per_million"] else "USD per million tokens in/cached/out: " + "/".join(map(str, m["usd_per_million"]))
        print(f"{n:10s} {m['label']:42s} key {m['key']}: {'set' if m['key'] in have else 'MISSING in .env'}; {price}")
    print("image config:", "current" if baked_is_current() else "STALE - run: python3 probes/sweep/models.py --write")
