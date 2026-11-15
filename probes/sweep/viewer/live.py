"""Watch running sweep episodes live: http://127.0.0.1:8770

    sg docker -c "MUJOCO_GL=egl python probes/sweep/viewer/live.py"

Nothing is recorded inside the run. The simulator is deterministic, so this viewer reads each running
simulator's command log (read-only, with `docker exec`), repeats the commands in its own copy of the room and
films that copy. A badge shows whether the copy agrees with what the real simulator reported.
"""
from __future__ import annotations

import glob
import io
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import mujoco
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "environment" / "env-server"))
from sweep.sim import TIME_LIMIT, World  # noqa: E402

MOVING = ("drive_to", "move_arm", "home_arm", "grasp", "release", "look", "set_torso")
FETCH = "import urllib.request,sys;sys.stdout.write(urllib.request.urlopen('http://localhost:8000/log',timeout=20).read().decode())"
RUNS: dict[str, dict] = {}
LOCK = threading.Lock()
KEEP = 900          # frames kept per run


def sh(*cmd, timeout=40) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def label_for(cid: str) -> str:
    """The run folder that holds this trial names the model and setting."""
    root = str(HERE.parent.parent.parent)
    main = root.split("/.claude/worktrees/")[0]
    for d in glob.glob(root + "/runs/sweep/*/*/sweep__*") + glob.glob(main + "/runs/sweep/*/*/sweep__*") + glob.glob(main + "/.claude/worktrees/*/runs/sweep/*/*/sweep__*"):
        if os.path.basename(d).lower().replace("sweep__", "") == cid:
            return Path(d).parents[1].name
    return cid


def jpg(arr, q=72) -> bytes:
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "JPEG", quality=q)
    return b.getvalue()


def film(run: dict, w: World, frames: list):
    """Render the motion of the last call from the room camera, then the head camera's present view.
    Rendering happens on a scratch copy of the state: touching the simulated state itself (even only to
    look at an earlier pose) changes the solver's warm start and the copy would slowly drift from the run."""
    k, r = run["scratch"], run["renderer"]
    hide = mujoco.MjvOption()
    hide.geomgroup[2] = 0
    def shot(q, cam, opt):
        k.qpos[:] = q
        mujoco.mj_forward(w.m, k)
        r.update_scene(k, camera=cam, scene_option=opt)
        return jpg(r.render())
    for q in frames[::2] + [w.d.qpos.copy()]:
        run["video"].append(shot(q, "overview", hide))
    run["head"] = shot(w.d.qpos, "head", mujoco.MjvOption())
    if len(run["video"]) > KEEP:
        drop = len(run["video"]) - KEEP
        del run["video"][:drop]
        run["first"] += drop


