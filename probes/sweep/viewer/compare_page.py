"""Levels 1 to 3 side by side, as a page for people: a film of every run on main since the arm fix, per level and per model.

    MUJOCO_GL=egl python probes/sweep/viewer/compare_page.py               # writes visuals/sweep/compare.html and visuals/sweep/videos/*.mp4
    MUJOCO_GL=egl python probes/sweep/viewer/compare_page.py --rebuild     # replay and film everything, ignoring the cache

Films are cached: videos/films.json keeps, per film, a key over its run's command log, room, setting and a fingerprint
of the simulator, scene, robot model and filming code, with the score the replay gave. A film whose key is unchanged is
neither replayed nor rendered; only new runs, or all of them after a simulator change, cost time.

Every row is one room (seed) in one setting, standard or privileged, and is folded until opened; its films load only then.

Columns: the scripted reference, then every model in models.json. Rows: the rooms (seeds) of a level.
A model's cell is filled from results/sweep/agent-runs/*.summary.json (standard setting, recorded since the
arm fix on main, newest per model, level, seed and setting); a cell without such a run says so. The reference cell is
the Harbor log in results/sweep/ when there is one, otherwise the same controller run in-process here.

Nothing was filmed during the runs. The simulator is deterministic, so each film is the logged calls repeated in
a copy of the room; the page says whether the copy ended with the score the run was given. Films show robot
time only (thinking costs none), eight times faster than real. Needs ffmpeg (on PATH, or `pip install imageio-ffmpeg`).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import html
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(HERE.parent / "environment" / "env-server"))
sys.path.insert(0, str(HERE.parent))
from sweep import policies as P  # noqa: E402
from sweep.sim import World  # noqa: E402

# Runs count when they were made on main's line from the arm fix on (decision 1114-no-build-tags-...): the build is the
# latest commit; a tag other than the arm-fix marker names a variant (task structure or simulator ablation) and its runs
# are left out here.
FROZEN = dict(tag="sweep-frozen-1", since="2026-11-14T18:32")
TASK_FILES = ("instruction.md", "task.toml", "environment", "tests", "solution")       # what the agent and the scorer run on
MOVING = ("drive_to", "move_arm", "home_arm", "grasp", "release", "look", "set_torso")
LEVELS = {1: "One piece of trash on the coffee table.",
          2: "Four pieces of trash and two personal items on the coffee table.",
          3: "Eight pieces of trash and four personal items on the table and the sofa, plus a jacket."}
SEEDS = {1: [1, 2, 3], 2: [1, 2, 3], 3: [1]}
W, H, FPS, EVERY = 640, 480, 20, 8          # one film frame per 8 recorded poses (0.05 s each): 8x real time at 20 fps


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            sys.exit("ffmpeg not found: install it or `pip install imageio-ffmpeg`")
    return exe


KEEP_FILMS = False
REBUILD = False
SIM_DIR = HERE.parent / "environment" / "env-server"
CACHE: dict = {}            # film name -> {"key": ..., "score": ...}; kept in videos/films.json next to the films


def sim_fingerprint() -> str:
    """Hash of everything a replayed film depends on besides its own commands: the simulator, the scene, the
    scripted controllers, the robot's model files and how films are made. A change to any of them re-films all."""
    h = hashlib.sha256(f"{W}x{H}@{FPS}/{EVERY}".encode())
    for f in sorted(list((SIM_DIR / "sweep").glob("*.py")) + [p for p in (SIM_DIR / "assets").rglob("*") if p.is_file()]):
        h.update(str(f.relative_to(SIM_DIR)).encode())
        h.update(f.read_bytes())
    h.update(film.__code__.co_code)
    return h.hexdigest()


def film_key(fingerprint: str, source: bytes, seed: int, level: int, privileged: bool) -> str:
    return hashlib.sha256(fingerprint.encode() + source + f"|{seed}|{level}|{privileged}".encode()).hexdigest()


