#!/usr/bin/env python3
"""One command: reference run, agent runs, do-nothing and stop-early, with the standard harness.

    python3 eval/run_eval.py                      # everything, seeds 1 2 4, level 2, local Docker
    python3 eval/run_eval.py --skip-agent         # no model needed: reference and the two baselines only
    python3 eval/run_eval.py --seeds 1 --env modal

Every run is `harbor run -p <task> -a <agent>`; this script only starts them, waits, and reads the scores
the verifier wrote. The agent model is picked with a provider preset, and any field can be overridden by a
flag or an environment variable (flag > variable > preset):

    --provider / EVAL_PROVIDER         verda (default): Kimi K3.1 Pro on https://inference.verda.com/v1
                                       featherless: small open models (Qwen 3) on https://api.featherless.ai/v1
                                       nemotron: Nemotron 3.5 Super VL on a Verda container (key VERDA_INFERENCE_KEY)
    --model / EVAL_MODEL               provider/model for `-m`, e.g. featherless/Qwen/Qwen3-8B
    --base-url / EVAL_BASE_URL         OpenAI-compatible endpoint, or empty for a native provider such as google/...
    --api-key-name / EVAL_API_KEY_NAME name of the variable holding the key (it is read from .env)
    --api-format / EVAL_API_FORMAT     openai_chat_completions unless the provider is native
    --images / EVAL_IMAGES             auto (default) | on | off: tell OpenCode the model takes pictures. Always on for
                                       Kimi on Verda; without it the model gets an error text instead of camera images

    python3 eval/run_eval.py --provider featherless                                   # Qwen3-8B
    python3 eval/run_eval.py --provider featherless --model featherless/Qwen/Qwen3-32B

Context window check (eval/context_check.py): before Featherless agent runs, the model's window is read from
the Featherless API and the eval refuses to start below --min-context (default 32768; EVAL_MIN_CONTEXT).
After every agent run, the OpenCode log is checked for a provider "does not fit" error; such runs are flagged
in the output and in results/eval-*.json (`context`, `context_overflow_seeds`, `mean_without_overflow`),
because an episode cut off by the window is a serving limit, not a decision of the agent.

Needs: .venv with harbor (see README), Docker (or `--env modal` and a Modal token), and for agent runs
a key in .env. Stdlib only.
"""
import argparse
import concurrent.futures as cf
import datetime
import glob
import json
import os
import subprocess
import sys

import context_check  # eval/ is on sys.path when this file is run as a script

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In a Claude Code worktree (.claude/worktrees/<name>) the virtualenv and .env live in the main checkout.
MAIN = os.path.dirname(os.path.dirname(os.path.dirname(ROOT))) if "/.claude/worktrees/" in ROOT else ROOT
HARBOR = os.path.join(MAIN, ".venv", "bin", "harbor")

# OpenAI-compatible endpoints. The provider name in `-m` must not be `openai` (OpenCode would then use the
# Responses API, see docs/harness-notes.md). Featherless model ids contain a slash themselves
# (Qwen/Qwen3-8B); OpenCode splits `-m` at the first slash, so featherless/Qwen/Qwen3-8B is right.
PROVIDERS = {
    # images: the model takes pictures. OpenCode does not know that for a model on a custom endpoint and
    # then replaces every image with an error text, so the run has to declare it (experiment 1114-1415).
    "verda": {"model": "verda/kimi-k3-1-pro", "base_url": "https://inference.verda.com/v1",
              "api_key_name": "VERDA_API_KEY", "images": True,
              "limit": {"context": 96000, "output": 16000}},      # as in probes/sweep/models.json: OpenCode compacts before the window is full
    "featherless": {"model": "featherless/Qwen/Qwen3-8B", "base_url": "https://api.featherless.ai/v1",
                    "api_key_name": "FEATHERLESS_API_KEY", "images": False},
    # NVIDIA Nemotron 3.5 Super VL (open weights, takes pictures) on a Verda container endpoint. Its key is a
    # different one from VERDA_API_KEY. Runs through OpenCode (sweep smoke test and three full runs, 14 Nov).
    "nemotron": {"model": "verda-nemotron/nemotron-3.5-super-vl",
                 "base_url": "https://containers.datacrunch.io/nemotron-3-5-super-vl-b300/v1",
                 "api_key_name": "VERDA_INFERENCE_KEY", "images": True,
                 "limit": {"context": 96000, "output": 16000}},
}


def docker_wrap(cmd):
    """Where the shell is not (yet) in the `docker` group the command goes through `sg docker`; elsewhere unchanged."""
    if subprocess.run(["docker", "ps"], capture_output=True).returncode == 0:
        return cmd
    return ["sg", "docker", "-c", " ".join("'" + c.replace("'", "'\\''") + "'" for c in cmd)]


