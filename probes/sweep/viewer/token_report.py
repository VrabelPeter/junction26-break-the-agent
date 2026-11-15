"""Where an OpenCode run's tokens went, from its event log:  python token_report.py <trial>/agent/opencode.txt
Prices are Verda's for kimi-k3-1-pro: input 2, cached input 0.2, output and reasoning 10 USD per million."""
import json, sys, collections
import numpy as np
events = []
for line in open(sys.argv[1], errors="ignore"):
    line = line.strip()
    if line.startswith("{"):
        try: events.append(json.loads(line))
        except Exception: pass
steps = []; cur = dict(tools=[], reasoning=0, text=0)
for e in events:
    p = e.get("part") or {}
    if e["type"] == "tool_use":
        st = p.get("state") or {}
        out = st.get("output") or ""
        att = st.get("attachments") or []
        cur["tools"].append((p.get("tool"), len(json.dumps(st.get("input") or {})), len(out) if isinstance(out, str) else len(json.dumps(out)), len(att)))
    elif e["type"] == "reasoning": cur["reasoning"] += len(p.get("text") or "")
    elif e["type"] == "text": cur["text"] += len(p.get("text") or "")
    elif e["type"] == "step_finish":
        tk = p["tokens"]; cur.update(prompt=tk["input"] + tk["cache"]["read"], input=tk["input"], cache=tk["cache"]["read"], out=tk["output"], reas=tk["reasoning"])
        steps.append(cur); cur = dict(tools=[], reasoning=0, text=0)
n = len(steps); P = np.array([s["prompt"] for s in steps])
print(f"{n} model calls; prompt tokens: first {P[0]}, at 25% {P[n // 4]}, 50% {P[n // 2]}, 75% {P[3 * n // 4]}, last {P[-1]}, max {P.max()}")
drops = [(i, int(P[i - 1]), int(P[i])) for i in range(1, n) if P[i] < P[i - 1] - 2000]
print("drops in prompt size (compaction):", drops if drops else "none")
tot_in, tot_cache, tot_out, tot_reas = (sum(s[k] for s in steps) for k in ("input", "cache", "out", "reas"))
cost = tot_in * 2e-6 + tot_cache * 0.2e-6 + (tot_out + tot_reas) * 10e-6
print(f"billed: uncached input {tot_in} ({tot_in * 2e-6:.2f} USD), cached input {tot_cache} ({tot_cache * 0.2e-6:.2f} USD), output {tot_out} + reasoning {tot_reas} ({(tot_out + tot_reas) * 10e-6:.2f} USD) = {cost:.2f} USD")
# what each step adds to the prompt: regress the growth on the characters and pictures produced in that step
X, y = [], []
for i in range(n - 1):
    s = steps[i]
    chars_out = sum(t[2] for t in s["tools"]); chars_in = sum(t[1] for t in s["tools"]); imgs = sum(t[3] for t in s["tools"])
    X.append([chars_out + chars_in, imgs, s["reas"] + s["out"], 1.0]); y.append(P[i + 1] - P[i])
X, y = np.array(X, float), np.array(y, float)
ok = y > -2000
coef, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
print(f"growth of the prompt per step ~ {coef[0]:.3f} tokens per character of tool call+result, {coef[1]:.0f} tokens per picture, {coef[2]:.2f} per generated token (reasoning+output kept), {coef[3]:.0f} fixed")
by = collections.defaultdict(lambda: [0, 0, 0, 0.0])
for i, s in enumerate(steps):
    left = n - 1 - i                        # how many later model calls re-read what this step added
    for tool, cin, cout, imgs in s["tools"]:
        b = by[tool]; b[0] += 1; b[1] += cout; b[2] += imgs
        b[3] += ((cin + cout) * coef[0] + imgs * coef[1]) * left
print(f"{'tool':22s} {'calls':>5s} {'chars/result':>12s} {'tokens/result':>13s} {'pictures':>8s} {'re-read tokens (M)':>18s} {'USD':>6s}")
tot = 0
for tool, b in sorted(by.items(), key=lambda kv: -kv[1][3]):
    tokres = (b[1] / b[0]) * coef[0] + (b[2] / b[0]) * coef[1]
    print(f"{tool:22s} {b[0]:5d} {b[1] / b[0]:12.0f} {tokres:13.0f} {b[2]:8d} {b[3] / 1e6:18.2f} {b[3] * 0.2e-6:6.2f}")
    tot += b[3]
gen = sum((s["reas"] + s["out"]) * coef[2] * (n - 1 - i) for i, s in enumerate(steps))
base = P[0] * n
print(f"re-reading tool calls and results: {tot / 1e6:.2f} M tokens; re-reading the model's own reasoning: {gen / 1e6:.2f} M; the fixed prompt ({P[0]} tokens x {n} calls): {base / 1e6:.2f} M; billed prompt total {(tot_in + tot_cache) / 1e6:.2f} M")