PLAN: list | None = None     # while planning: the films that have to be made, as (key, job)
PLACEHOLDER = dict(score=0.0, trash_in_bin=0, trash_total=0, mistakes=[], robot_time_s=0.0)


def make_film(job):
    """One film, in a worker process: job = (kind, seed, level, privileged, calls, out, keep_films)."""
    global KEEP_FILMS
    kind, seed, level, privileged, calls, out, KEEP_FILMS = job
    w = World(seed, level, privileged=privileged)
    return film(w, P.POLICIES["reference"] if kind == "reference" else replay(calls), Path(out))


def cached(out: Path, key: str, job):
    """The film and its score are reused when the film exists and nothing it depends on changed (same key).
    Otherwise the film is planned (made in parallel, see main) and a placeholder stands in. --rebuild ignores the cache."""
    hit = CACHE.get(out.name)
    if not REBUILD and hit and hit["key"] == key and out.exists():
        return hit["score"]
    if PLAN is not None:
        PLAN.append((key, job))
        return PLACEHOLDER
    score = make_film(job)
    CACHE[out.name] = dict(key=key, score=score)
    return score


def film(w: World, play, out: Path) -> dict:
    """Run `play(w)` with every pose recorded, score the room, and write the film. Returns the score details.
    With --keep-films an existing film is not rendered again (the run is still repeated, for its score)."""
    w.frames, marks, steps = [], [(0, 0.0)], w._steps

    def counted(n, count=True):
        steps(n, count)
        marks.append((len(w.frames), w.robot_time))
    w._steps = counted
    try:
        play(w)
    except Exception as e:                                  # a controller that gives up still gets scored
        print("   stopped:", repr(e)[:120])
    score = w.score()
    poses, w.frames = w.frames, None
    at = np.interp(np.arange(len(poses)), [m[0] for m in marks], [m[1] for m in marks])

    if KEEP_FILMS and out.exists():
        return score
    scratch, r = mujoco.MjData(w.m), mujoco.Renderer(w.m, H, W)
    hide = mujoco.MjvOption()
    hide.geomgroup[2] = 0
    enc = subprocess.Popen([ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "27", "-preset", "slow",
                            "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)

    def shot(q, text):
        scratch.qpos[:] = q
        mujoco.mj_forward(w.m, scratch)
        r.update_scene(scratch, camera="overview", scene_option=hide)
        im = Image.fromarray(r.render())
        d = ImageDraw.Draw(im)
        d.rectangle([0, H - 22, W, H], fill=(0, 0, 0))
        d.text((8, H - 19), text, font_size=14, fill=(255, 255, 255))
        return im.tobytes()

    picked = list(range(0, len(poses), EVERY)) or [None]
    for i in picked:
        enc.stdin.write(shot(w.d.qpos if i is None else poses[i], f"robot time {0 if i is None else at[i]:4.0f} s   (8x)"))
    end = shot(w.d.qpos, f"end: score {score['score']:g}, {score['trash_in_bin']} of {score['trash_total']} trash in the bin, robot time {score['robot_time_s']:.0f} s")
    for _ in range(FPS * 3):
        enc.stdin.write(end)
    enc.stdin.close()
    enc.wait()
    r.close()
    return score


def replay(calls):
    def play(w):
        for c in calls:
            if c["tool"] in MOVING and not w.closed:
                w.call(c["tool"], **c["args"])
    return play


def git_ok(*args) -> bool:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True).returncode == 0


def frozen(summary: dict) -> bool:
    """Recorded since the arm fix, from a clean commit on main's line at or after it, and not on a tagged variant."""
    if summary.get("date", "") < FROZEN["since"] or summary.get("score") is None:
        return False
    commit = summary.get("commit", "")
    # "+uncommitted" counts only when someone checked file by file that the uncommitted change was the run's own
    # model entry and recorded that in the summary (`uncommitted_checked`).
    if not commit or ("+" in commit and not summary.get("uncommitted_checked")):
        return False
    commit = commit.split("+")[0]
    if not (git_ok("merge-base", "--is-ancestor", FROZEN["tag"], commit) and git_ok("merge-base", "--is-ancestor", commit, "HEAD")):
        return False
    tags = subprocess.run(["git", "tag", "--points-at", commit], cwd=ROOT, capture_output=True, text=True).stdout.split()
    return all(t == FROZEN["tag"] for t in tags)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=str(ROOT / "visuals" / "sweep" / "compare.html"))
    ap.add_argument("--keep-films", action="store_true", help="do not render films that already exist (runs are still replayed)")
    ap.add_argument("--rebuild", action="store_true", help="replay and film every run, ignoring videos/films.json")
    a = ap.parse_args()
    global KEEP_FILMS, REBUILD, CACHE
    KEEP_FILMS, REBUILD = a.keep_films, a.rebuild
    out = Path(a.out)
    vids = out.parent / "videos"
    vids.mkdir(parents=True, exist_ok=True)
    manifest = vids / "films.json"
    CACHE = json.loads(manifest.read_text()) if manifest.exists() else {}
    fp = sim_fingerprint()
    models = json.loads((HERE.parent / "models.json").read_text())
    # Models that are not in the task's own list: open models we serve ourselves (serving/qwen_vl_modal.py). They
    # played a copy of the frozen task whose only change is their entry in the model list; a column appears once
    # such a model has a run.
    extra = json.loads((HERE / "extra_models.json").read_text()) if (HERE / "extra_models.json").exists() else {}
    keep = ROOT / "results" / "sweep" / "agent-runs"

    runs = {}                                               # (model, level, seed) -> newest summary on the frozen build
    for f in sorted(glob.glob(str(keep / "*.summary.json"))):
        s = json.loads(Path(f).read_text())
        if s.get("model") in extra and s.get("model") not in models and frozen(s):
            models[s["model"]] = extra[s["model"]]
        # A model's column shows the reasoning effort its entry names now; runs recorded at another effort are left out.
        if s.get("variant") and s["variant"] != models.get(s.get("model"), {}).get("variant", s["variant"]):
            continue
        if s.get("model") in models and frozen(s):
            k = (s["model"], s["level"], s["seed"], s["setting"])
            if k not in runs or s["date"] > runs[k]["date"]:
                runs[k] = s
    # The no-shell variant (branches sweep-no-shell*, experiments 1115-0208 and 1115-0513): the agent has no shell and
    # no depth file, only the pictures. Its runs (run name tagged "noshell") never enter the tables above; they get a
    # section of their own, next to the same model's run with a shell on the same room.
    noshell = {}                                            # (model, level, seed) -> newest no-shell summary
    for f in sorted(glob.glob(str(keep / "*-noshell.summary.json"))):
        s = json.loads(Path(f).read_text())
        if s.get("score") is not None and s.get("setting") == "standard":
            k = (s["model"], s["level"], s["seed"])
            if k not in noshell or s["date"] > noshell[k]["date"]:
                noshell[k] = s
    seeds = {lv: sorted(set(SEEDS[lv]) | {k[2] for k in runs if k[1] == lv and k[3] == "standard"}) for lv in LEVELS}
    told = {lv: sorted({k[2] for k in runs if k[1] == lv and k[3] == "privileged"}) for lv in LEVELS}

    # Pass 1 finds the films that are missing or out of date; they are made side by side, one per core; pass 2 (all
    # cache hits by then) builds the cells.
    global PLAN
    PLAN = []
    collect(vids, fp, seeds, told, runs, models, keep, quiet=True, noshell=noshell)
    todo, PLAN = PLAN, None
    if todo:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor
        print(f"{len(todo)} of the films are new or out of date; making them on {min(len(todo), os.cpu_count() or 1)} cores", flush=True)
        t = time.time()
        with ProcessPoolExecutor(max_workers=min(len(todo), os.cpu_count() or 1), mp_context=multiprocessing.get_context("spawn")) as ex:
            for (key, job), score in zip(todo, ex.map(make_film, [j for _, j in todo])):
                CACHE[Path(job[5]).name] = dict(key=key, score=score)
        print(f"made in {time.time() - t:.0f} s", flush=True)
    REBUILD = False
    cells, made = collect(vids, fp, seeds, told, runs, models, keep, noshell=noshell)
    for old in vids.glob("*.mp4"):
        if old.name not in made:
            old.unlink()
    manifest.write_text(json.dumps({k: v for k, v in sorted(CACHE.items()) if k in made}, indent=1) + "\n")
    page(out, vids, cells, seeds, told, models, noshell)