def env_file_keys():
    """Names of the variables set (non-empty) in .env, without reading values into anything else."""
    path = os.path.join(MAIN, ".env")
    if not os.path.exists(path):
        return set()
    names = set()
    for line in open(path):
        name, eq, value = line.strip().partition("=")
        if eq and not name.startswith("#") and value.strip().strip("\"'"):
            names.add(name.strip().removeprefix("export ").strip())
    return names


def image_input_config(model: str, limit: dict | None = None) -> str:
    """OpenCode config that declares image input for a model on a custom endpoint (`provider/model-id`).
    Without it OpenCode hands the model an error text instead of every picture a tool returns."""
    provider, model_id = model.split("/", 1)
    entry = {"attachment": True, "modalities": {"input": ["text", "image"], "output": ["text"]}}
    if limit:
        entry["limit"] = limit          # lets OpenCode compact the history before the window is full
    return json.dumps({"provider": {provider: {"models": {model_id: entry}}}})


def run(kind, seed, a, stamp):
    """Start one harbor job and return its score details."""
    job = f"{stamp}-{kind}-s{seed}"
    cmd = [HARBOR, "run", "-p", a.task, "-o", a.out, "--job-name", job]
    if a.env != "docker":
        cmd += ["-e", a.env]
    if kind == "reference":
        cmd += ["-a", "oracle"]
    elif kind == "stop_early":
        cmd += ["-a", "oracle", "--ae", "TABLETOP_POLICY=stop_early", "--ae", "SWEEP_POLICY=stop_early"]
    elif kind == "do_nothing":
        cmd += ["-a", "nop"]
    else:
        cmd += ["-a", "opencode", "-m", a.model, "--env-file", os.path.join(MAIN, ".env")]
        if a.base_url:
            cmd += ["--base-url", a.base_url, "--api-key-name", a.api_key_name, "--api-format", a.api_format]
            if a.images:
                cmd += ["--ak", "opencode_config=" + image_input_config(a.model, a.limit)]
    env = dict(os.environ, TABLETOP_SEED=str(seed), TABLETOP_LEVEL=str(a.level), SWEEP_SEED=str(seed), SWEEP_LEVEL=str(a.level))
    log = os.path.join(a.out, job + ".log")
    with open(log, "w") as f:
        code = subprocess.run(docker_wrap(cmd) if a.env == "docker" else cmd, cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT).returncode
    # Agent runs: did the episode end because the prompt outgrew the model's context window?
    ctx = {}
    if kind == "agent":
        for trial in context_check.trials_under(os.path.join(a.out, job)):
            ctx = context_check.check_trial(trial, a.context_length)
    found = glob.glob(os.path.join(a.out, job, "*", "verifier", "details.json"))
    if not found:
        return {"kind": kind, "seed": seed, "score": None, "error": f"no score (harbor exit {code}); see {log}", **ctx}
    d = json.load(open(found[0]))
    reward = open(os.path.join(os.path.dirname(found[0]), "reward.txt")).read().strip()
    return {"kind": kind, "seed": seed, "score": float(reward), "progress": d.get("progress"), "damaged": d.get("damaged"),
            "flawless": d.get("flawless"), "detail": d.get("detail"), "trial": os.path.dirname(os.path.dirname(found[0])),
            **ctx}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", required=True,
                    help="Harbor task directory, e.g. probes/shapes. No default: the kitchen-tabletop task this script was\n"
                         "written for was removed on 14 Nov, and the living-room sweep task is not on main yet.")
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 4])
    ap.add_argument("--level", type=int, default=2)
    ap.add_argument("--env", default="docker", help="docker (default) or modal")
    ap.add_argument("--out", default="runs/eval")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--skip-agent", action="store_true")
    ap.add_argument("--provider", choices=sorted(PROVIDERS), default=os.environ.get("EVAL_PROVIDER", "verda"))
    ap.add_argument("--model")
    ap.add_argument("--base-url")
    ap.add_argument("--api-key-name")
    ap.add_argument("--api-format")
    ap.add_argument("--images", choices=["auto", "on", "off"], default=os.environ.get("EVAL_IMAGES", "auto"),
                    help="declare image input for the model to OpenCode. auto: on for Kimi on Verda, off for the Featherless models")
    ap.add_argument("--min-context", type=int, default=int(os.environ.get("EVAL_MIN_CONTEXT", context_check.DEFAULT_MIN_CONTEXT)),
                    help="refuse a Featherless model whose context window is smaller (tokens)")
    a = ap.parse_args()
    preset = dict(PROVIDERS[a.provider], api_format="openai_chat_completions")
    for field in ("model", "base_url", "api_key_name", "api_format"):
        if getattr(a, field) is None:
            setattr(a, field, os.environ.get("EVAL_" + field.upper(), preset[field]))
    a.images = preset.get("images", False) if a.images == "auto" else a.images == "on"
    a.limit = preset.get("limit")
    if not a.skip_agent and a.base_url and a.api_key_name not in env_file_keys() and not os.environ.get(a.api_key_name):
        sys.exit(f"agent runs need {a.api_key_name} in .env (see .env.example), or use --skip-agent")
    a.context_length = None
    if not a.skip_agent and (a.base_url or "").rstrip("/") == context_check.FEATHERLESS_BASE:
        from featherless_models import api_key
        ok, msgs, a.context_length = context_check.preflight(a.model, api_key(a.api_key_name), a.min_context)
        for m in msgs:
            print(f"context check, {a.model}: {m}")
        if not ok:
            sys.exit("not starting: pick another model (python3 eval/featherless_models.py) or lower --min-context")
    if not os.path.exists(HARBOR):
        sys.exit("harbor is not installed: python3 -m venv .venv && .venv/bin/pip install 'harbor[modal]'")
    os.makedirs(os.path.join(ROOT, a.out), exist_ok=True)
    a.out = os.path.join(ROOT, a.out)
    stamp = datetime.datetime.now().strftime("%m%d-%H%M")
    kinds = ["reference", "do_nothing", "stop_early"] + ([] if a.skip_agent else ["agent"])
    jobs = [(k, s) for k in kinds for s in a.seeds]
    print(f"task {a.task}, level {a.level}, seeds {a.seeds}, {len(jobs)} runs on {a.env}" + ("" if a.skip_agent else f", agent model {a.model}"))
    with cf.ThreadPoolExecutor(a.parallel) as ex:
        res = list(ex.map(lambda j: run(j[0], j[1], a, stamp), jobs))
    print(f"\n{'run':<12}" + "".join(f"seed {s:<6}" for s in a.seeds) + "mean    flawless")
    summary = {}
    for k in kinds:
        rows = [r for r in res if r["kind"] == k]
        sc = [r["score"] for r in rows]
        ok = [x for x in sc if x is not None]
        mean = sum(ok) / len(ok) if ok else float("nan")
        summary[k] = {"scores": sc, "mean": mean}
        if k == "agent":
            over = [r["seed"] for r in rows if r.get("context") == "overflow"]
            fair = [r["score"] for r in rows if r.get("context") != "overflow" and r["score"] is not None]
            summary[k].update(context_overflow_seeds=over, context_length=a.context_length,
                              mean_without_overflow=sum(fair) / len(fair) if fair else float("nan"))
        print(f"{k:<12}" + "".join(f"{('%.3f' % x) if x is not None else 'ERROR':<11}" for x in sc) + f"{mean:<8.3f}" + (f"{sum(bool(r.get('flawless')) for r in rows)}/{len(rows)}" if any(r.get('flawless') is not None for r in rows) else "-"))
    for r in res:
        if r.get("error"):
            print("  !", r["kind"], "seed", r["seed"], r["error"])
        elif r["kind"] == "agent" and r.get("damaged"):
            print(f"  agent seed {r['seed']}: damaged {r['detail'].get('damage')}")
        if r.get("context") in ("overflow", "near_limit"):
            print(f"  ! agent seed {r['seed']}: {'ENDED ON THE CONTEXT WINDOW' if r['context'] == 'overflow' else 'near the context window'}"
                  f" (largest prompt {r.get('peak_prompt_tokens') or '?'} tokens, window {r.get('context_length') or '?'}):"
                  f" {r.get('context_evidence', '')}")
    over = summary.get("agent", {}).get("context_overflow_seeds")
    if over:
        print(f"\n  ! {len(over)} of {len(a.seeds)} agent runs (seeds {over}) were cut off by the model's context window, not by"
              f" a decision of the agent. They are not agent failures: do not report them as the gap. Mean without them:"
              f" {summary['agent']['mean_without_overflow']:.3f}. Use a model with a larger window.")
    out = os.path.join(ROOT, "results", f"eval-{stamp}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"task": a.task, "level": a.level, "seeds": a.seeds, "env": a.env, "model": None if a.skip_agent else a.model,
               "base_url": None if a.skip_agent else a.base_url,
               "summary": summary, "runs": [{k: v for k, v in r.items() if k != "trial"} for r in res]}, open(out, "w"), indent=1)
    print(f"\nwrote {os.path.relpath(out, ROOT)}; trial folders (trajectories, replays) under {os.path.relpath(a.out, ROOT)}")


if __name__ == "__main__":
    main()
