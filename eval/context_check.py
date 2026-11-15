#!/usr/bin/env python3
"""Catch agent runs that fail because the model's context window is too small, not because of a decision.

An OpenCode episode on our tasks resends the whole conversation every turn, so the prompt grows with every
tool call. Measured on the Kimi K3.1 Pro runs of 14 Nov (21 trajectories under runs/): the first request is
7-9K tokens (OpenCode's system prompt, our tool schemas, the instruction), and full episodes peak at
30-74K prompt tokens. Small open models on Featherless are often served with 4K-32K windows. When the
prompt no longer fits, the provider rejects the request, OpenCode exits, and Harbor still grades the
half-done state: it looks exactly like an agent that stopped early. Such a run is a limit of the serving
setup, not a result, and must not be counted as an agent failure (CLAUDE.md: fair difficulty only).

Two checks:

    python3 eval/context_check.py --model featherless/Qwen/Qwen3-8B      # before: is the window big enough?
    python3 eval/context_check.py runs/eval/<job or trial dir> [...]      # after: did a run end on the window?

eval/run_eval.py runs both: the first before any Featherless agent run (it refuses to start below
--min-context), the second on every agent trial, and it reports overflowed runs separately. Stdlib only.
"""
import argparse
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request

# Prompt sizes seen in our own OpenCode runs (see the docstring). Below FIRST_REQUEST nothing works at all;
# below PEAK_SEEN some episodes will overflow; the default minimum sits between the two.
FIRST_REQUEST_TOKENS = 9_000
PEAK_SEEN_TOKENS = 74_000
DEFAULT_MIN_CONTEXT = 32_768
NEAR_LIMIT = 0.9  # a run whose largest prompt used this share of the window is reported as near the limit

# Provider and OpenCode messages for "the request does not fit". Matched only against error events and
# stderr lines, never against the model's own text, so an agent talking about "context" cannot trigger it.
OVERFLOW_PATTERNS = [re.compile(p, re.I) for p in (
    r"context[_ ]length[_ ]exceeded",
    r"maximum context length",
    r"context[_ ]?overflow",
    r"max_model_len",
    r"(prompt|input|request|message)s? (is|are) too (long|large)",
    r"reduce the length of the (messages|prompt|input)",
    r"(exceed|larger than|greater than|longer than|more than)\w*\s.{0,80}(context|token limit|tokens? allowed|max(imum)? tokens)",
    r"(context|prompt|input)\s.{0,60}(exceed|too long|too large|does not fit)",
    r"max(_completion)?_tokens.{0,80}(too large|exceed|must be (less|at most|<=)|greater than)",
)]

FEATHERLESS_BASE = "https://api.featherless.ai/v1"


# ---------- before the run: does the model's window fit an OpenCode episode? ----------

def featherless_model(model_id, key, base=FEATHERLESS_BASE):
    """GET /v1/models/{id}: context_length, max_completion_tokens, features, available_on_current_plan."""
    req = urllib.request.Request(f"{base}/models/{model_id}",
                                 headers={"Authorization": f"Bearer {key}", "User-Agent": "harbor-eval"})
    with urllib.request.urlopen(req, timeout=30) as r:
        info = json.load(r)
    return info.get("data", info) if isinstance(info, dict) else info


def judge_model(info, min_context=DEFAULT_MIN_CONTEXT):
    """Return (ok, messages, context_length) for a Featherless model record. Pure, so it is testable."""
    ctx = info.get("context_length")
    msgs, ok = [], True
    if not ctx:
        return True, ["context window unknown (Featherless did not report context_length); overflow will be "
                      "detected after each run"], None
    if ctx < FIRST_REQUEST_TOKENS:
        ok = False
        msgs.append(f"context window {ctx} tokens is smaller than OpenCode's first request (about "
                    f"{FIRST_REQUEST_TOKENS}): the agent cannot even start")
    elif ctx < min_context:
        ok = False
        msgs.append(f"context window {ctx} tokens is below the minimum {min_context} (--min-context): most "
                    f"episodes would end on the window, not on a decision")
    elif ctx < PEAK_SEEN_TOKENS:
        msgs.append(f"context window {ctx} tokens: past episodes peaked at 30-74K prompt tokens, so some runs "
                    f"may end on the window; such runs are flagged after the run")
    feats = info.get("features") or {}
    if feats and feats.get("tool_use") is False:
        ok = False
        msgs.append("model has no native tool calls (features.tool_use is false): it cannot drive OpenCode")
    if info.get("available_on_current_plan") is False:
        ok = False
        msgs.append("model is not available on the current Featherless plan")
    return ok, msgs, ctx


