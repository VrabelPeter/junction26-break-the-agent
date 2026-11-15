"""Experience for the camera task (standard setting, level 1): what a vision model would see and do.

    MUJOCO_GL=egl python training/camera_episodes.py --seeds 1000-1999 --out runs/training/camera/episodes.jsonl

One episode = the calls an agent could make itself in the standard setting, with nothing it is not given:

    get_task, two drives to the table viewpoint, look, camera(head)      -> the colour picture (saved as PNG)
    point(u, v)                                                         -> the room point seen at that pixel
    ... the scripted reference's moves (sweep/policies.py: sweep_all), planned from that one point ...

`point` stands for what the agent does in its shell: download /camera/head/depth.npy and calibration.json
(logged by the server as `camera_file`) and apply the formula of instruction.md to one pixel. The pixel is the
only thing taken from the simulator's ground truth (the trash's centre projected into the picture): it is the
label a model has to learn to give from the picture. Everything after it is computed from the returned point,
so a model that points well and repeats the arithmetic reproduces the episode. The tools stand at the same
place in every level-1 room; the controller is given the handle positions the reference finds with the camera.

Each episode carries the environment's own score; training keeps the episodes that scored 1.0.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import textenv as T          # noqa: E402  (puts the simulator on the path)
import collect as C          # noqa: E402
import locate_plan as L    # noqa: E402

VIEW = [dict(x=-0.442, y=-1.715, heading=2.542), dict(x=0.3, y=-1.835, heading=1.571)]   # the reference's way to its table viewpoint
LOOK = dict(pan=0.0, tilt=-0.668)


def project(cal: dict, p) -> tuple[float, float]:
    import numpy as np
    c = np.array(cal["cam_rot"]).T @ (np.array(p, dtype=float) - np.array(cal["cam_pos"]))
    return cal["cx"] + cal["f"] * c[0] / -c[2], cal["cy"] - cal["f"] * c[1] / -c[2]


def episode(job) -> dict:
    seed, level, img_dir = job
    T.import_sweep()
    from sweep.sim import World
    from sweep import policies as P, scene as S
    told = World(seed, level, privileged=True).observe()          # ground truth, used for the pixel label and the tool handles only
    trash = [o for o in told["objects"] if o["trash"]]
    out = dict(seed=seed, level=level, setting="standard", score=None, skip=None)
    if len(trash) != 1:
        return dict(out, skip="not exactly one piece of trash")
    o = trash[0]
    w = World(seed, level)
    rec = C.Recorder(w)
    rec.calls.append(dict(tool="get_task", args={}, t=0.0, result=w.call("get_task")))
    for v in VIEW:
        rec.drive_to(**v)
    rec.look(**LOOK)
    cam = w.camera("head")
    cal = cam["calibration"]
    u, v = project(cal, (o["x"], o["y"], o["z"]))
    u, v = int(round(u)), int(round(v))
    if not (4 <= u <= 635 and 4 <= v <= 475):
        return dict(out, skip="trash outside the picture", kind=o["kind"])
    pt = w.pixel_point("head", u, v)
    top = S.SURFACES["table"]["top"]
    if pt["z"] < top + 0.004:
        return dict(out, skip="the pixel shows the table, not the trash", kind=o["kind"])
    img = None
    if img_dir:
        from PIL import Image
        img = f"{img_dir}/l{level}-s{seed}.png"
        Image.fromarray(cam["rgb"]).save(img)
    rec.calls.append(dict(tool="camera", args=dict(name="head"), t=round(w.robot_time, 2), result=dict(ok=True, calibration=cal, image=img)))
    text = L.run(cam["depth"], cal, u, v)                          # the agent's shell script, run on this room's depth image
    head, steps = L.parse(text)
    if head is None:
        return dict(out, skip="the script found nothing on the table at the pixel", kind=o["kind"])
    rec.calls.append(dict(tool="point", args=dict(u=u, v=v), t=round(w.robot_time, 2), result=dict(ok=True, text=text, **head)))
    pt = head
    try:
        L.execute(rec, steps)                                      # the printed steps, nothing else
    except RuntimeError as e:
        out["stopped"] = repr(e)[:200]
    s = w.score()
    return dict(out, kind=o["kind"], truth=dict(x=o["x"], y=o["y"], z=o["z"]), pixel=[u, v], point=pt, calls=rec.calls,
                score=s["score"], robot_time_s=s["robot_time_s"], mistakes=s["mistakes"], milestones=s.get("milestones"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="1000-1019")
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument("--out", default="runs/training/camera/episodes.jsonl")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 4))
    a = ap.parse_args()
    seeds = T.parse_seeds(a.seeds)
    out = Path(a.out)
    img_dir = out.parent / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    import multiprocessing as mp
    t0, n, ok, skips = time.time(), 0, 0, {}
    with mp.get_context("spawn").Pool(a.workers) as pool, out.open("w") as f:
        for ep in pool.imap_unordered(episode, [(s, a.level, str(img_dir)) for s in seeds]):
            n += 1
            if ep["skip"]:
                skips[ep["skip"]] = skips.get(ep["skip"], 0) + 1
            else:
                ok += ep["score"] >= 0.99
                f.write(json.dumps(ep) + "\n")
            if n % 20 == 0 or n == len(seeds):
                print(f"{n}/{len(seeds)} rooms, {ok} scored 1.0, skipped {skips}, {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
