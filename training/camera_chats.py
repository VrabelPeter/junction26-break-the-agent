"""Camera-task episodes (camera_episodes.py) as the conversations OpenCode would have had, for fine-tuning.

    MUJOCO_GL=egl python training/camera_chats.py --episodes runs/training/camera/episodes_l1.jsonl \
        --request runs/training/capture/reqs/req-0006.json --out runs/training/camera/chats_l1 --model-name qwen3.5-9b-sweep \
        --provider modal-qwen35ft

The request file is one request OpenCode sent to a model endpoint during a Harbor run of this task (recorded by a
logging pass-through): its system prompt and its list of 24 tools are copied as they are, so the training text is
what the model meets in evaluation. Per episode the conversation is:

    system                  OpenCode's system prompt
    user                    the task's instruction.md, as OpenCode sends it
    assistant -> tool       robot_get_task, robot_drive_to x2, robot_look, robot_camera(head)   one call per turn
    user                    "Attached media from tool result:" + the colour picture + the grey depth picture
    assistant -> tool       bash: the script of locate_plan.py: find what stands on the table near pixel (u, v), print the steps
    assistant -> tool       ... the printed steps, one call per turn ("Step n."), with the server's replies ...
    assistant               a closing sentence, no call (this ends an OpenCode run)

The pictures are rendered again here exactly as the server does (JPEG, quality 88 and 85) and written next to the
chats. Replies are trimmed the way server.py trims them (no joint angles outside observe). Episodes with a move
that did not arrive are left out: the server adds an explanation to those replies that is not reproduced here.
"""
from __future__ import annotations

import argparse
import io
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import textenv as T          # noqa: E402
import camera_episodes as E  # noqa: E402
import locate_plan as L      # noqa: E402

DEPTH_URL = "http://env-server:8000/camera/head/depth.npy"
DONE = "The trash is in the bin."


def dumps(x) -> str:
    return json.dumps(x, separators=(",", ":"))


def pictures(job):
    """The two pictures the camera tool returns at the viewpoint, and its JSON reply, as the server builds them."""
    seed, level, out_dir, cal_expected = job
    T.import_sweep()
    import numpy as np
    from PIL import Image
    from sweep.sim import World
    w = World(seed, level)
    w.call("get_task")
    for v in E.VIEW:
        w.call("drive_to", **v)
    w.call("look", **E.LOOK)
    c = w.camera("head", 640, 480, depth=True, all_walls=True)
    if c["calibration"] != cal_expected:
        return seed, None
    near, far = 0.3, 5.0
    grey = (255 * (1.0 - np.clip((c["depth"] - near) / (far - near), 0.0, 1.0))).astype(np.uint8)
    rgb_path, grey_path = f"{out_dir}/l{level}-s{seed}-rgb.jpg", f"{out_dir}/l{level}-s{seed}-depth.jpg"
    Image.fromarray(c["rgb"]).save(rgb_path, "JPEG", quality=88)
    Image.fromarray(grey).save(grey_path, "JPEG", quality=85)
    return seed, [Path(rgb_path).name, Path(grey_path).name]


