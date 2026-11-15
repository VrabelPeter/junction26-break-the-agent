#!/bin/bash
# Runs as root after the agent has stopped. The agent ran as the unprivileged user `agent`, so it could
# not touch system files; what it could do is leave processes behind (also ones that keep restarting each
# other) and plant files in the log directory, which Harbor creates writable by everyone.
#
# Order matters: first the directory is taken away from the agent user, then its processes are killed,
# then the directory is emptied, and only then is the score fetched and written. Whatever goes wrong,
# a score is written, and it is 0.
/usr/local/bin/python3 -I - <<'PY'
import json, os, pwd, shutil, signal, stat, time, urllib.request

OUT = "/logs/verifier"
agent = pwd.getpwnam("agent")
notes = []


def agent_pids():
    pids = []
    for p in os.listdir("/proc"):
        if p.isdigit():
            try:
                if os.stat(f"/proc/{p}").st_uid == agent.pw_uid:
                    pids.append(int(p))
            except OSError:              # gone between listing and looking
                pass
    return pids


def lock():
    """Only root may create, rename or delete entries in the log directory from here on."""
    os.makedirs(OUT, exist_ok=True)
    os.chown(OUT, 0, 0)
    os.chmod(OUT, 0o755)


def kill_agent():
    """One kill(-1) sent as the agent user reaches every process of that user in a single system call,
    so processes that restart each other cannot outrun it. Repeated until none is left."""
    for _ in range(50):
        if not agent_pids():
            return True
        child = os.fork()
        if child == 0:
            try:
                os.setgroups([])
                os.setresgid(agent.pw_gid, agent.pw_gid, agent.pw_gid)
                os.setresuid(agent.pw_uid, agent.pw_uid, agent.pw_uid)
                os.kill(-1, signal.SIGKILL)
            finally:
                os._exit(0)
        os.waitpid(child, 0)
        time.sleep(0.05)
    return not agent_pids()


def empty():
    mine = os.fstat(1)                   # Harbor sends this script's output to a file in the same directory: keep it
    for name in os.listdir(OUT):
        path = os.path.join(OUT, name)
        try:
            st = os.lstat(path)
            if stat.S_ISREG(st.st_mode) and (st.st_dev, st.st_ino) == (mine.st_dev, mine.st_ino):
                continue
            shutil.rmtree(path) if os.path.isdir(path) and not os.path.islink(path) else os.unlink(path)
        except OSError as e:
            notes.append(f"could not remove {name!r}: {e!r}")


def get(path):
    # No proxy from the environment: the score comes from the simulator's container and from nowhere else.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://env-server:8000" + path, timeout=60) as r:
        return json.load(r)


def write(name, text):
    """Written beside the final name and renamed over it, as a fresh file owned by root."""
    tmp = os.path.join(OUT, f".{name}.root")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, os.path.join(OUT, name))


d, s, log = {}, 0.0, None
try:
    lock()
    clean = kill_agent()
    empty()
    if not clean:
        notes.append("processes of the agent user could not be stopped")
    # The score comes from the simulator: where every object lies at the end.
    d = get("/score")
    s = min(1.0, max(0.0, float(d["score"])))
    if s != s:                           # not a number
        s = 0.0
    log = get("/log")
except Exception as e:                   # an unreachable simulator, or anything else going wrong, grades as zero
    d, s = dict(d, error=repr(e)), 0.0
if notes:
    d["verifier_notes"] = notes

lock()
empty()                                  # nothing but the verifier's own files may be left for Harbor to read
if log is not None:
    write("commands.json", json.dumps(log))
write("details.json", json.dumps(d, indent=1))
write("reward.txt", f"{s:.4f}\n")
write("reward.json", json.dumps({"reward": round(s, 4)}))   # Harbor reads this file first if it exists
PY
status=$?
if [ "$status" -ne 0 ] || [ ! -s /logs/verifier/reward.json ]; then
    # The grader itself failed: still a score, and it is 0.
    chown 0:0 /logs/verifier; chmod 755 /logs/verifier
    rm -rf /logs/verifier/reward.json /logs/verifier/reward.txt
    printf '0.0000\n' > /logs/verifier/reward.txt
    printf '{"reward": 0.0}\n' > /logs/verifier/reward.json
fi
cat /logs/verifier/reward.txt /logs/verifier/details.json