def collect(vids, fp, seeds, told, runs, models, keep, quiet=False, noshell=None):
    """Every cell of the page: the reference and each model's run per level, room and setting, with its film."""
    say = (lambda *_: None) if quiet else (lambda *x: print(*x, flush=True))
    cells, made = {}, set()
    for lv in LEVELS:
        for seed in seeds[lv]:
            logs = sorted(glob.glob(str(ROOT / "results" / "sweep" / f"reference-cameras-l{lv}-s{seed}-harbor-*.commands.json")))
            name = f"reference-l{lv}-s{seed}.mp4"
            t = time.time()
            if logs:
                log = json.loads(Path(logs[-1]).read_text())
                given = json.loads(Path(logs[-1].replace(".commands.", ".details.")).read_text())
                key = film_key(fp, Path(logs[-1]).read_bytes(), seed, lv, False)
                sc = cached(vids / name, key, ("replay", seed, lv, False, log["calls"], str(vids / name), KEEP_FILMS))
                src = f"Harbor run, results/sweep/{Path(logs[-1]).name.replace('.commands.json', '')}"
                calls = len(log["calls"])
            else:
                key = film_key(fp, b"policy:reference", seed, lv, False)
                sc = cached(vids / name, key, ("reference", seed, lv, False, None, str(vids / name), KEEP_FILMS))
                given, src, calls = sc, "run in-process for this page (python -m sweep.run --policy reference), not under Harbor", None
            cells["reference", lv, seed, "standard"] = dict(video=name, score=given["score"], d=sc, same=sc["score"] == given["score"], src=src, calls=calls,
                                                 replay=f"reference-cameras-seed{seed}.html" if logs and lv == 1 else None)
            made.add(name)
            say(f"reference level {lv} seed {seed}: {sc['score']}  ({time.time() - t:.0f} s)")
        for seed, setting in [(x, "standard") for x in seeds[lv]] + [(x, "privileged") for x in told[lv]]:
            for m in models:
                s = runs.get((m, lv, seed, setting))
                if not s:
                    continue
                log = json.loads((keep / f"{s['run']}.commands.json").read_text())
                name = f"{s['run']}.mp4"
                key = film_key(fp, (keep / f"{s['run']}.commands.json").read_bytes(), seed, lv, setting == "privileged")
                sc = cached(vids / name, key, ("replay", seed, lv, setting == "privileged", log["calls"], str(vids / name), KEEP_FILMS))
                cells[m, lv, seed, setting] = dict(video=name, score=s["score"], d=sc, same=sc["score"] == s["score"], calls=s["tool_calls"],
                                          src=f"Harbor run {s['run']}, {s['minutes']:.0f} min", replay=f"{s['run']}.html", error=s.get("error"))
                made.add(name)
                say(f"{m} level {lv} seed {seed} {setting}: run {s['score']}, copy {sc['score']}")
    for (m, lv, seed), s in sorted((noshell or {}).items()):
        log = json.loads((keep / f"{s['run']}.commands.json").read_text())
        name = f"{s['run']}.mp4"
        key = film_key(fp, (keep / f"{s['run']}.commands.json").read_bytes(), seed, lv, False)
        sc = cached(vids / name, key, ("replay", seed, lv, False, log["calls"], str(vids / name), KEEP_FILMS))
        cells[m, lv, seed, "noshell"] = dict(video=name, score=s["score"], d=sc, same=sc["score"] == s["score"], calls=s["tool_calls"],
                                             src=f"Harbor run {s['run']}, {s['minutes']:.0f} min", replay=None, error=s.get("error"))
        made.add(name)
        say(f"{m} level {lv} seed {seed} standard, no shell: run {s['score']}, copy {sc['score']}")
    return cells, made


