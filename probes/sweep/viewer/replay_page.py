"""One recorded run as a page for people: what the agent said and called on the left, the room on the right.

    MUJOCO_GL=egl python probes/sweep/viewer/replay_page.py <trial dir> -o visuals/sweep/<name>.html --title "..."

The simulator is deterministic, so the page repeats the logged calls in its own copy of the room and
renders that; nothing was recorded during the run. The agent's words come from the trial's trajectory.json.
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import sys
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "environment" / "env-server"))
from sweep import scene as S  # noqa: E402
from sweep.sim import World  # noqa: E402

MOVING = ("drive_to", "move_arm", "home_arm", "grasp", "release", "look", "set_torso")


def jpg(arr, q=62) -> str:
    b = io.BytesIO()
    Image.fromarray(arr).save(b, "JPEG", quality=q)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def agent_words(trial: Path, logged: list[str]) -> list[str]:
    """For every logged call, what the agent wrote just before it; one more entry for what it said at the end.
    The trajectory and the server's log do not always list the same calls (a retried or parallel call shows
    once in one and twice in the other), so the two sequences of tool names are aligned first."""
    f = trial / "agent" / "trajectory.json"
    if not f.exists():
        return []
    out, names, pending = [], [], []
    for st in json.loads(f.read_text()).get("steps", []):
        if st.get("source") != "agent":
            continue
        for key in ("reasoning_content", "message"):
            v = st.get(key)
            if isinstance(v, str) and v.strip():
                pending.append(v.strip())
        for c in st.get("tool_calls") or []:
            name = c.get("function_name", "")
            if name.startswith("robot_"):
                out.append("\n\n".join(pending))
                names.append(name[len("robot_"):])
                pending = []
            else:
                arg = json.dumps(c.get("arguments"))[:300]
                pending.append(f"[{name}] {arg}")
    import difflib
    words = [""] * len(logged)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, names, logged, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                words[j1 + k] = out[i1 + k]
        elif i2 > i1 and j2 > j1:                 # words of calls that did not line up go to the first logged call there
            words[j1] = "\n\n".join(w for w in out[i1:i2] if w)
    return words + ["\n\n".join(pending)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trial")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--title", default="Living-room sweep: one run")
    ap.add_argument("--note", default="")
    ap.add_argument("--width", type=int, default=440)
    a = ap.parse_args()
    trial = Path(a.trial)
    log = json.loads(next(trial.rglob("commands.json")).read_text())
    calls = log["calls"]
    words = agent_words(trial, [c["tool"] for c in calls])

    w = World(int(log.get("seed", 1)), int(log.get("level", 1)), privileged=log.get("setting") == "privileged")
    h = a.width * 3 // 4
    r = mujoco.Renderer(w.m, h, a.width)
    opt = mujoco.MjvOption()
    opt.geomgroup[2] = 0
    room = mujoco.MjvCamera()
    room.type = mujoco.mjtCamera.mjCAMERA_FREE

    def frame():
        base = w.base_pose()
        t = S.TABLE
        mid = np.array([(base[0] + t["cx"]) / 2, (base[1] + t["cy"]) / 2, 0.45])
        room.lookat[:] = mid
        room.distance = 2.6 + 0.6 * float(np.hypot(base[0] - t["cx"], base[1] - t["cy"]))
        room.azimuth, room.elevation = 35, -42          # from the sofa side, so the robot does not hide the table
        r.update_scene(w.d, camera=room, scene_option=opt)
        return jpg(r.render())

    def head():
        return jpg(w.camera("head", 320, 240, depth=False)["rgb"], 55)

    trash = [n for n, it in w.items.items() if it["trash"]]
    steps, events = [], []
    where = {n: w.where(n) for n in w.items}
    bin_at = w._pos("bin").copy()
    steps.append(dict(t=0.0, call="start", res="", img=frame(), cam="", say="", ev=""))
    for i, c in enumerate(calls):
        tool, args = c["tool"], c["args"]
        ev = []
        if tool in MOVING:
            held_before = dict(w.holding)
            try:
                getattr(w, tool)(**args)
            except Exception as e:                      # the server returned an error for this call; nothing moved
                ev.append("refused: " + str(e)[:80])
            for n in w.items:
                now = w.where(n)
                if now != where[n]:
                    ev.append(f"{S.KINDS[w.items[n]['kind']]['label']}: {where[n].replace('_', ' ')} to {now.replace('_', ' ')}")
                    where[n] = now
            moved = float(np.linalg.norm(w._pos("bin")[:2] - bin_at[:2]))
            if moved > 0.05 and "bin" not in held_before.values() and "bin" not in w.holding.values():
                ev.append(f"the bin was pushed {moved * 100:.0f} cm while no hand held it")
            bin_at = w._pos("bin").copy()
            for arm in ("left", "right"):
                if w.holding[arm] != held_before[arm]:
                    ev.append(f"{arm} hand " + (f"takes the {w.holding[arm]}" if w.holding[arm] else f"lets go of the {held_before[arm]}"))
        res = c.get("result", {})
        short = {k: res[k] for k in ("reached", "holding", "released", "error", "error_m") if isinstance(res, dict) and k in res}
        argtxt = ", ".join(f"{v:g}" if isinstance(v, (int, float)) else str(v) for v in args.values())
        st = dict(t=c.get("t", 0.0), call=f"{tool}({argtxt})", res=json.dumps(short) if short else "",
                  say=words[i] if words else "", ev="; ".join(ev))
        if tool in MOVING:
            st["img"] = frame()
        elif tool == "camera":
            st["cam"] = head() if args.get("name", "head") == "head" else ""
        steps.append(st)
        if ev:
            events.append(dict(step=len(steps) - 1, t=st["t"], text="; ".join(ev)))
    score = w.score()
    steps.append(dict(t=score["robot_time_s"], call="end of run", res=f"score {score['score']}", img=frame(),
                      say=words[-1] if words else "", ev=""))
    fate = ", ".join(f"{S.KINDS[w.items[n]['kind']]['label']} {score['fate'][n].replace('_', ' ')}" for n in trash)
    data = dict(title=a.title, note=a.note, steps=steps, events=events,
                summary=f"Score {score['score']}: {score['trash_in_bin']} of {score['trash_total']} pieces in the bin, "
                        f"{len(score['mistakes'])} mistakes. {fate}. {len(calls)} calls, {score['robot_time_s']} s of robot time.")
    page = PAGE.replace("__TITLE__", html.escape(a.title)).replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print(f"wrote {out}: {len(steps)} steps, {len(events)} events, {out.stat().st_size / 1e6:.1f} MB, replayed score {score['score']} ({fate})")


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>__TITLE__</title><style>
:root{--bg:#f3f5f6;--card:#fff;--ink:#15212b;--mut:#586675;--line:#d6dde2;--acc:#1d6c68;--warn:#a8500f;--warnbg:#fbe9d8}
@media (prefers-color-scheme:dark){:root{--bg:#0f1418;--card:#182027;--ink:#e5ebf0;--mut:#94a2af;--line:#2b3742;--acc:#5cc0b9;--warn:#e8a367;--warnbg:#3a2816;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1280px;margin:0 auto;padding:16px}h1{font-size:20px;margin:0 0 4px}a{color:var(--acc)}
.sub{color:var(--mut);font-size:13px;margin-bottom:10px}.note{border-left:3px solid var(--warn);background:var(--card);padding:8px 12px;border-radius:6px;margin:8px 0}
.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:14px}@media (max-width:860px){.cols{grid-template-columns:minmax(0,1fr)}}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;min-width:0}
#list{max-height:70vh;overflow:auto;display:flex;flex-direction:column}
#list button{all:unset;cursor:pointer;display:block;padding:5px 8px;border-bottom:1px solid var(--line);font:12.5px/1.4 ui-monospace,Menlo,Consolas,monospace;overflow-wrap:anywhere}
#list button[aria-current=true]{background:var(--bg);box-shadow:inset 3px 0 0 var(--acc)}
#list .t{color:var(--mut)}#list .ev{display:block;color:var(--warn);font-family:system-ui,sans-serif}
#img{width:100%;border-radius:6px;background:#000;display:block}#cam{width:42%;border-radius:6px;display:block;margin-top:8px}
#say{white-space:pre-wrap;font-size:13px;color:var(--ink);max-height:22vh;overflow:auto;margin-top:8px;border-top:1px solid var(--line);padding-top:8px}
.bar{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}.bar button{font:inherit;padding:5px 12px;border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.bar input{flex:1 1 140px;accent-color:var(--acc)}.ev{color:var(--warn)}
#events button{all:unset;cursor:pointer;display:block;padding:3px 0;color:var(--warn)}#events button:hover{text-decoration:underline}
.lab{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);font-weight:600;margin-bottom:4px}
</style></head><body><main>
<div class="sub"><a href="../../environments.html">&larr; Environments</a> · For people. Agents: project state lives in coord/, not here.</div>
<h1 id="title"></h1><div class="sub" id="summary"></div><div class="note" id="note" hidden></div>
<div class="card" style="margin-bottom:14px"><div class="lab">What happened to the things in the room (click to jump)</div><div id="events"></div></div>
<div class="cols">
<div class="card"><div class="lab">The agent's calls</div><div id="list"></div></div>
<div class="card"><div class="lab">The room at this step (a camera for people; the agent never gets it)</div><img id="img" alt="">
<div class="bar"><button id="prev">Back</button><button id="play">Play</button><button id="next">Next</button><input type="range" id="scrub" min="0" value="0"><span id="lab" class="sub" style="margin:0"></span></div>
<div id="evnow" class="ev"></div>
<div class="lab" style="margin-top:10px" id="camlab" hidden>What the head camera returned for this call</div><img id="cam" alt="" hidden>
<div class="lab" style="margin-top:10px">What the agent wrote before this call</div><div id="say"></div></div>
</div></main><script>
const D=/*DATA*/null,S=D.steps,$=i=>document.getElementById(i);let cur=0,timer=null;
$("title").textContent=D.title;$("summary").textContent=D.summary;if(D.note){$("note").hidden=false;$("note").textContent=D.note}
const imgAt=i=>{for(let j=i;j>=0;j--)if(S[j].img)return S[j].img;return""};
S.forEach((s,i)=>{const b=document.createElement("button");const t=document.createElement("span");t.className="t";t.textContent=s.t.toFixed(1)+" s  ";b.append(t,document.createTextNode(s.call+(s.res?"  "+s.res:"")));
 if(s.ev){const e=document.createElement("span");e.className="ev";e.textContent=s.ev;b.append(e)}b.onclick=()=>{stop();show(i)};$("list").append(b)});
D.events.forEach(e=>{const b=document.createElement("button");b.textContent=e.t.toFixed(0)+" s: "+e.text;b.onclick=()=>{stop();show(e.step)};$("events").append(b)});
if(!D.events.length)$("events").textContent="Nothing in the room changed place.";
function show(i){cur=Math.max(0,Math.min(S.length-1,i));const s=S[cur];$("img").src=imgAt(cur);$("scrub").value=cur;$("lab").textContent="step "+cur+" of "+(S.length-1)+" · "+s.t.toFixed(1)+" s robot time";
 $("evnow").textContent=s.ev||"";$("cam").hidden=$("camlab").hidden=!s.cam;if(s.cam)$("cam").src=s.cam;$("say").textContent=s.say||"(nothing)";
 [...$("list").children].forEach((b,j)=>{b.setAttribute("aria-current",j===cur);if(j===cur)b.scrollIntoView({block:"nearest"})})}
function stop(){if(timer){clearInterval(timer);timer=null;$("play").textContent="Play"}}
$("play").onclick=()=>{if(timer)return stop();if(cur>=S.length-1)show(0);$("play").textContent="Pause";timer=setInterval(()=>{cur>=S.length-1?stop():show(cur+1)},450)};
$("prev").onclick=()=>{stop();show(cur-1)};$("next").onclick=()=>{stop();show(cur+1)};$("scrub").max=S.length-1;$("scrub").oninput=e=>{stop();show(+e.target.value)};show(0);
</script></body></html>
"""

if __name__ == "__main__":
    main()
