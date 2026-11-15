#!/usr/bin/env python3
"""Full agent runs of the sweep task. Long (15 to 60 minutes each) and, for Kimi, paid: a person starts them.

    python3 probes/sweep/run_agent.py --model nemotron                          # standard setting, level 1, seed 1
    python3 probes/sweep/run_agent.py --model kimi --seeds 1 2 3 --parallel 3   # three seeds side by side
    python3 probes/sweep/run_agent.py --model kimi --setting privileged --level 2 --seeds 3

Every teammate runs the same command with the model they have a key for (`python3 probes/sweep/models.py`
lists the models; add one in models.json). Run names start with your coordination handle, so two people's
runs never collide. For each run a small summary, the scorer's details and the logged tool calls are copied to
results/sweep/agent-runs/ (commit those); the full Harbor trial stays in runs/sweep/ (not committed).
`python3 probes/sweep/report.py` turns everything in results/sweep/agent-runs/ into one table.

Run `python3 probes/sweep/smoke.py --model <name>` first if anything changed since the last passing smoke test.
"""
import argparse, concurrent.futures, glob, json, os, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import models  # noqa: E402
from models import HARBOR, HERE, ROOT  # noqa: E402

KEEP = os.path.join(ROOT, "results", "sweep", "agent-runs")


def commit():
    c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--", HERE], cwd=HERE, capture_output=True, text=True).stdout.strip()
    return c + ("+uncommitted" if dirty else "")


def one(a, seed, stamp):
    model = models.canonical(a.model)
    name = f"{a.who}-{model}-{a.setting}-l{a.level}-s{seed}-{stamp}" + (f"-{a.tag}" if a.tag else "")
    out = os.path.join(ROOT, "runs", "sweep", name)
    os.makedirs(out, exist_ok=True)
    cmd = [HARBOR, "run", "-p", HERE, "-o", out] + models.harbor_args(model)
    env = dict(os.environ, SWEEP_SETTING=a.setting, SWEEP_LEVEL=str(a.level), SWEEP_SEED=str(seed))
    print(f"starting {name}; log: {out}.log", flush=True)
    t = time.time()
    with open(out + ".log", "w") as f:
        subprocess.run(models.docker_wrap(cmd), cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT)
    trial = (glob.glob(os.path.join(out, "*", "sweep__*")) or [""])[0]

    def read(rel):
        p = os.path.join(trial, rel)
        return open(p, errors="ignore").read() if trial and os.path.exists(p) else ""

    d = json.loads(read("verifier/details.json") or "{}")
    calls = json.loads(read("verifier/commands.json") or "{}").get("calls", [])
    reward = read("verifier/reward.txt").strip()
    tok = dict(input=0, cached=0, output=0, cache_write=0)
    for line in read("agent/opencode.txt").splitlines():
        try:
            u = json.loads(line).get("part", {}).get("tokens")
        except ValueError:
            continue
        if u:
            tok["input"] += u.get("input", 0); tok["cached"] += u.get("cache", {}).get("read", 0); tok["output"] += u.get("output", 0) + u.get("reasoning", 0)
            tok["cache_write"] += u.get("cache", {}).get("write", 0)
    # A score is written even when the agent was cut off (network failure, crash, timeout): say so in the summary.
    stopped = (json.loads(read("result.json") or "{}").get("exception_info") or {}).get("exception_type")
    if stopped:
        last, failure = None, None
        for line in read("agent/opencode.txt").splitlines():
            if line.startswith('{"type":"error"'):
                try:
                    failure = str(json.loads(line)["error"].get("data", {}).get("message", ""))[:200]
                except (ValueError, KeyError):
                    failure = "error"
            elif line.startswith('{"type":"step_finish"'):
                try:
                    last = json.loads(line)["part"].get("reason")
                except (ValueError, KeyError):
                    pass
        if failure:
            stopped += ": " + failure
        elif last == "stop":                # the model had said its last word; OpenCode's exit code alone cuts nothing off
            stopped = None
    p = models.get(model)["usd_per_million"]
    cost = round((tok["input"] * p[0] + tok["cached"] * p[1] + tok["output"] * p[2]
                  + tok["cache_write"] * (p[3] if len(p) > 3 else p[0])) / 1e6, 2) if p else None
    summary = dict(run=name, who=a.who, model=model, model_id=f"{models.get(model)['provider']}/{models.get(model)['model']}",
                   variant=models.get(model).get("variant"), setting=a.setting, level=a.level, seed=seed, score=float(reward) if reward else None,
                   trash_in_bin=d.get("trash_in_bin"), mistakes=d.get("mistakes"), milestones=d.get("milestones"),
                   robot_time_s=d.get("robot_time_s"), tool_calls=len(calls), minutes=round((time.time() - t) / 60, 1),
                   tokens=tok, cost_usd=cost, commit=a.commit, date=time.strftime("%Y-%m-%dT%H:%M"),
                   error=(f"agent cut off, not a clean run ({stopped})" if stopped else None) if reward else f"no score written; see runs/sweep/{name}.log", trial=os.path.relpath(trial, ROOT) if trial else None)
    json.dump(summary, open(out + ".summary.json", "w"), indent=1)
    os.makedirs(KEEP, exist_ok=True)
    json.dump(summary, open(os.path.join(KEEP, name + ".summary.json"), "w"), indent=1)
    for rel in ("details.json", "commands.json"):
        src = os.path.join(trial, "verifier", rel)
        if trial and os.path.exists(src):
            shutil.copy(src, os.path.join(KEEP, f"{name}.{rel}"))
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, choices=models.names())
    ap.add_argument("--setting", default="standard", choices=["standard", "privileged"])
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--seeds", "--seed", nargs="+", type=int, default=[1])
    ap.add_argument("--parallel", type=int, default=1, help="how many runs at once (each needs about 2 CPU cores and 4 GB)")
    ap.add_argument("--who", default=models.handle(), help="prefix of the run names; default: your coordination handle")
    ap.add_argument("--tag", default="", help="free text appended to the run names, for example the build under test")
    a = ap.parse_args()
    if models.get(a.model)["key"] not in models.keys_set():
        sys.exit(f"{models.get(a.model)['key']} has no value in {models.ENV_FILE}")
    if not models.baked_is_current():
        sys.exit("environment/opencode-models.json does not match models.json. Run: python3 probes/sweep/models.py --write")
    a.commit = commit()
    stamp = time.strftime("%m%d-%H%M")
    with concurrent.futures.ThreadPoolExecutor(max(1, a.parallel)) as pool:
        done = list(pool.map(lambda s: one(a, s, stamp), a.seeds))
    for s in done:
        print(json.dumps(s, indent=1))
    scores = [s["score"] for s in done]
    print(f"\n{models.canonical(a.model)} {a.setting} level {a.level}: seeds {a.seeds} -> scores {scores}")
    print(f"summaries copied to {os.path.relpath(KEEP, ROOT)}/ - commit them, then: python3 probes/sweep/report.py")


if __name__ == "__main__":
    main()