def preflight(model, key, min_context=DEFAULT_MIN_CONTEXT, base=FEATHERLESS_BASE):
    """Check a `featherless/<id>` model before launching runs. Network trouble is a warning, not a stop."""
    model_id = model.split("/", 1)[1] if model.startswith("featherless/") else model
    try:
        info = featherless_model(model_id, key, base)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, [f"Featherless has no model {model_id!r} (HTTP 404)"], None
        return True, [f"could not check the context window (HTTP {e.code}); overflow will be detected after "
                      f"each run"], None
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return True, [f"could not check the context window ({e}); overflow will be detected after each run"], None
    return judge_model(info, min_context)


# ---------- after the run: did it end on the window? ----------

def _read(path, parse=False):
    with open(path, errors="replace") as f:
        return json.load(f) if parse else f.read()


def _error_texts(trial):
    """Error events and non-JSON (stderr) lines from OpenCode's log, plus the error lines Harbor kept."""
    out = []
    log = os.path.join(trial, "agent", "opencode.txt")
    if os.path.exists(log):
        for line in _read(log).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                out.append(line)  # stderr is merged into this file (2>&1)
                continue
            if isinstance(ev, dict) and (ev.get("type") == "error" or "error" in ev):
                out.append(json.dumps(ev.get("error", ev)))
    res = os.path.join(trial, "result.json")
    if os.path.exists(res):
        try:
            exc = _read(res, parse=True).get("exception_info") or {}
        except ValueError:
            exc = {}
        # The exception message repeats the whole command, instruction included: keep only error events.
        for line in (exc.get("exception_message") or "").splitlines():
            if '"type":"error"' in line or line.lower().startswith(("stderr:", "error")):
                out.append(line)
    return out


def peak_prompt_tokens(trial):
    path = os.path.join(trial, "agent", "trajectory.json")
    if not os.path.exists(path):
        return None
    try:
        steps = _read(path, parse=True).get("steps") or []
    except ValueError:
        return None
    peaks = [((s.get("metrics") or {}).get("prompt_tokens") or 0) for s in steps]
    return max(peaks) if peaks and max(peaks) else None


def check_trial(trial, context_length=None):
    """Classify one trial: overflow (the provider refused a request for its size), near_limit, ok, or no_log."""
    peak = peak_prompt_tokens(trial)
    for text in _error_texts(trial):
        if any(p.search(text) for p in OVERFLOW_PATTERNS):
            return {"context": "overflow", "peak_prompt_tokens": peak, "context_length": context_length,
                    "context_evidence": text[:300]}
    if not os.path.exists(os.path.join(trial, "agent", "opencode.txt")):
        return {"context": "no_log", "peak_prompt_tokens": peak, "context_length": context_length}
    if context_length and peak and peak >= NEAR_LIMIT * context_length:
        return {"context": "near_limit", "peak_prompt_tokens": peak, "context_length": context_length,
                "context_evidence": f"largest prompt {peak} of {context_length} tokens"}
    return {"context": "ok", "peak_prompt_tokens": peak, "context_length": context_length}


def trials_under(path):
    """A trial dir itself, or every trial dir below a job dir / runs folder."""
    if os.path.isdir(os.path.join(path, "agent")):
        return [path]
    return sorted(os.path.dirname(os.path.dirname(p))
                  for p in glob.glob(os.path.join(path, "**", "agent", "opencode.txt"), recursive=True))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", help="trial or job directories to check after a run")
    ap.add_argument("--model", help="featherless/<id>: check the window before a run")
    ap.add_argument("--context", type=int, help="the model's window, to flag runs near it")
    ap.add_argument("--min-context", type=int, default=DEFAULT_MIN_CONTEXT)
    a = ap.parse_args()
    if not a.model and not a.paths:
        ap.error("give --model and/or run directories")
    bad = False
    if a.model:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from featherless_models import api_key
        ok, msgs, ctx = preflight(a.model, api_key(), a.min_context)
        print(f"{a.model}: {'OK' if ok else 'NOT USABLE'}" + (f", context window {ctx}" if ctx else ""))
        for m in msgs:
            print("  -", m)
        bad |= not ok
        a.context = a.context or ctx
    for path in a.paths:
        for trial in trials_under(path):
            r = check_trial(trial, a.context)
            print(f"{r['context']:<11}{str(r['peak_prompt_tokens'] or '-'):>8}  {trial}"
                  + (f"\n           {r['context_evidence']}" if r.get("context_evidence") else ""))
            bad |= r["context"] == "overflow"
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
