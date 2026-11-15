"""One line per logged call:  python trace_log.py [first index] < commands.json"""
import json, sys
d = json.load(sys.stdin)
calls = d["calls"] if isinstance(d, dict) else d
start = int(sys.argv[1]) if len(sys.argv) > 1 else 0
for i, c in enumerate(calls):
    if i < start or c["tool"] in ("get_task",): continue
    r = c.get("result", {}) if isinstance(c.get("result"), dict) else {}
    a = c.get("args", {})
    arg = ",".join(f"{v:.3f}" if isinstance(v, float) else str(v) for v in a.values())
    bits = []
    for k in ("reached", "error_m", "holding", "released", "error", "depth_m"):
        if k in r: bits.append(f"{k}={r[k]}")
    if c["tool"] == "depth_at" and "x" in r: bits.append(f"-> ({r['x']:.3f},{r['y']:.3f},{r['z']:.3f})")
    if c["tool"] == "observe" and "objects" in r: bits.append("objects: " + "; ".join(f"{o['name']}@({o['x']},{o['y']},{o['z']}) {o['where']}" for o in r["objects"]))
    if c["tool"] in ("drive_to",) and "base" in r: b = r["base"]; bits.append(f"base=({b['x']},{b['y']},{b['heading']})")
    if c["tool"] in ("move_arm",) and a.get("arm") and a["arm"] + "_hand" in r: h = r[a["arm"] + "_hand"]; bits.append(f"hand=({h['x']},{h['y']},{h['z']},{h['yaw']})")
    print(f"{i:3d} t={c['t']:6.1f} {c['tool']}({arg}) {' '.join(bits)}")
