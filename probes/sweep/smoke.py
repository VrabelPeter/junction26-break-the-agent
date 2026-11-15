#!/usr/bin/env python3
"""Quick checks to run before any long or paid run of the sweep task. Minutes, not hours.

    python3 probes/sweep/smoke.py                      # free: do-nothing, interface check, scripted reference
    python3 probes/sweep/smoke.py --model kimi         # plus a 6-minute run with Kimi K3.1 Pro
    python3 probes/sweep/smoke.py --model nemotron     # plus a 6-minute run with Nemotron 3.5 Super VL
    python3 probes/sweep/smoke.py --model kimi nemotron --skip-free

Models are the entries of probes/sweep/models.json (`python3 probes/sweep/models.py` lists them).

What it establishes:
  harness     the task builds, the sidecar answers, the verifier writes a score
  reward      doing nothing scores 0
  interface   from inside the agent's container: the tools are the intended ones, the head camera gives a colour
              picture, a depth picture and calibration, the depth file downloads, the room cameras and the
              object positions are out of reach (standard setting)
  reference   the scripted reference scores (privileged setting)
  model       the model receives pictures and acts: it is told to look, read a depth value and drive a little,
              and the server's own log shows whether it did
"""
import argparse, glob, json, os, re, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import models  # noqa: E402  (probes/sweep/models.py: the model list, paths, Docker access)
from models import HARBOR, HERE, MAIN, ROOT  # noqa: E402

SMOKE_TEXT = ("THIS IS A SHORT CONNECTION TEST, NOT THE TASK. Do exactly these steps and then stop: "
              "1) call get_task; 2) call camera with name head and write one sentence saying what you see on the table; "
              "3) in the shell, download http://env-server:8000/camera/head/depth.npy and print its shape and the value at row 240, column 320; "
              "4) call observe, then drive_to a point 0.2 m further along +x with the same heading; 5) stop. Do not do anything else.")


def run(name, args, env, out):
    cmd = [HARBOR, "run", "-p", HERE, "-o", os.path.join(out, name)] + args
    t = time.time()
    with open(os.path.join(out, name + ".log"), "w") as f:
        subprocess.run(models.docker_wrap(cmd), cwd=ROOT, env=dict(os.environ, **env), stdout=f, stderr=subprocess.STDOUT)
    trial = (glob.glob(os.path.join(out, name, "*", "sweep__*")) or [None])[0]
    def read(rel):
        p = os.path.join(trial, rel) if trial else ""
        return open(p, errors="ignore").read() if os.path.exists(p) else ""
    score = read("verifier/reward.txt").strip()
    return dict(score=float(score) if score else None, trial=trial, read=read, seconds=round(time.time() - t))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", nargs="*", default=[], choices=models.names())
    ap.add_argument("--skip-free", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "sweep", "smoke-" + time.strftime("%H%M")))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows, ok = [], True
    def report(name, passed, note):
        nonlocal ok
        ok &= bool(passed)
        rows.append((name, "ok" if passed else "FAIL", note))
        print(f"{name:28s} {'ok' if passed else 'FAIL':5s} {note}", flush=True)
    if not models.baked_is_current():
        print("environment/opencode-models.json does not match models.json. Run: python3 probes/sweep/models.py --write")
        sys.exit(2)
    std, priv = dict(SWEEP_SETTING="standard", SWEEP_LEVEL="1", SWEEP_SEED="1"), dict(SWEEP_SETTING="privileged", SWEEP_LEVEL="1", SWEEP_SEED="1")
    if not a.skip_free:
        r = run("nop", ["-a", "nop"], std, a.out)
        report("harness + do-nothing", r["score"] == 0.0, f"score {r['score']} in {r['seconds']} s")
        r = run("interface", ["-a", "oracle", "--ae", "SWEEP_POLICY=smoke"], std, a.out)
        m = None
        for f in glob.glob(os.path.join(r["trial"] or "", "**", "*"), recursive=True):
            if os.path.isfile(f):
                m = m or re.search(r"SMOKE_JSON (\{.*\})", open(f, errors="ignore").read())
        d = json.loads(m.group(1)) if m else {}
        report("interface (standard)", d.get("ok") is True, json.dumps({k: d.get(k) for k in ("arm", "empty_grasp_says_why", "head_parts", "wrist_parts", "depth", "room_camera_status", "objects_in_observation", "no_pixel_to_position_tool")}) if d else "no SMOKE_JSON found in the trial")
        r = run("reference", ["-a", "oracle"], std, a.out)
        report("scripted reference", r["score"] is not None and r["score"] >= 0.99, f"score {r['score']} in {r['seconds']} s (standard setting: it works from the cameras; level 1, seed 1)")
    for name in a.model:
        if models.get(name)["key"] not in models.keys_set():
            report(f"model {name}", False, f"{models.get(name)['key']} has no value in {models.ENV_FILE}")
            continue
        r = run("model-" + name, models.harbor_args(name) + ["--agent-timeout-multiplier", "0.1", "--extra-instruction", SMOKE_TEXT], std, a.out)
        calls = json.loads(r["read"]("verifier/commands.json") or "{}").get("calls", [])
        names = [c["tool"] + (":" + c["args"].get("what", "") if c["tool"] == "camera_file" else "") for c in calls]
        agent_log = r["read"]("agent/opencode.txt")
        saw = "camera" in names and "Cannot read image" not in agent_log
        report(f"model {name}", saw and "camera_file:depth.npy" in names and "drive_to" in names,
               f"{len(calls)} calls in {r['seconds']} s: {names[:12]}; picture reached the model: {saw}")
    print("\nSMOKE " + ("PASSED" if ok else "FAILED") + f"  (details: {a.out})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
