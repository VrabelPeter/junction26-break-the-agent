#!/bin/bash
# Runs as root after the agent has stopped. The agent ran as the unprivileged
# user `agent`, so it could not touch system files; what it could do is leave
# processes behind or plant files in the world-writable log directory.
/usr/local/bin/python3 -I - <<'PY'
import json, os, pwd, shutil, signal, time, urllib.request

# 1. Nothing the agent left running may race the grader.
uid = pwd.getpwnam("agent").pw_uid
for _ in range(20):
    mine = [int(p) for p in os.listdir("/proc") if p.isdigit() and os.stat(f"/proc/{p}").st_uid == uid]
    if not mine:
        break
    for pid in mine:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    time.sleep(0.1)

# 2. Drop anything planted in the log directory (Harbor prefers reward.json if it exists).
out = "/logs/verifier"
os.makedirs(out, exist_ok=True)
for name in os.listdir(out):
    path = os.path.join(out, name)
    shutil.rmtree(path) if os.path.isdir(path) and not os.path.islink(path) else os.unlink(path)

# 3. The score comes from the environment server's own state.
try:
    with urllib.request.urlopen("http://env-server:8000/score", timeout=20) as r:
        d = json.load(r)
    s = min(1.0, max(0.0, float(d["score"])))
except Exception as e:  # unreachable server grades as zero
    d, s = {"error": repr(e)}, 0.0
d["agent_processes_killed"] = True
open(os.path.join(out, "details.json"), "w").write(json.dumps(d))
open(os.path.join(out, "reward.txt"), "w").write(f"{s:.4f}\n")
PY
cat /logs/verifier/reward.txt
