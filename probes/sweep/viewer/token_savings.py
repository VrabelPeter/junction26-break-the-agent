"""What each cost-saving option would have saved in a finished run:  python token_savings.py label=<trial>/agent/opencode.txt ..."""
import json, sys
import numpy as np
MOTION = ("robot_move_arm", "robot_drive_to", "robot_look", "robot_grasp", "robot_release", "robot_set_torso", "robot_home_arm")
def load(path):
    steps, cur = [], dict(tools=[], gen=0)
    for line in open(path, errors="ignore"):
        if not line.startswith("{"): continue
        try: e = json.loads(line)
        except Exception: continue
        p = e.get("part") or {}
        if e["type"] == "tool_use":
            st = p.get("state") or {}; out = st.get("output") or ""
            cur["tools"].append((p.get("tool"), len(json.dumps(st.get("input") or {})) + len(out if isinstance(out, str) else json.dumps(out)), len(st.get("attachments") or []), out if isinstance(out, str) else ""))
        elif e["type"] == "step_finish":
            tk = p["tokens"]; cur.update(P=tk["input"] + tk["cache"]["read"], gen=tk["output"] + tk["reasoning"], reas=tk["reasoning"]); steps.append(cur); cur = dict(tools=[], gen=0)
    return steps
for label, path in [a.split("=") for a in sys.argv[1:]]:
    s = load(path); n = len(s); P = np.array([x["P"] for x in s], float)
    total = P.sum(); usd = lambda tok: tok * 0.2e-6
    CH, IMG = 0.43, 436
    left = lambda i: n - 1 - i
    A = sum(max(c * CH - 60, 0) * left(i) for i, x in enumerate(s) for t, c, im, out in x["tools"] if t in MOTION)
    B = sum((len(out) - len(json.dumps({k: ({kk: vv for kk, vv in v.items() if kk != "joints"} if isinstance(v, dict) else v) for k, v in json.loads(out).items()}, separators=(",", ":")))) * CH * left(i)
            for i, x in enumerate(s) for t, c, im, out in x["tools"] if t in MOTION + ("robot_observe",) and out.startswith("{"))
    C = sum(im * (IMG - 110) * left(i) for i, x in enumerate(s) for t, c, im, out in x["tools"])
    E = sum(x["reas"] * left(i) for i, x in enumerate(s))
    # compaction at a context limit: when the prompt passes L, restart from the fixed prompt plus a 4k summary and regrow
    res = {}
    for L in (64000, 100000):
        tot2, cur, off = 0.0, P[0], 0.0
        for i in range(n):
            cur = P[i] - off
            if cur > L:
                off = P[i] - (P[0] + 4000); cur = P[0] + 4000
            tot2 += cur
        res[L] = total - tot2
    gen_cost = sum(x["gen"] for x in s) * 10e-6
    print(f"== {label}: {n} model calls, prompt total {total / 1e6:.2f} M tokens = {usd(total):.2f} USD at the cached rate (+ {gen_cost:.2f} USD generated)")
    for name, v in (("A short action results (about 60 tokens instead of the full robot state)", A), ("B drop only the joint lists", B), ("C pictures at 320x240 (changes what can be seen)", C),
                    ("D1 context limit 64k so OpenCode compacts", res[64000]), ("D2 context limit 100k", res[100000]), ("E do not resend the model's own reasoning", E)):
        print(f"   {name:75s} -{v / 1e6:5.2f} M  -{usd(v):.2f} USD  ({100 * v / total:4.1f}% of prompt tokens)")