def worker():
    while True:
        names = [n for n in sh("docker", "ps", "--format", "{{.Names}}").split() if n.startswith("sweep__") and n.endswith("env-server-1")]
        for name in names:
            cid = name.split("__")[1]
            raw = sh("docker", "exec", name, "python", "-c", FETCH)
            try:
                log = json.loads(raw)
            except ValueError:
                continue
            with LOCK:
                run = RUNS.get(cid)
            if run is None:
                w = World(int(log["seed"]), int(log["level"]), privileged=(log["setting"] == "privileged"))
                run = dict(id=cid, label=label_for(cid), setting=log["setting"], level=log["level"], seed=log["seed"], world=w, done=0,
                           scratch=mujoco.MjData(w.m), renderer=mujoco.Renderer(w.m, 480, 640), video=[], first=0, head=b"", calls=[], sync="no moves yet", worst=0.0, live=True, t=0.0, holding={}, fate={})
                film(run, w, [])
                with LOCK:
                    RUNS[cid] = run
            w = run["world"]
            for c in log["calls"][run["done"]:]:
                if c["tool"] in MOVING and not w.closed:
                    w.frames = []
                    r = w.call(c["tool"], **c["args"])
                    frames, w.frames = w.frames, None
                    film(run, w, frames)
                    real = c.get("result") or {}
                    if r.get("ok") and real.get("base") and r.get("base"):
                        off = max(abs(r["base"][k] - real["base"][k]) for k in ("x", "y"))
                        for hand in ("left_hand", "right_hand"):
                            if hand in real and hand in r:
                                off = max(off, *(abs(r[hand][k] - real[hand][k]) for k in ("x", "y", "z")))
                        run["worst"] = max(run["worst"], off)
                        run["sync"] = f"copy agrees with the run (largest difference {run['worst'] * 1000:.0f} mm)" if run["worst"] < 0.01 else f"copy has drifted from the run by {run['worst'] * 100:.1f} cm"
                    run["holding"] = {a: r.get(a + "_hand", {}).get("holding") for a in ("left", "right")} if r.get("ok") else run["holding"]
                args = ", ".join(f"{v:.2f}" if isinstance(v, float) else str(v) for v in c["args"].values())
                res = c.get("result") or {}
                note = "" if res.get("ok", True) else " -> refused: " + str(res.get("error"))[:60]
                note += "".join(f" {k}={res[k]}" for k in ("reached", "holding") if k in res)
                run["calls"].append(f"{c.get('t', 0):6.1f} s  {c['tool']}({args}){note}")
                run["done"] += 1
            run["t"] = w.robot_time
            run["fate"] = {n: w.where(n) for n in w.items if w.items[n]["trash"]}
            run["live"] = True
        with LOCK:
            for cid, run in RUNS.items():
                if not any(n.split("__")[1] == cid for n in names):
                    run["live"] = False
        time.sleep(2)


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sweep, live</title><style>
:root{--bg:#f3f5f6;--card:#fff;--ink:#15212b;--mut:#586675;--line:#d6dde2;--ok:#1c7448;--bad:#b0271f}
@media (prefers-color-scheme:dark){:root{--bg:#0f1418;--card:#182027;--ink:#e5ebf0;--mut:#94a2af;--line:#2b3742;--ok:#6fd09c;--bad:#f28a82}}
body{margin:0;padding:16px;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif}
h1{font-size:20px;margin:0 0 4px}.mut{color:var(--mut);font-size:12.5px}
#runs{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(min(100%,560px),1fr));margin-top:14px}
.run{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:8px;min-width:0}
.top{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:baseline}.top b{font-size:15px}
.views{display:grid;grid-template-columns:2fr 1fr;gap:8px;align-items:start}.views img{width:100%;border-radius:6px;background:#000;display:block}
.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden}.bar i{display:block;height:100%;background:var(--ok)}
pre{margin:0;font:12px/1.5 ui-monospace,Menlo,monospace;max-height:150px;overflow:auto;background:var(--bg);border-radius:6px;padding:8px;white-space:pre-wrap}
.ok{color:var(--ok)}.bad{color:var(--bad)}figure{margin:0}figcaption{font-size:11.5px;color:var(--mut)}
</style><h1>Living-room sweep, live</h1>
<div class="mut">For people. Each film is this viewer's own copy of the room, driven by the commands the running simulator has logged. Finished runs stay until the viewer is restarted.</div>
<div id="runs"></div><script>
const pos = {}, el = {};
function card(r){const d=document.createElement('div');d.className='run';d.innerHTML=`<div class="top"><b></b><span class="mut st"></span></div>
<div class="views"><figure><img class="v" alt="room"><figcaption>Room camera (the agent never gets it)</figcaption></figure><figure><img class="h" alt="head camera"><figcaption>Head camera (what the agent gets)</figcaption></figure></div>
<div class="bar"><i></i></div><div class="mut info"></div><div class="mut sync"></div><pre></pre>`;document.getElementById('runs').append(d);return d}
async function tick(){let rs=[];try{rs=await (await fetch('state')).json()}catch(e){}
 for(const r of rs){if(!el[r.id]){el[r.id]=card(r);pos[r.id]=Math.max(r.first,r.count-1)}
  const d=el[r.id];d.querySelector('b').textContent=r.label;d.querySelector('.st').textContent=(r.live?'running':'ended')+' · '+r.setting+' · level '+r.level+' · seed '+r.seed;
  d.querySelector('.bar i').style.width=Math.min(100,100*r.t/r.limit)+'%';
  d.querySelector('.info').textContent=`robot time ${r.t.toFixed(0)} of ${r.limit} s · ${r.calls_total} calls · holding: left ${r.holding.left||'nothing'}, right ${r.holding.right||'nothing'} · trash: ${Object.values(r.fate).join(', ')}`;
  const s=d.querySelector('.sync');s.textContent=r.sync;s.className='mut sync '+(r.sync.includes('drifted')?'bad':'ok');
  const p=d.querySelector('pre');const stick=p.scrollTop+p.clientHeight>=p.scrollHeight-4;p.textContent=r.calls.join('\\n');if(stick)p.scrollTop=p.scrollHeight;
  d.querySelector('.h').src='head/'+r.id+'?'+r.count;d.dataset.count=r.count;d.dataset.first=r.first}}
function play(){for(const id in el){const d=el[id],count=+d.dataset.count,first=+d.dataset.first;if(pos[id]<first)pos[id]=first;
  if(count-pos[id]>120)pos[id]=count-120;             // far behind: jump close to the present
  if(pos[id]<count){d.querySelector('.v').src='frame/'+id+'/'+pos[id];pos[id]++}}}
setInterval(tick,1500);setInterval(play,100);tick();
</script></html>"""


class Handler(BaseHTTPRequestHandler):
    def send(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = self.path.split("?")[0].strip("/").split("/")
        with LOCK:
            runs = dict(RUNS)
        if parts == [""]:
            return self.send(PAGE.encode(), "text/html; charset=utf-8")
        if parts == ["state"]:
            out = [dict(id=r["id"], label=r["label"], setting=r["setting"], level=r["level"], seed=r["seed"], live=r["live"], t=r["t"], limit=TIME_LIMIT,
                        first=r["first"], count=r["first"] + len(r["video"]), calls=r["calls"][-40:], calls_total=len(r["calls"]), sync=r["sync"],
                        holding=r["holding"], fate=r["fate"]) for r in sorted(runs.values(), key=lambda r: (not r["live"], r["label"]))]
            return self.send(json.dumps(out).encode(), "application/json")
        if len(parts) == 3 and parts[0] == "frame" and parts[1] in runs:
            r = runs[parts[1]]
            i = int(parts[2]) - r["first"]
            if 0 <= i < len(r["video"]):
                return self.send(r["video"][i], "image/jpeg")
        if len(parts) == 2 and parts[0] == "head" and parts[1] in runs and runs[parts[1]]["head"]:
            return self.send(runs[parts[1]]["head"], "image/jpeg")
        self.send_error(404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    threading.Thread(target=worker, daemon=True).start()
    print("live view: http://127.0.0.1:8770", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8770), Handler).serve_forever()
