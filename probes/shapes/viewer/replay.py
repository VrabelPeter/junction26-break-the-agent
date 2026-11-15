"""Replay of a shape-board run as one self-contained HTML page: what the agent did (and thought, if
the run has a trajectory) on the left, the true situation at the hole on the right, in step.

    python probes/shapes/viewer/replay.py runs/shapes/<job>/<trial> --seed 1 -o replay.html
    python probes/shapes/viewer/replay.py --policy reference --seed 1 -o replay.html     # a scripted controller

Works from a Harbor trial directory (verifier/commands.json and, if present, agent/trajectory.json),
from a bare commands.json, or plays a scripted policy itself. The simulator is deterministic, so
replaying the logged commands on the same seed reproduces the episode exactly. The page shows hidden
state (where the hole really is): it is for people, the agent never sees it. Needs numpy only.
"""
import argparse
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "environment", "env-server"))

from shapeboard import sim  # noqa: E402
from shapeboard.policies import POLICIES  # noqa: E402
from shapeboard.sim import World  # noqa: E402


def load(path):
    if os.path.isdir(path):
        cmds = json.load(open(os.path.join(path, "verifier", "commands.json")))
        tp = os.path.join(path, "agent", "trajectory.json")
        return cmds, (json.load(open(tp)).get("steps") if os.path.exists(tp) else None)
    return json.load(open(path)), None


def short(x, n=400):
    s = x if isinstance(x, str) else json.dumps(x)
    return s if len(s) <= n else s[:n] + " ..."


def replay(seed, cmds):
    w = World(seed)
    spans = []
    for c in cmds:
        a = len(w.frames)
        out = json.loads(w.call(c["tool"], **c["args"]))
        spans.append((a, max(a, len(w.frames) - 1), out))
    return w, spans


def reading(out):
    if not out.get("ok", True):
        return "refused: " + out.get("error", "")
    t, f = out["tool"], out["wrench"]
    s = (f"tool x {t['x']:+.2f} y {t['y']:+.2f} z {t['z']:+.2f} yaw {t['yaw']:+.2f} | "
         f"f {f['fx']:+.1f} {f['fy']:+.1f} {f['fz']:+.1f} | t {f['tx']:+.0f} {f['ty']:+.0f} {f['tz']:+.0f} | left {out['moves_left']}")
    return s + (" | " + ", ".join(out["events"]) if out["events"] else "")


def transcript(cmds, traj, spans):
    items, k, last = [], 0, 0

    def add_call(name, args):
        nonlocal k, last
        text = f"{name}({', '.join(f'{p}={v:g}' if isinstance(v, (int, float)) else f'{p}={v}' for p, v in args.items())})"
        if k < len(cmds) and cmds[k]["tool"] == name:
            a, b, out = spans[k]
            k, last = k + 1, b
            items.append(("call", text, a, b))
            items.append(("result", reading(out), b, b))
        else:
            items.append(("call", text, last, last))

    if traj:
        for s in traj:
            if s.get("source") == "user" and s.get("message"):
                items.append(("task", short(s["message"], 600), last, last))
            elif s.get("source") == "agent":
                if s.get("reasoning_content"):
                    items.append(("thought", short(s["reasoning_content"], 900), last, last))
                if s.get("message"):
                    items.append(("say", short(s["message"], 900), last, last))
                for tc in s.get("tool_calls") or []:
                    args = tc.get("arguments") or {}
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except ValueError:
                            args = {"raw": args}
                    add_call((tc.get("function_name") or "").split("robot_")[-1], args)
    while k < len(cmds):
        add_call(cmds[k]["tool"], cmds[k]["args"])
    return items


PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title><style>
:root{--bg:#f6f5f1;--fg:#1d1d1b;--mut:#6b6a65;--line:#d9d6cd;--card:#fff;--board:#e9dfc8;--hole:#3a3530;--air:#c98a1a;--surf:#c6432b;--in:#2f7d4f;--acc:#2456a6}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#171716;--fg:#ecebe6;--mut:#a09e97;--line:#3a3935;--card:#201f1d;--board:#5a5140;--hole:#0e0d0c;--air:#e0a63a;--surf:#e2644c;--in:#58b47c;--acc:#7fa8ee}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif}
header{padding:10px 16px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
h1{font-size:16px;margin:0}header span{color:var(--mut)}
main{display:grid;grid-template-columns:minmax(280px,1fr) minmax(320px,1.2fr);gap:12px;padding:12px 16px;height:calc(100vh - 100px);min-height:420px}
@media (max-width:800px){main{grid-template-columns:1fr;height:auto}#log{max-height:40vh}}
#log{overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px}
.it{padding:3px 8px;border-left:3px solid transparent;cursor:pointer;font:12px/1.4 ui-monospace,monospace;white-space:pre-wrap;word-break:break-word}
.it.thought,.it.say,.it.task{font-family:system-ui,sans-serif;color:var(--mut)}.it.result{color:var(--mut)}.it.call{font-weight:600}
.it.on{border-left-color:var(--acc);background:color-mix(in srgb,var(--acc) 12%,transparent)}
#view{display:flex;flex-direction:column;gap:8px;min-width:0}canvas{width:100%;flex:1;min-height:300px;background:var(--card);border:1px solid var(--line);border-radius:8px}
#hud{font:12px/1.5 ui-monospace,monospace;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 10px;white-space:pre-wrap}
footer{padding:0 16px 12px;display:flex;gap:10px;align-items:center}footer input{flex:1}button{font:inherit;padding:4px 14px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
</style></head><body><header><h1>__TITLE__</h1><span>score __SCORE__ &middot; __SEATED__ &middot; seed __SEED__</span><span>The right pane shows the true hole. The agent never sees it.</span></header>
<main><div id="log"></div><div id="view"><canvas id="c"></canvas><div id="hud"></div></div></main>
<footer><button id="play">Play</button><input id="scrub" type="range" min="0" max="0" value="0"><span id="pos"></span></footer>
<script>
const D=__DATA__;const F=D.frames,I=D.items,P=D.pegs;
const log=document.getElementById('log'),cv=document.getElementById('c'),hud=document.getElementById('hud'),scrub=document.getElementById('scrub');
I.forEach((it,i)=>{const d=document.createElement('div');d.className='it '+it[0];d.textContent=(it[0]=='call'?'> ':it[0]=='result'?'  ':'')+it[1];d.onclick=()=>{stop();show(it[3])};log.appendChild(d)});
scrub.max=F.length-1;let cur=0,timer=null;
function css(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim()}
function path(g,pts,ox,oy,s,x,y,a){const c=Math.cos(a),n=Math.sin(a);g.beginPath();pts.forEach((p,i)=>{const X=ox+s*(x+p[0]*c-p[1]*n),Y=oy-s*(y+p[0]*n+p[1]*c);i?g.lineTo(X,Y):g.moveTo(X,Y)});g.closePath()}
function draw(){const f=F[cur],p=P[f[0]],r=devicePixelRatio||1,W=cv.clientWidth,H=cv.clientHeight;cv.width=W*r;cv.height=H*r;const g=cv.getContext('2d');g.scale(r,r);
 const side=110,s=Math.min((W-side)/46,H/46),ox=(W-side)/2,oy=H/2;
 g.fillStyle=css('--board');g.fillRect(ox-22*s,oy-22*s,44*s,44*s);
 path(g,p.mouth,ox,oy,s,0,0,0);g.fillStyle=css('--mut');g.globalAlpha=.45;g.fill();g.globalAlpha=1;
 path(g,p.hole,ox,oy,s,0,0,0);g.fillStyle=css('--hole');g.fill();
 const col=f[5]=='inside'?css('--in'):f[5]=='surface'?css('--surf'):css('--air');
 path(g,p.outline,ox,oy,s,f[1],f[2],f[3]*Math.PI/180);g.fillStyle=col;g.globalAlpha=f[5]=='air'?.35:.6;g.fill();g.globalAlpha=1;g.strokeStyle=col;g.lineWidth=2;g.stroke();
 const ex=-p.err[0],ey=-p.err[1];g.strokeStyle=css('--acc');g.lineWidth=1.5;g.beginPath();g.moveTo(ox+s*ex-7,oy-s*ey);g.lineTo(ox+s*ex+7,oy-s*ey);g.moveTo(ox+s*ex,oy-s*ey-7);g.lineTo(ox+s*ex,oy-s*ey+7);g.stroke();
 g.fillStyle=css('--fg');g.font='12px system-ui';g.fillText('peg '+(f[0]+1)+' of '+P.length+': '+p.shape,ox-22*s,oy-22*s-6>12?oy-22*s-6:12);
 g.fillStyle=css('--acc');g.fillText('+ camera estimate',ox-22*s,oy+22*s+14<H?oy+22*s+14:H-4);
 const bx=W-side+30,top=oy-18*s,sc=(36*s)/(D.depth+6),z0=top+6*sc;g.fillStyle=css('--board');g.fillRect(bx-14,z0,70,D.depth*sc+10);g.fillStyle=css('--hole');g.fillRect(bx+6,z0,30,D.depth*sc);
 const h=Math.min(f[4],6);g.fillStyle=col;g.fillRect(bx+9,z0-h*sc-40,24,40);
 g.fillStyle=css('--fg');g.fillText('side view',bx-14,top-8);g.fillText((f[4]>=0?'height ':'depth ')+Math.abs(f[4]).toFixed(1)+' mm',bx-14,z0+D.depth*sc+26);
 const st=f[5]=='inside'?(f[4]<=-D.depth+1e-6?'in the hole, at the bottom':'in the hole'):f[5]=='surface'?'standing on the board':'in the air';
 hud.textContent='true offset from the hole   x '+f[1].toFixed(2)+' mm   y '+f[2].toFixed(2)+' mm   turn '+f[3].toFixed(2)+' deg\\nstate   '+st;
 let on=-1;I.forEach((it,i)=>{if(it[2]<=cur)on=i});[...log.children].forEach((d,i)=>d.classList.toggle('on',i==on));
 if(on>=0&&timer){const d=log.children[on];log.scrollTop=d.offsetTop-log.clientHeight/2}
 scrub.value=cur;document.getElementById('pos').textContent=(cur+1)+' / '+F.length}
function show(i){cur=Math.max(0,Math.min(F.length-1,i));draw()}
function stop(){clearInterval(timer);timer=null;document.getElementById('play').textContent='Play'}
document.getElementById('play').onclick=()=>{if(timer)return stop();if(cur>=F.length-1)cur=0;document.getElementById('play').textContent='Pause';timer=setInterval(()=>{if(cur>=F.length-1)return stop();show(cur+1)},40)};
scrub.oninput=()=>{stop();show(+scrub.value)};addEventListener('resize',draw);matchMedia('(prefers-color-scheme: dark)').addEventListener('change',draw);show(0);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?", help="Harbor trial directory, or a commands.json")
    ap.add_argument("--policy", choices=list(POLICIES), help="play this scripted controller instead of a recorded run")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("-o", "--out", default="replay.html")
    ap.add_argument("--title")
    a = ap.parse_args()
    if a.policy:
        w0 = World(a.seed)
        POLICIES[a.policy](lambda tool, **args: json.loads(w0.call(tool, **args)), w0.task())
        cmds, traj = w0.log, None
    elif a.run:
        cmds, traj = load(a.run)
    else:
        ap.error("give a run or --policy")
    w, spans = replay(a.seed, cmds)
    score = w.score()
    pegs = [{"shape": j["shape"], "outline": w.pegs[j["shape"]].outline.round(3).tolist(), "hole": w.pegs[j["shape"]].hole.round(3).tolist(),
             "mouth": sim._grow(w.pegs[j["shape"]].hole, sim.CHAMFER).round(3).tolist(), "err": [round(v, 3) for v in j["err"]]} for j in w.jobs]
    data = {"frames": w.frames, "items": transcript(cmds, traj, spans), "pegs": pegs, "depth": sim.DEPTH}
    title = a.title or f"Shape board: {a.policy or os.path.basename(os.path.normpath(a.run))}"
    page = (PAGE.replace("__TITLE__", html.escape(title)).replace("__SCORE__", f"{score['score']:.3f}")
            .replace("__SEATED__", f"{score['seated']} of {score['pegs']} pegs seated").replace("__SEED__", str(a.seed))
            .replace("__DATA__", json.dumps(data).replace("</", "<\\/")))
    open(a.out, "w").write(page)
    print(f"wrote {a.out}: {len(w.frames)} frames, {len(data['items'])} transcript entries, {len(page) / 1e6:.2f} MB, score {score['score']}")


if __name__ == "__main__":
    main()
