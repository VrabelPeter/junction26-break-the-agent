"""Build and test the camera pipeline (perception.py) against ground truth.

Ground truth (object positions and kinds, read from the simulator) is used ONLY in this file:
  --train   build perception_model.json, the table of examples of what each kind of thing looks like,
            from surveys of rooms with seeds 1000 and up (never the rooms it is tested on)
  --eval    survey rooms with seeds 1 to 40 at levels 1, 2 and 3 and compare with the truth
  --tools   find the brush and the bin at the tool station, also when they stand a little differently
  --checks  the awkward cases: robot's own arms, tools on or near a surface, tools in the hands

    cd probes/sweep/environment/env-server
    MUJOCO_GL=egl python -m sweep.perception_eval --train && MUJOCO_GL=egl python -m sweep.perception_eval --eval
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import random
import time
from collections import Counter, defaultdict

import numpy as np

from . import perception as PC
from . import scene as S
from .sim import World

BRUSH_TOLERANCE = 0.05      # the brush stroke tolerates about this much sideways error


def no_depth(w: World) -> World:
    """Make sure the pipeline only ever asks for colour pictures."""
    real = w.camera

    def camera(name="head", *a, **k):
        assert k.get("depth") is False, "perception.py asked the camera for depth"
        return real(name, *a, **k)
    w.camera = camera
    return w


# ---- ground truth (this file only) ---------------------------------------------------------------
def body_footprint(w: World, body: str) -> dict:
    """Middle and size of a body's outline on the floor, from the simulator's geometry."""
    m, d = w.m, w.d
    b = m.body(body).id
    Rb, pb = d.xmat[b].reshape(3, 3), d.xpos[b]
    pts = []
    for g in range(m.ngeom):
        if m.geom_bodyid[g] != b:
            continue
        c, h = m.geom_aabb[g, :3], m.geom_aabb[g, 3:]
        Rg, pg = d.geom_xmat[g].reshape(3, 3), d.geom_xpos[g]
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    pts.append(pg + Rg @ (c + h * np.array([sx, sy, sz])))
    local = (np.array(pts) - pb) @ Rb                       # in the body's own frame, where its outline is a rectangle
    lo, hi = local.min(0), local.max(0)
    mid = pb + Rb @ ((lo + hi) / 2)
    size = sorted((hi - lo)[:2], reverse=True)
    return dict(x=float(mid[0]), y=float(mid[1]), length=float(size[0]), width=float(size[1]), top=float(np.array(pts)[:, 2].max()))


def truth(w: World) -> list[dict]:
    out = []
    for n, it in w.items.items():
        where = w.where(n)
        if where not in ("on_table", "on_sofa"):          # rolled off: not the survey's business
            continue
        f = body_footprint(w, n)
        out.append(dict(name=n, kind=it["kind"], group="trash" if it["trash"] else "personal", surface=where[3:], origin=[float(v) for v in w._pos(n)[:2]], **f))
    return out


def match(dets: list[dict], gt: list[dict]):
    """Pair detections with true things. Returns (pairs, missed things, unpaired detections)."""
    pairs, used = [], set()
    cands = sorted(((math.hypot(d["x"] - g["x"], d["y"] - g["y"]), i, j) for i, d in enumerate(dets) for j, g in enumerate(gt)
                    if d["surface"] == g["surface"]), key=lambda t: t[0])
    taken = set()
    for dist, i, j in cands:
        if i in used or j in taken or dist > max(0.07, 0.6 * gt[j]["length"]):
            continue
        used.add(i)
        taken.add(j)
        pairs.append((dets[i], gt[j], dist))
    missed = [g for j, g in enumerate(gt) if j not in taken]
    extra = []
    for i, d in enumerate(dets):
        if i in used:
            continue
        near = min(gt, key=lambda g: math.hypot(d["x"] - g["x"], d["y"] - g["y"]) if g["surface"] == d["surface"] else 9, default=None)
        dist = math.hypot(d["x"] - near["x"], d["y"] - near["y"]) if near and near["surface"] == d["surface"] else 9
        extra.append(dict(det=d, kind="piece of " + near["kind"] if dist < 0.6 * near["length"] + 0.05 else "nothing there"))
    return pairs, missed, extra


# ---- one room ------------------------------------------------------------------------------------
def survey_room(job):
    seed, level, extra, depth = job
    try:
        w = World(seed, level) if depth else no_depth(World(seed, level))
    except RuntimeError as e:                               # the room generator could not place everything: not a perception matter
        return dict(seed=seed, level=level, skipped=str(e))
    rng = random.Random(seed)
    gt_extra = []
    if extra == "brush_on_table" or extra == "brush_on_sofa":      # a tool lying where things lie (teleported: this file only)
        surf = S.SURFACES["table" if extra == "brush_on_table" else "sofa"]
        for _ in range(200):
            x, y = rng.uniform(surf["x"][0] + 0.25, surf["x"][1] - 0.25), rng.uniform(surf["y"][0] + 0.14, surf["y"][1] - 0.14)
            if all(math.hypot(x - w._pos(n)[0], y - w._pos(n)[1]) > 0.33 for n in w.items):
                break
        w.place_tool("brush", x, y, surf["top"] + 0.01, rng.uniform(-math.pi, math.pi))
        w.rest(1.0)
    t = time.time()
    res = PC.survey(w, depth=depth)
    gt = truth(w)
    if extra:
        f = body_footprint(w, "brush")
        gt.append(dict(name="brush", kind="brush", group="tool", surface="table" if extra == "brush_on_table" else "sofa",
                       origin=[f["x"], f["y"]], **f))
    dets = res["detections"]
    pairs, missed, extras = match(dets, gt)
    return dict(seed=seed, level=level, extra=extra, views=res["views"], robot_time=res["robot_time_s"], unseen=res["unseen"], wall=round(time.time() - t, 1),
                pairs=[dict(det=d, gt=g, err=e, err_origin=math.hypot(d["x"] - g["origin"][0], d["y"] - g["origin"][1])) for d, g, e in pairs],
                missed=missed, extras=extras, n_items=len(gt))


def run(jobs, workers: int):
    if workers <= 1:
        rooms = [survey_room(j) for j in jobs]
    else:
        with mp.get_context("spawn").Pool(workers) as pool:
            rooms = pool.map(survey_room, jobs, chunksize=1)
    skipped = [(r["seed"], r["level"], r["skipped"]) for r in rooms if "skipped" in r]
    if skipped:
        print("rooms that could not be generated (skipped):", skipped)
    return [r for r in rooms if "skipped" not in r]


# ---- train ---------------------------------------------------------------------------------------
def train(a):
    depth = not a.colour_only
    jobs = [(s, 3, None, depth) for s in range(1000, 1000 + a.rooms)] + [(s, 2, None, depth) for s in range(1200, 1200 + a.rooms // 3)]
    if a.with_brush:                                        # off by default: the robot knows where it put its own tools (survey's `ignore`)
        jobs += [(s, 1, "brush_on_table", depth) for s in range(1100, 1108)] + [(s, 1, "brush_on_sofa", depth) for s in range(1110, 1118)]
    rooms = run(jobs, a.workers)
    examples, heights = [], defaultdict(list)
    for r in rooms:
        for p in r["pairs"]:
            d, g = p["det"], p["gt"]
            if p["err"] > 0.05 and g["kind"] not in ("jacket", "brush"):
                continue                                     # a doubtful pairing teaches nothing
            examples.append(dict(kind=g["kind"], group=g["group"], surface=g["surface"], features=[round(float(v), 3) for v in PC.features(d)]))
            if d["view_spread"] > 2.0 and d["clean_views"] >= 3:   # seen from opposite sides: the tail gives the height
                heights[g["kind"]].append(d["height"])
    per_kind = defaultdict(list)
    for e in examples:
        per_kind[e["kind"]].append(e)
    rng = random.Random(0)
    kept = []
    for k, ex in per_kind.items():
        rng.shuffle(ex)
        kept += ex[:a.per_kind]
    model = json.loads(PC.MODEL_FILE.read_text()) if PC.MODEL_FILE.exists() else {}
    model["note"] = "examples of what each kind of thing looks like, one table per mode, from surveys of rooms with seeds 1000 and up; built by perception_eval.py --train"
    model["depth" if depth else "colour"] = dict(kind_height={k: round(float(np.median(v)), 4) for k, v in heights.items() if len(v) >= 3},
                                                 examples=[dict(kind=e["kind"], group=e["group"], features=e["features"]) for e in kept])
    PC.MODEL_FILE.write_text(json.dumps(model, separators=(",", ":")))
    print("examples per kind:", dict(Counter(e["kind"] for e in kept)))
    print("mode:", "colour and depth" if depth else "colour only", "; heights per kind:", model["depth" if depth else "colour"]["kind_height"])
    print("wrote", PC.MODEL_FILE, round(PC.MODEL_FILE.stat().st_size / 1e3), "kB")


# ---- eval ----------------------------------------------------------------------------------------
def summarise(rooms, title):
    items = sum(r["n_items"] for r in rooms)
    pairs = [p for r in rooms for p in r["pairs"]]
    missed = [m for r in rooms for m in r["missed"]]
    extras = [e for r in rooms for e in r["extras"]]
    err = np.array([p["err"] for p in pairs]) if pairs else np.zeros(1)
    right = [p["det"]["group"] == p["gt"]["group"] for p in pairs]
    out = dict(title=title, rooms=len(rooms), things=items, found=len(pairs), found_share=round(len(pairs) / max(items, 1), 4),
               rooms_all_found=round(float(np.mean([not r["missed"] for r in rooms])), 3),
               false_per_room=round(len(extras) / len(rooms), 3), false_kinds=dict(Counter(e["kind"] for e in extras)),
               err_mean_mm=round(float(err.mean() * 1000), 1), err_median_mm=round(float(np.median(err) * 1000), 1), err_p95_mm=round(float(np.percentile(err, 95) * 1000), 1),
               within_brush_tolerance=round(float((err < BRUSH_TOLERANCE).mean()), 4),
               group_right=round(float(np.mean(right)), 4) if right else None,
               kind_right=round(float(np.mean([p["det"]["kind"] == p["gt"]["kind"] for p in pairs])), 4) if pairs else None,
               missed_kinds=dict(Counter(m["kind"] for m in missed)),
               robot_time_s=round(float(np.mean([r["robot_time"] for r in rooms])), 1), views=round(float(np.mean([r["views"] for r in rooms])), 1))
    return out


def per_kind(rooms):
    rows = {}
    kinds = sorted({p["gt"]["kind"] for r in rooms for p in r["pairs"]} | {m["kind"] for r in rooms for m in r["missed"]})
    for k in kinds:
        for surf in ("table", "sofa"):
            ps = [p for r in rooms for p in r["pairs"] if p["gt"]["kind"] == k and p["gt"]["surface"] == surf]
            ms = [m for r in rooms for m in r["missed"] if m["kind"] == k and m["surface"] == surf]
            if not ps and not ms:
                continue
            e = np.array([p["err"] for p in ps]) if ps else np.zeros(1)
            rows[f"{k} on {surf}"] = dict(n=len(ps) + len(ms), found=len(ps), err_mean_mm=round(float(e.mean() * 1000), 1), err_p95_mm=round(float(np.percentile(e, 95) * 1000), 1),
                                         err_max_mm=round(float(e.max() * 1000), 1), within_5cm=round(float((e < BRUSH_TOLERANCE).mean()), 3),
                                         group_right=round(float(np.mean([p["det"]["group"] == p["gt"]["group"] for p in ps])), 3) if ps else None,
                                         called=dict(Counter(p["det"]["kind"] for p in ps)))
    return rows


def evaluate(a):
    report = dict(mode="colour only" if a.colour_only else "colour and depth", levels={}, by_kind=None)
    print("mode:", report["mode"])
    all_rooms = []
    for level in a.levels:
        rooms = run([(s, level, None, not a.colour_only) for s in a.seeds], a.workers)
        all_rooms += rooms
        report["levels"][level] = summarise(rooms, f"level {level}")
        print(json.dumps(report["levels"][level]))
    report["all"] = summarise(all_rooms, "all levels")
    report["by_kind"] = per_kind(all_rooms)
    print(json.dumps(report["all"]))
    print(f"{'kind and surface':22s} {'n':>4s} {'found':>5s} {'mean':>6s} {'p95':>6s} {'max':>6s} {'<5cm':>6s} {'group':>6s}  called")
    for k, r in report["by_kind"].items():
        print(f"{k:22s} {r['n']:4d} {r['found']:5d} {r['err_mean_mm']:6.1f} {r['err_p95_mm']:6.1f} {r['err_max_mm']:6.1f} {r['within_5cm']:6.3f} {str(r['group_right']):>6s}  {r['called']}")
    worst = sorted(((p["err"], r["seed"], r["level"], p["gt"]["name"], p["gt"]["surface"]) for r in all_rooms for p in r["pairs"]), reverse=True)[:8]
    print("largest position errors (m, seed, level, thing, surface):", [(round(e, 3), s, l, n, sf) for e, s, l, n, sf in worst])
    print("missed:", [(r["seed"], r["level"], m["name"], m["surface"]) for r in all_rooms for m in r["missed"]][:30])
    print("false detections:", [(r["seed"], r["level"], e["kind"], e["det"]["surface"], e["det"]["kind"], round(e["det"]["area"] * 1e4, 1)) for r in all_rooms for e in r["extras"]][:30])
    wrong = [(r["seed"], r["level"], p["gt"]["name"], p["gt"]["surface"], p["det"]["kind"], p["det"]["confidence"]) for r in all_rooms for p in r["pairs"] if p["det"]["group"] != p["gt"]["group"]]
    print("trash/personal mistakes:", wrong[:30])
    if a.out:
        json.dump(report, open(a.out, "w"), indent=1)
        print("wrote", a.out)


# ---- tools ---------------------------------------------------------------------------------------
def tools_case(job):
    seed, jitter, depth = job
    w = World(seed, 1) if depth else no_depth(World(seed, 1))
    rng = random.Random(seed)
    if jitter:                                              # put the tools down a little differently (teleported: this file only)
        sh = S.STATION["shelf"]
        w.place_tool("brush", S.STATION["brush_grip"][0] + S.BRUSH["grip_x"] + rng.uniform(-0.03, 0.03), sh["cy"] + rng.uniform(-0.02, 0.02),
                     sh["top"] + 0.005, math.pi + rng.uniform(-0.35, 0.35))
        side = rng.choice((1, 1, -1))
        w.place_tool("bin", -1.62 + rng.uniform(-0.08, 0.10), sh["cy"] + side * (0.33 + rng.uniform(0, 0.15)), 0.003, math.pi / 2 + rng.uniform(-0.5, 0.5) + rng.choice((0, 0, math.pi)))
        w.rest(1.0)
    t = PC.locate_tools(w, depth=depth)
    out = dict(seed=seed, jitter=jitter, views=t["views"], robot_time=round(w.robot_time, 1))
    for tool in ("brush", "bin"):
        true = w.d.site_xpos[w.grip[tool]]
        axis = w.d.site_xmat[w.grip[tool]].reshape(3, 3)[:, 0]
        got = t[tool]
        if got is None:
            out[tool] = None
            continue
        closing = np.array([math.cos(got["closing_yaw"]), math.sin(got["closing_yaw"]), 0.0])
        out[tool] = dict(err_xy=float(np.hypot(got["x"] - true[0], got["y"] - true[1])), err_z=float(abs(got["z"] - true[2])),
                         across=float(abs(closing @ axis)),      # the grasp needs this below 0.5: fingers closing across the handle
                         would_grasp=bool(np.linalg.norm([got["x"] - true[0], got["y"] - true[1], got["z"] - true[2]]) < 0.035 and abs(closing @ axis) < 0.5))
    return out


def tools(a):
    depth = not a.colour_only
    print("mode:", "colour and depth" if depth else "colour only")
    jobs = [(s, False, depth) for s in (1, 2, 3)] + [(s, True, depth) for s in range(1, 1 + a.cases)]
    with mp.get_context("spawn").Pool(a.workers) as pool:
        res = pool.map(tools_case, jobs, chunksize=1)
    for name, sel in (("as the room starts", [r for r in res if not r["jitter"]]), ("put down differently", [r for r in res if r["jitter"]])):
        for tool in ("brush", "bin"):
            ok = [r[tool] for r in sel if r[tool]]
            e = np.array([o["err_xy"] for o in ok]) if ok else np.zeros(1)
            print(f"{name:22s} {tool:5s}: found {len(ok)}/{len(sel)}  position error mean {e.mean() * 1000:.1f} mm, max {e.max() * 1000:.1f} mm; "
                  f"within the grasp's reach and direction {sum(o['would_grasp'] for o in ok)}/{len(sel)}; views {np.mean([r['views'] for r in sel]):.1f}; robot time {np.mean([r['robot_time'] for r in sel]):.1f} s")
    bad = [(r["seed"], tool, r[tool]) for r in res for tool in ("brush", "bin") if not r[tool] or not r[tool]["would_grasp"]]
    print("not good enough to grasp:", bad[:12])


# ---- the awkward cases -----------------------------------------------------------------------------
def check_case(job):
    what, seed, depth = job
    import mujoco
    rng = random.Random(seed * 7 + 1)
    try:
        World(seed, 3)
    except RuntimeError as e:                               # the room generator could not place everything
        return dict(what=what, seed=seed, skipped=str(e))
    if what == "tools in the hands":
        # privileged only so that the scripted pick-up in policies.py can run; the survey itself reads nothing from it
        from . import policies as P
        w = World(seed, 3, privileged=True)
        w = w if depth else no_depth(w)
        P.fetch_tools(w)
        if w.holding["left"] != "brush" or w.holding["right"] != "bin":
            return dict(what=what, seed=seed, skipped="the scripted pick-up failed")
    else:
        w = World(seed, 3) if depth else no_depth(World(seed, 3))
    if what == "bin beside the table":                      # the bin standing against an edge, as while sweeping (teleported)
        t = S.SURFACES["table"]
        w.place_tool("bin", rng.uniform(t["x"][0] + 0.2, t["x"][1] - 0.2), t["y"][0] - 0.11 if rng.random() < 0.5 else t["y"][1] + 0.11, 0.003, 0.0)
        w.rest(1.0)
    seg = []
    if what == "the robot's own arms":                      # which pixels really show the robot, from the renderer (truth, this file only)
        m = w.m
        base = m.body("base_link").id
        robot = set()
        for b in range(m.nbody):
            r = b
            while r not in (0, base):
                r = m.body_parentid[r]
            if r == base:
                robot.add(b)
        ren = mujoco.Renderer(m, 480, 640)
        real = w.camera

        def camera(name="head", *a, **k):
            out = real(name, *a, **k)
            ren.enable_segmentation_rendering()
            ren.update_scene(w.d, camera=name)
            s = ren.render().copy()
            ren.disable_segmentation_rendering()
            ok = (s[..., 1] == int(mujoco.mjtObj.mjOBJ_GEOM)) & (s[..., 0] >= 0)
            is_robot = np.zeros(ok.shape, bool)
            is_robot[ok] = np.isin(m.geom_bodyid[s[..., 0][ok]], list(robot))
            seg.append(is_robot)
            return out
        w.camera = camera
    res = PC.survey(w, depth=depth)
    gt = truth(w)
    pairs, missed, extras = match(res["detections"], gt)
    out = dict(what=what, seed=seed, views=res["views"], robot_time=res["robot_time_s"], n_items=len(gt), found=len(pairs), missed=[m["name"] for m in missed],
               extras=[(e["kind"], e["det"]["surface"], e["det"]["kind"]) for e in extras], err=[p[2] for p in pairs],
               group_right=[p[0]["group"] == p[1]["group"] for p in pairs])
    if seg:
        views = [v for m in res["maps"].values() for v in m.views]
        leak, total = 0, 0
        for v, is_robot in zip(views, seg):
            total += int(is_robot.sum())
            leak += int((is_robot & ~v.robot).sum())
        out.update(robot_pixels=total, robot_pixels_not_masked=leak)
    return out


def checks(a):
    depth = not a.colour_only
    print("mode:", "colour and depth" if depth else "colour only")
    jobs = [(what, s, depth) for what in ("the robot's own arms", "tools in the hands", "bin beside the table") for s in range(1, 1 + a.cases // 2)]
    with mp.get_context("spawn").Pool(a.workers) as pool:
        res = pool.map(check_case, jobs, chunksize=1)
    for what in ("the robot's own arms", "tools in the hands", "bin beside the table"):
        rs = [r for r in res if r["what"] == what and "skipped" not in r]
        sk = [r for r in res if r["what"] == what and "skipped" in r]
        if not rs:
            print(f"{what}: nothing ran ({len(sk)} skipped: {sk[:2]})")
            continue
        err = np.array([e for r in rs for e in r["err"]] or [0.0])
        line = (f"{what}: {len(rs)} rooms, found {sum(r['found'] for r in rs)}/{sum(r['n_items'] for r in rs)}, false detections {sum(len(r['extras']) for r in rs)} "
                f"{dict(Counter(e[0] for r in rs for e in r['extras']))}, position error mean {err.mean() * 1000:.1f} mm p95 {np.percentile(err, 95) * 1000:.1f} mm, "
                f"trash/personal right {np.mean([g for r in rs for g in r['group_right']]):.3f}, views {np.mean([r['views'] for r in rs]):.1f}, robot time {np.mean([r['robot_time'] for r in rs]):.1f} s")
        if "robot_pixels" in rs[0]:
            line += f"; robot pixels outside the mask {sum(r['robot_pixels_not_masked'] for r in rs)} of {sum(r['robot_pixels'] for r in rs)}"
        print(line + (f"; skipped {len(sk)}" if sk else ""))
        print("   missed:", [(r["seed"], r["missed"]) for r in rs if r["missed"]][:10])
    brush = run([(s, 1, "brush_on_table", depth) for s in range(1, 9)] + [(s, 1, "brush_on_sofa", depth) for s in range(11, 19)], a.workers)
    got = [p for r in brush for p in r["pairs"] if p["gt"]["kind"] == "brush"]
    conf = [p["det"]["confidence"] for p in got]
    print(f"brush lying on a surface, not announced to the survey: seen {len(got)}/{len(brush)}, taken for {dict(Counter(p['det']['kind'] for p in got))}, "
          f"confidence median {np.median(conf) if conf else 0:.2f}; other things in those rooms still judged right: "
          f"{np.mean([p['det']['group'] == p['gt']['group'] for r in brush for p in r['pairs'] if p['gt']['kind'] != 'brush']):.3f}; "
          f"extra detections {sum(len(r['extras']) for r in brush)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--tools", action="store_true")
    ap.add_argument("--checks", action="store_true")
    ap.add_argument("--colour-only", action="store_true", help="the mode without depth (survey(world, depth=False)); default is colour and depth")
    ap.add_argument("--with-brush", action="store_true", help="train: also learn what the brush looks like lying on a surface")
    ap.add_argument("--rooms", type=int, default=48, help="training rooms at level 3")
    ap.add_argument("--per-kind", type=int, default=45, help="examples kept per kind")
    ap.add_argument("--seeds", nargs="+", type=int, default=list(range(1, 41)))
    ap.add_argument("--levels", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--cases", type=int, default=24)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.train:
        train(a)
    if a.eval:
        evaluate(a)
    if a.tools:
        tools(a)
    if a.checks:
        checks(a)


if __name__ == "__main__":
    main()
