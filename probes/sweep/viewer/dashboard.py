"""Build the dashboard page: what the room looks like, how an end state is scored, and one rollout.

    MUJOCO_GL=egl python probes/sweep/viewer/dashboard.py -o runs/sweep/dashboard.html
    python probes/sweep/viewer/dashboard.py --standalone --data-from visuals/sweep/index.html -o visuals/sweep/index.html   # text-only change

Every picture and every score on the page comes from the simulator and its scorer; nothing is drawn by hand.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "environment" / "env-server"))
try:                                # the simulator; not needed with --data-from
    import numpy as np
    from PIL import Image
    from sweep import policies as P  # noqa: E402
    from sweep import scene as S  # noqa: E402
    from sweep.sim import SETTLE, TIME_LIMIT, World  # noqa: E402
except ImportError as missing:
    SIM_MISSING = missing
else:
    SIM_MISSING = None


def jpg(arr: np.ndarray, size=None, q: int = 80) -> str:
    im = Image.fromarray(arr)
    if size:
        im = im.resize(size, Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=q)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def shot(w: World, cam: str, wh=(960, 720), size=None, walls=False) -> str:
    return jpg(w.camera(cam, wh[0], wh[1], depth=False, all_walls=walls)["rgb"], size)


def depth_picture(depth: np.ndarray, near=0.4, far=4.5) -> np.ndarray:
    t = np.clip((depth - near) / (far - near), 0, 1)[..., None]
    stops = np.array([[250, 230, 120], [80, 190, 160], [45, 110, 160], [30, 30, 70]], float)   # near -> far
    x = t * (len(stops) - 1)
    i = np.clip(np.floor(x).astype(int), 0, len(stops) - 2)
    f = x - i
    return (stops[i[..., 0]] * (1 - f) + stops[i[..., 0] + 1] * f).astype(np.uint8)


def item_rows(w: World) -> list:
    return [dict(name=n, label=S.KINDS[it["kind"]]["label"], trash=it["trash"], surface=it["surface"]) for n, it in w.items.items()]


def levels() -> list:
    out = []
    for level in (1, 2, 3):
        w = World(1, level)
        row = dict(level=level, note=S.LEVELS[level]["note"], items=item_rows(w),
                   overview=shot(w, "overview"), top=shot(w, "top", (720, 720)))
        # what the robot sees when it stands in front of the table and looks down at it
        w.drive_to(S.TABLE["cx"], S.TABLE["cy"] - 1.35, math.pi / 2)
        w.look(0.0, -0.80)
        cam = w.camera("head", 640, 480, depth=True)
        row["head"] = jpg(cam["rgb"])
        row["depth"] = jpg(depth_picture(cam["depth"]))
        row["calibration"] = cam["calibration"]
        row["observation"] = w.observe()
        out.append(row)
    return out


def presets() -> tuple[list, list]:
    w = World(1, 3, privileged=True)
    start = w.save()
    trash = [n for n, it in w.items.items() if it["trash"]]
    keep = [n for n, it in w.items.items() if not it["trash"] and it["kind"] != "jacket"]
    out = []

    def add(pid, title, blurb, moves=(), tip=False, base=None):
        w.load(base if base is not None else ready)
        for slot, (n, where) in enumerate(moves):
            w.place(n, where, slot)
        w.rest(2.5)
        if tip:
            p = w._pos("bin")
            w.place_tool("bin", float(p[0]), float(p[1]) - 0.25, 0.12, 0.0, tipped=True)
            w.rest(1.5)
        r = w.score()
        out.append(dict(id=pid, title=title, blurb=blurb, image=shot(w, "stage"), fate=r["fate"], bin_upright=w.bin_upright(),
                        score=r["score"], progress=r["progress"], care=r["care"], trash_in_bin=r["trash_in_bin"],
                        trash_total=r["trash_total"], mistakes=r["mistakes"]))
        print(f"  preset {pid}: score {r['score']}  ({r['trash_in_bin']}/{r['trash_total']}, mistakes {len(r['mistakes'])})")

    add("nothing", "Do nothing", "The robot never moves.", base=start)
    w.load(start)
    P.fetch_tools(w)
    fetched = w.save()
    add("tools", "Fetch the tools, then stop", "Brush and bin are in the hands. Nothing has been swept.", base=fetched)
    # set the bin down at the south edge of the table with the robot's own actions, then vary what lies where
    w.load(fetched)
    s = S.SURFACES["table"]
    stand = s["y"][0] - P.SWEEP_STANDOFF
    P.travel(w, S.TABLE["cx"] - 0.03, stand - 0.2, math.pi / 2)
    w.drive_to(S.TABLE["cx"] - 0.03, stand, math.pi / 2)
    h = w.observe()["right_hand"]
    w.move_arm("right", h["x"], h["y"], S.BIN["height"] - 0.006, h["yaw"])
    w.release("right")
    w.move_arm("right", h["x"], h["y"], h["z"] + 0.10, h["yaw"])
    w.drive_to(S.TABLE["cx"] - 0.03, stand - 0.35, math.pi / 2)
    w.drive_to(S.TABLE["cx"] - 1.15, stand - 0.20, 0.5)          # step aside so the picture shows the table and the bin
    ready = w.save()
    add("one", "One piece in the bin", "One of eight pieces of trash is in the bin.", [(trash[0], "in_bin")])
    add("half", "Half in the bin, half on the floor", "Four pieces were swept past the bin. Trash on the floor earns nothing and costs nothing.",
        [(n, "in_bin") for n in trash[:4]] + [(n, "on_floor") for n in trash[4:]])
    add("all", "All trash in the bin", "The full score: every piece of trash is in the bin and nothing else was disturbed.",
        [(n, "in_bin") for n in trash])
    add("plus_one", "All trash, and the " + S.KINDS[w.items[keep[0]]["kind"]]["label"], "One personal item went into the bin with the trash: the score is halved.",
        [(n, "in_bin") for n in trash + keep[:1]])
    add("knocked", "All trash, one item knocked to the floor", "A personal item on the floor is a mistake too.",
        [(n, "in_bin") for n in trash] + [(keep[1], "on_floor")])
    add("everything", "Sweep everything in", "No judgement at all: every small thing goes into the bin. Four mistakes, one sixteenth of the score.",
        [(n, "in_bin") for n in trash + keep])
    add("tipped", "All trash in, then the bin is knocked over", "Trash only counts inside an upright bin, and a bin on its side is a mistake.",
        [(n, "in_bin") for n in trash], tip=True)
    w.load(start)
    return out, item_rows(w)


def rollout(seed: int = 1, level: int = 1) -> dict:
    w = World(seed, level, privileged=True)
    steps = []

    def frame():
        cam = "station" if w.base_pose()[0] < -0.7 and abs(w.base_pose()[1] + 0.6) < 0.5 else "stage"
        return shot(w, cam, (800, 600), (640, 480)), jpg(w.camera("head", 320, 240, depth=False)["rgb"])

    f0 = frame()
    steps.append(dict(tool="reset", args=dict(seed=seed, level=level), t=0.0, result="world built; the robot stands at its start pose", frame=f0[0], head=f0[1]))
    for name in ("drive_to", "move_arm", "grasp", "release"):
        def wrap(name=name):
            f = getattr(w, name)

            def g(*a, **k):
                r = f(*a, **k)
                args = w.log[-1]["args"]
                keep = {k2: r[k2] for k2 in ("reached", "holding", "released", "error_m") if k2 in r}
                fr = frame()
                steps.append(dict(tool=name, args={k2: (round(float(v), 3) if not isinstance(v, str) else v) for k2, v in args.items()},
                                  t=round(w.robot_time, 1), result=keep, frame=fr[0], head=fr[1]))
                return r
            return g
        setattr(w, name, wrap())
    r = P.reference_privileged(w)
    fr = frame()
    steps.append(dict(tool="end", args={}, t=round(w.robot_time, 1), result=f"world left alone for {SETTLE:g} s, then scored", frame=fr[0], head=fr[1]))
    print(f"  rollout seed {seed} level {level}: score {r['score']} in {r['robot_time_s']} s of robot time, {len(steps)} steps")
    return dict(seed=seed, level=level, setting="privileged", steps=steps, score={k: r[k] for k in ("score", "progress", "care", "trash_in_bin", "trash_total", "mistakes", "fate", "milestones", "robot_time_s")},
                trash=[S.KINDS[it["kind"]]["label"] for it in w.items.values() if it["trash"]])


def baselines(seeds=range(1, 21), level: int = 1, names=("do_nothing", "stop_early", "reference_privileged", "reference")) -> dict:
    """Scores per room. `reference` works from the cameras (standard setting); `reference_privileged` is told positions."""
    out = {}
    for name in names:
        scores = []
        for seed in seeds:
            w = World(seed, level, privileged=name != "reference")
            try:
                scores.append(P.POLICIES[name](w)["score"])
            except Exception:
                scores.append(w.score()["score"])
        out[name] = scores
        print(f"  {name}: mean {sum(scores) / len(scores):.3f}")
    return dict(level=level, seeds=list(seeds), scores=out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", default="runs/sweep/dashboard.html")
    ap.add_argument("--standalone", action="store_true",
                    help="write a complete HTML document for the team board (visuals/sweep/index.html on main) instead of an artifact body")
    ap.add_argument("--thumb", help="also write a small picture of the room to this path")
    ap.add_argument("--add-reference", action="store_true",
                    help="with --data-from: also score the reference (standard setting) in the same rooms if the page lacks it")
    ap.add_argument("--data-from", metavar="PAGE",
                    help="reuse the pictures and numbers of a page this script wrote before instead of simulating again; "
                         "only the template and the task prompt (instruction.md) are read fresh")
    a = ap.parse_args()
    if a.data_from:
        m = re.search(r"const D = (\{.*?\});\n", Path(a.data_from).read_text(), re.S)
        data = json.loads(m.group(1))
        if a.add_reference and "reference" not in data["baselines"]["scores"]:
            if SIM_MISSING:
                sys.exit(f"--add-reference needs the simulator ({SIM_MISSING})")
            b = data["baselines"]
            b["scores"].update(baselines(b["seeds"], b["level"], names=("reference",))["scores"])
    else:
        if SIM_MISSING:
            sys.exit(f"the simulator is not importable ({SIM_MISSING}); run with MuJoCo installed, or pass --data-from")
        print("levels"); lv = levels()
        print("presets"); pr, items = presets()
        print("rollout"); ro = rollout()
        print("baselines"); bl = baselines()
        data = dict(levels=lv, presets=pr, items=items, rollout=ro, baselines=bl, time_limit=TIME_LIMIT, settle=SETTLE,
                    task=World(1, 3).get_task())
    data["instruction"] = (HERE.parent / "instruction.md").read_text()      # the task prompt, verbatim
    html = (HERE / "dashboard.template.html").read_text().replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    if a.standalone:
        banner = ('<div class="chips"><a class="chip" href="../../environment.html">&larr; Environment</a>'
                  '<span class="chip">For people. Agents: project state lives in coord/, not here.</span></div>')
        html = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                '<meta name="robots" content="noindex,nofollow">' + html.replace('<div class="page">', '<div class="page">' + banner, 1))
    if a.thumb and not SIM_MISSING:
        w = World(1, 3)
        Image.fromarray(w.camera("overview", 640, 480, depth=False, all_walls=False)["rgb"]).save(a.thumb, "JPEG", quality=78)
    out = Path(a.o)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print("wrote", out, round(out.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
