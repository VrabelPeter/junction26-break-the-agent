#!/usr/bin/env python3
"""List Featherless models that can drive OpenCode (native tool calls), with context and concurrency cost.

    python3 eval/featherless_models.py            # Qwen models with tool use
    python3 eval/featherless_models.py --all      # every model with tool use
    python3 eval/featherless_models.py Qwen/Qwen3-8B   # details of one model

Reads FEATHERLESS_API_KEY from the environment or .env. Stdlib only. Use the printed id as
`--model featherless/<id>` in eval/run_eval.py.

Why this matters: OpenCode only works with native `tool_calls`. Featherless documents native tool calling
for the Qwen 3 family and Kimi K2; other models fall back to a JSON-prompting workaround that OpenCode does
not use. OpenCode's own system prompt plus our tool schemas need well over 8K tokens, so pick a model whose
context_length is at least 32K.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://api.featherless.ai/v1"


def api_key(name="FEATHERLESS_API_KEY"):
    key = os.environ.get(name)
    path = os.path.join(ROOT, ".env")
    if not key and os.path.exists(path):
        for line in open(path):
            var, eq, value = line.strip().partition("=")
            if eq and var.strip().removeprefix("export ").strip() == name:
                key = value.strip().strip("\"'")
    if not key:
        sys.exit(f"{name} is not set (put it in .env, see .env.example)")
    return key


def get(path, **params):
    url = f"{BASE}{path}" + (("?" + urllib.parse.urlencode(params)) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key()}", "User-Agent": "harbor-eval"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", nargs="?", help="show the details of one model id, e.g. Qwen/Qwen3-8B")
    ap.add_argument("--all", action="store_true", help="all families, not only Qwen")
    ap.add_argument("--min-context", type=int, default=32768)
    a = ap.parse_args()
    if a.model:
        print(json.dumps(get("/models/" + a.model.removeprefix("featherless/")), indent=1))
        return
    data = get("/models", all="true", capabilities="tool-use", context_length_min=a.min_context).get("data", [])
    rows = [m for m in data if a.all or "qwen" in m.get("id", "").lower()]
    rows.sort(key=lambda m: m.get("id", ""))
    print(f"{'id':<55}{'context':>9}{'max out':>9}  class")
    for m in rows:
        print(f"{m.get('id', ''):<55}{m.get('context_length') or '':>9}{m.get('max_completion_tokens') or '':>9}  {m.get('model_class', '')}")
    print(f"\n{len(rows)} models. Run with: python3 eval/run_eval.py --provider featherless --model featherless/<id>")


if __name__ == "__main__":
    main()