def chat(ep: dict, system: str, user: str, pics: list[str], rng: random.Random) -> list[dict] | None:
    msgs = [dict(role="system", content=system), dict(role="user", content=user)]
    left, plan, step = 900.0, None, 0

    def turn(name: str, args: dict, reply: str, say: str = ""):
        cid = "chatcmpl-tool-" + "".join(rng.choice("0123456789abcdef") for _ in range(16))
        msgs.append(dict(role="assistant", content=say,
                         tool_calls=[dict(id=cid, type="function", function=dict(name=name, arguments=dumps(args)))]))
        msgs.append(dict(role="tool", tool_call_id=cid, content=reply))

    for c in ep["calls"]:
        tool, args, r = c["tool"], c["args"], json.loads(json.dumps(c["result"]))
        if not r.get("ok") or r.get("reached") is False:
            return None
        if tool == "camera":
            meta = dict(ok=True, camera="head", width=640, height=480, calibration=r["calibration"], time_left_s=left,
                        depth=dict(picture="second image: grey, near is bright", near_m=0.3, far_m=5.0, values=DEPTH_URL))
            turn("robot_camera", args, dumps(meta))
            msgs.append(dict(role="user", content=[dict(type="text", text="Attached media from tool result:"),
                                                   dict(type="image", path=pics[0]), dict(type="image", path=pics[1])]))
            continue
        if tool == "point":
            u, v = args["u"], args["v"]
            turn("bash", dict(command=L.command(u, v)), r["text"],
                 say=f"The trash on the table is at pixel ({u}, {v}) of the colour picture.")
            step, plan = 0, r
            continue
        say = ""
        if plan is not None:                      # after the script: say which printed step this call is
            step += 1
            say = f"Step {step}."
            if step == 1:
                say = (f"The trash is at x={plan['x']}, y={plan['y']}. I sweep it over the {plan['edge']} edge of the table"
                       f"{' after pulling it closer' if plan['gather'] else ''}, following the {plan['steps']} printed steps. Step 1.")
        if tool not in ("observe", "get_task"):
            for hand in ("left_hand", "right_hand"):
                if isinstance(r.get(hand), dict):
                    r[hand].pop("joints", None)
        left = r.get("time_left_s", left)
        turn("robot_" + tool, args, dumps(r), say=say)
    msgs.append(dict(role="assistant", content=DONE))
    return msgs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", default="runs/training/camera/episodes_l1.jsonl")
    ap.add_argument("--request", default="runs/training/capture/reqs/req-0006.json")
    ap.add_argument("--instruction", default=str(HERE.parent / "probes/sweep/instruction.md"))
    ap.add_argument("--out", default="runs/training/camera/chats_l1")
    ap.add_argument("--model-name", default="qwen3.5-9b-sweep")
    ap.add_argument("--provider", default="modal-qwen35ft")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    req = json.loads(Path(a.request).read_text())
    system = req["messages"][0]["content"]
    old = [ln for ln in system.split("\n") if ln.startswith("You are powered by the model named")]
    assert len(old) == 1, "the system prompt has no model line"
    system = system.replace(old[0], f"You are powered by the model named {a.model_name}. The exact model ID is {a.provider}/{a.model_name}")
    user = '"' + Path(a.instruction).read_text() + '"'        # OpenCode puts the text it is started with between quotes
    out = Path(a.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "tools.json").write_text(json.dumps(req["tools"]))
    eps = [e for e in map(json.loads, open(a.episodes)) if e["score"] >= 0.99]
    if a.limit:
        eps = eps[:a.limit]
    cal = {e["seed"]: next(c["result"]["calibration"] for c in e["calls"] if c["tool"] == "camera") for e in eps}
    import multiprocessing as mp
    with mp.get_context("spawn").Pool(a.workers) as pool:
        pics = dict(pool.imap_unordered(pictures, [(e["seed"], e["level"], str(out / "images"), cal[e["seed"]]) for e in eps], chunksize=4))
    rng, n, dropped = random.Random(0), 0, 0
    with (out / "chats.jsonl").open("w") as f:
        for e in eps:
            m = chat(e, system, user, pics[e["seed"]], rng) if pics.get(e["seed"]) else None
            if m is None:
                dropped += 1
                continue
            f.write(json.dumps(dict(seed=e["seed"], level=e["level"], score=e["score"], pixel=e["pixel"], kind=e["kind"],
                                    n_calls=len(e["calls"]), messages=m)) + "\n")
            n += 1
    chars = len(system) + len(user) + len(json.dumps(req["tools"]))
    print(f"{n} chats written to {out}/chats.jsonl, {dropped} left out; fixed part (system, instruction, tools): {chars} characters")


if __name__ == "__main__":
    main()