def page(out, vids, cells, seeds, told, models, noshell=None):
    """Write the page from the cells."""

    e = html.escape
    cols = [("reference", "The reference")] + [(m, models[m]["label"].split(" (")[0]) for m in models]
    SETTING = {"standard": ("std", "standard", "cameras (colour, depth, calibration) and joint readings"),
               "privileged": ("priv", "privileged", "also told the position and kind of every object")}

    def badge(setting):
        cls, name, what = SETTING[setting]
        return f'<span class="set {cls}" title="{e(what)}">{name}</span>'

    def tone(x):
        return "ok" if x >= 0.99 else "bad" if x <= 0.01 else "mid"

    def mean(col, lv, setting="standard"):
        got = [c for (m, l, _, st), c in cells.items() if m == col and l == lv and st == setting]
        cut = sum(1 for c in got if c.get("error"))
        note = f"{len(got)} run" + ("s" if len(got) != 1 else "") + (f", {cut} cut off" if cut else "")
        if got:
            v = sum(c["score"] for c in got) / len(got)
            return f'<b class="{tone(v)}">{v:.2f}</b> <small>{note}</small>'
        return "<small>not applicable</small>" if col == "reference" and setting == "privileged" else "<small>no run yet</small>"

    head = "".join(f"<th>{e(label)}</th>" for _, label in cols)
    summary = "".join(f"<tr><td>Level {lv} {badge('standard')}</td>" + "".join(f"<td>{mean(c, lv)}</td>" for c, _ in cols) + "</tr>" for lv in LEVELS)
    summary += "".join(f"<tr><td>Level {lv} {badge('privileged')}</td>" + "".join(f"<td>{mean(c, lv, 'privileged')}</td>" for c, _ in cols) + "</tr>"
                       for lv in LEVELS if told[lv])
    parts = []
    for lv, what in LEVELS.items():
        rows = []
        for seed, setting in [(x, "standard") for x in seeds[lv]] + [(x, "privileged") for x in told[lv]]:
            cards, chips = [], []
            for col, label in cols:
                c = cells.get((col, lv, seed, setting))
                if not c:
                    why = (f"Not applicable: the reference works from the cameras (see seed {seed}, standard)."
                           if col == "reference" and setting == "privileged" else "No run yet.")
                    cards.append(f'<div class="cell none"><div class="who">{e(label)}</div>{why}</div>')
                    continue
                chips.append(f'<span class="mini {tone(c["score"])}">{e(label)} <b>{c["score"]:g}</b></span>')
                d = c["d"]
                wrong = "; ".join(m["why"] for m in d["mistakes"])
                facts = [f"{d['trash_in_bin']} of {d['trash_total']} trash in the bin", wrong or "no mistakes", f"{d['robot_time_s']:.0f} s robot time"]
                if c["calls"]:
                    facts.append(f"{c['calls']} tool calls")
                agree = "" if c["same"] else f'<div class="warn">The copy filmed here ended with score {d["score"]:g}, not the run\'s {c["score"]:g}: the film may differ from the run.</div>'
                if c.get("error"):
                    agree += f'<div class="warn"><b>Not a clean run.</b> {e(c["error"])}</div>'
                link = f' · <a href="{e(c["replay"])}">step by step</a>' if c.get("replay") and (out.parent / c["replay"]).exists() else ""
                cards.append(f'<div class="cell"><div class="who">{e(label)}</div>'
                             f'<video data-src="videos/{e(c["video"])}" controls muted playsinline preload="none"></video>'
                             f'<div class="score {tone(c["score"])}">{c["score"]:g}</div>'
                             f'<div class="facts">{e(" · ".join(facts))}</div>{agree}<div class="src">{e(c["src"])}{link}</div></div>')
            rows.append(f'<details class="row"><summary><span class="seed">Seed {seed}</span>{badge(setting)}'
                        f'<span class="minis">{"".join(chips) or "<small>no runs</small>"}</span></summary>'
                        f'<div class="bar"><button type="button" class="play">Play all in this row</button>'
                        f'<span class="sub">{SETTING[setting][2].capitalize()}.</span></div>'
                        f'<div class="cells">{"".join(cards)}</div></details>')
        parts.append(f'<section><h2>Level {lv}</h2><p class="sub">{e(what)}</p>{"".join(rows)}</section>')

    def card(label, c):
        d = c["d"]
        wrong = "; ".join(m["why"] for m in d["mistakes"])
        facts = [f"{d['trash_in_bin']} of {d['trash_total']} trash in the bin", wrong or "no mistakes", f"{d['robot_time_s']:.0f} s robot time"]
        if c["calls"]:
            facts.append(f"{c['calls']} tool calls")
        agree = "" if c["same"] else f'<div class="warn">The copy filmed here ended with score {d["score"]:g}, not the run\'s {c["score"]:g}: the film may differ from the run.</div>'
        if c.get("error"):
            agree += f'<div class="warn"><b>Not a clean run.</b> {e(c["error"])}</div>'
        return (f'<div class="cell"><div class="who">{e(label)}</div>'
                f'<video data-src="videos/{e(c["video"])}" controls muted playsinline preload="none"></video>'
                f'<div class="score {tone(c["score"])}">{c["score"]:g}</div>'
                f'<div class="facts">{e(" · ".join(facts))}</div>{agree}<div class="src">{e(c["src"])}</div></div>')

    if noshell:
        names = dict(cols)
        rows = []
        for lv, seed in sorted({(k[1], k[2]) for k in noshell}):
            cards, chips = [], []
            ref = cells.get(("reference", lv, seed, "standard"))
            if ref:
                cards.append(card("The reference (with the depth file)", ref))
                chips.append(f'<span class="mini {tone(ref["score"])}">The reference <b>{ref["score"]:g}</b></span>')
            for m in sorted(k[0] for k in noshell if k[1:] == (lv, seed)):
                label = names.get(m, m)
                c = cells[m, lv, seed, "noshell"]
                cards.append(card(f"{label}, no shell", c))
                chips.append(f'<span class="mini {tone(c["score"])}">{e(label)}, no shell <b>{c["score"]:g}</b></span>')
                w = cells.get((m, lv, seed, "standard"))
                if w:
                    cards.append(card(f"{label}, with a shell", w))
                    chips.append(f'<span class="mini {tone(w["score"])}">{e(label)}, with a shell <b>{w["score"]:g}</b></span>')
                else:
                    cards.append(f'<div class="cell none"><div class="who">{e(label)}, with a shell</div>No run with a shell on this room.</div>')
            rows.append(f'<details class="row"><summary><span class="seed">Level {lv}, seed {seed}</span>{badge("standard")}'
                        f'<span class="set var">no shell</span><span class="minis">{"".join(chips)}</span></summary>'
                        f'<div class="bar"><button type="button" class="play">Play all in this row</button>'
                        f'<span class="sub">Cameras and joint readings; the agent cannot run code or fetch the depth file.</span></div>'
                        f'<div class="cells">{"".join(cards)}</div></details>')
        parts.append('<section id="no-shell"><h2>Variant: the agent has no shell</h2>'
                     '<p class="sub">An ablation on a separate branch, not the submitted task and not counted in the table at the top. '
                     'The agent gets the same pictures, including depth as a grey picture, but cannot run code or download the measured depth; '
                     'it has to place the hand from what it sees. The scripted reference still uses the depth file. One room, one run per model.</p>'
                     + "".join(rows) + '</section>')

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    page = PAGE.replace("<!--SUMMARY-->", f"<div class='scroll'><table class='sum'><tr><th></th>{head}</tr>{summary}</table></div>").replace("<!--LEVELS-->", "".join(parts)) \
               .replace("<!--NOSHELL-->", '<p class="sub">Also on this page: <a href="#no-shell">the same task without a shell</a> (a variant), GPT-6 Astra and Claude Fable 5.2 side by side.</p>' if noshell else "") \
               .replace("<!--BUILT-->", e(f"Runs on main from the arm fix ({FROZEN['tag']}) on; tagged variants are left out of the levels; the no-shell variant has its own section at the end. Page made {time.strftime('%Y-%m-%d %H:%M')} at {sha} by probes/sweep/viewer/compare_page.py."))
    out.write_text(page, encoding="utf-8")
    size = sum(f.stat().st_size for f in vids.glob("*.mp4")) / 1e6
    print(f"wrote {os.path.relpath(out, ROOT)} and {len({c['video'] for c in cells.values()})} films ({size:.1f} MB)")


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Levels and models</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&family=Space+Grotesk:wght@500;600&display=swap">
<style>
/* Same design tokens as the scene page (dashboard.template.html) and the Environment tab. */
:root{--bg:#f3f5f6;--surface:#fff;--sunken:#e9edef;--ink:#15212b;--muted:#586675;--line:#d6dde2;--accent:#1d6c68;--accent-ink:#fff;
 --trash:#a8500f;--trash-bg:#fbe9d8;--keep:#2a4d8f;--keep-bg:#e1e9f8;--good:#1c7448;--bad:#b0271f;--mid:#9a6700;
 --display:"Space Grotesk","Inter",system-ui,sans-serif;--body:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:"JetBrains Mono",ui-monospace,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1418;--surface:#182027;--sunken:#111920;--ink:#e5ebf0;--muted:#94a2af;--line:#2b3742;
 --accent:#5cc0b9;--accent-ink:#08201f;--trash:#e8a367;--trash-bg:#3a2816;--keep:#93b3ee;--keep-bg:#1c2a44;--good:#6fd09c;--bad:#f28a82;--mid:#e3b341;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0f1418;--surface:#182027;--sunken:#111920;--ink:#e5ebf0;--muted:#94a2af;--line:#2b3742;
 --accent:#5cc0b9;--accent-ink:#08201f;--trash:#e8a367;--trash-bg:#3a2816;--keep:#93b3ee;--keep-bg:#1c2a44;--good:#6fd09c;--bad:#f28a82;--mid:#e3b341;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--body)}
main{max-width:1500px;margin:0 auto;padding:24px 16px 64px;display:flex;flex-direction:column;gap:18px}
a{color:var(--accent)}h1,h2{font-family:var(--display);font-weight:600;margin:0;letter-spacing:-.01em}h1{font-size:30px;line-height:1.15}h2{font-size:21px}
p{margin:0;max-width:900px}.sub{color:var(--muted);font-size:13px}small{color:var(--muted)}
section{display:flex;flex-direction:column;gap:8px;margin-top:10px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.scroll{overflow-x:auto}table{border-collapse:collapse}
.sum{background:var(--surface);border:1px solid var(--line);border-radius:10px;width:100%}
.sum th,.sum td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums;white-space:nowrap}
.sum th{font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}.sum tr:last-child td{border-bottom:0}
.ok{color:var(--good)}.bad{color:var(--bad)}.mid{color:var(--mid)}
.set{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid currentColor;vertical-align:1px}
.var{color:var(--mid);margin-left:-4px}.std{color:var(--keep);background:var(--keep-bg)}.priv{color:var(--trash);background:var(--trash-bg)}
details.row{background:var(--surface);border:1px solid var(--line);border-radius:10px}
details.row>summary{list-style:none;cursor:pointer;display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;padding:10px 14px}
details.row>summary::-webkit-details-marker{display:none}
details.row>summary::before{content:"\\25B8";color:var(--muted);transition:transform .15s}details.row[open]>summary::before{transform:rotate(90deg)}
details.row>summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:10px}
.seed{font-family:var(--display);font-weight:600}
.minis{display:flex;flex-wrap:wrap;gap:6px}.mini{font-size:12.5px;padding:1px 8px;border-radius:999px;background:var(--sunken);color:var(--ink)}
.mini b{font-variant-numeric:tabular-nums}.mini.ok b{color:var(--good)}.mini.bad b{color:var(--bad)}.mini.mid b{color:var(--mid)}
.bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:0 14px 8px}
.cells{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(min(100%,280px),1fr));padding:0 14px 14px}
.cell{border:1px solid var(--line);border-radius:8px;padding:10px;background:var(--bg);min-width:0}
.who{font-weight:600;margin-bottom:6px}video{width:100%;aspect-ratio:4/3;background:#000;border-radius:6px;display:block}
.score{font:600 26px/1.2 var(--display);font-variant-numeric:tabular-nums;margin-top:6px}
.facts{font-size:13.5px}.src{font-size:12px;color:var(--muted);overflow-wrap:anywhere;margin-top:2px}.warn{font-size:12.5px;color:var(--mid);overflow-wrap:anywhere}
.none{color:var(--muted);font-size:13.5px}.none .who{color:var(--ink)}
button{font:500 13px var(--body);padding:5px 12px;border-radius:7px;border:1px solid var(--line);background:var(--surface);color:var(--ink);cursor:pointer}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
</style></head><body><main>
<div class="sub"><a href="../../environment.html">&larr; Environment</a> · For people. Agents: project state lives in coord/, not here.</div>
<h1>Levels and models, side by side</h1>
<p>A wheeled two-arm robot has to get the trash, and only the trash, into the bin. Each film is one whole run, seen from a room camera for people
(the agent never gets this view). It shows robot time only, eight times faster than real; the time a model spends thinking is not in it.
Reward = share of the trash in the bin at the end, halved for every mistake (a personal item in the bin or on the floor, or the bin tipped over).</p>
<p class="sub">Every row names its setting. <span class="set std">standard</span> cameras (colour, depth, calibration) and joint readings only, as in the task.
<span class="set priv">privileged</span> an ablation: also told the position and kind of every object and of both handles.
The newest run per model, room and setting is shown; rows are folded, and a row's films load only when you open it.</p>
<!--SUMMARY-->
<!--NOSHELL-->
<!--LEVELS-->
<p class="sub" style="margin-top:20px"><!--BUILT--> The films are the logged calls repeated in a copy of the deterministic simulator; nothing was recorded during the runs.</p>
</main><script>
document.querySelectorAll("details.row").forEach(d=>d.addEventListener("toggle",()=>{
 d.querySelectorAll("video").forEach(v=>{if(d.open){if(!v.getAttribute("src"))v.src=v.dataset.src}else v.pause()})}));
document.querySelectorAll("button.play").forEach(b=>b.onclick=()=>{const v=[...b.closest("details").querySelectorAll("video")];const on=v.some(x=>!x.paused);
 v.forEach(x=>{if(on)x.pause();else{x.currentTime=0;x.play()}});b.textContent=on?"Play all in this row":"Pause all"});
</script></body></html>
"""

if __name__ == "__main__":
    main()
