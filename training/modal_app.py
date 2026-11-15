"""Post-training experiment on Modal: does the environment's reward help a smaller model learn?

Three arms, all scored by the environment itself on held-out seeds (privileged text setting):
    A  the base model, untrained
    B  LoRA fine-tuned on episodes selected by the reward (score >= 0.99)
    C  LoRA fine-tuned on the same number of episodes drawn without looking at the reward

    modal run training/modal_app.py --smoke          # a few minutes, well under a dollar: checks the whole path
    modal run training/modal_app.py                  # the experiment; writes results/training/<run>.json

Run from the repository root, after collect.py and dataset.py (see training/README.md).
Every GPU function asks for exactly one GPU of the type in GPU and has a timeout; nothing here starts a cluster.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
ENV_SERVER = REPO / "probes" / "sweep" / "environment" / "env-server"

MODEL_ID = "Qwen/Qwen3-4B-Instruct-2507"
MODEL_REVISIONS = {"Qwen/Qwen3-4B-Instruct-2507": "cdbee75f17c01a7cc42f958dc650907174af0554"}   # pinned; other models: latest
GPU = os.environ.get("SWEEP_TRAIN_GPU", "L40S")      # one GPU of this type per function; override to try another type
EVAL_SEEDS = "1-30"               # held out: collection uses seeds 1000 and up

app = modal.App("sweep-training")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libosmesa6", "libgl1", "libglx-mesa0")
    .pip_install("torch==2.8.0", "transformers==4.57.1", "peft==0.17.1", "accelerate==1.10.1", "tokenizers==0.22.1",
                 "huggingface_hub==0.36.0", "safetensors==0.6.2", "mujoco==4.0.1", "numpy==2.5.4", "pillow==13.0.0")
    .env({"HF_HOME": "/cache/hf", "SWEEP_ENV_SERVER": "/root/env-server", "MUJOCO_GL": "osmesa", "PYOPENGL_PLATFORM": "osmesa",
          "TOKENIZERS_PARALLELISM": "false", "PYTHONUNBUFFERED": "1"})
)
if modal.is_local():              # the simulator and this directory's modules, as they are in this checkout
    not_code = lambda p: "__pycache__" in p.parts or p.suffix in (".pyc", ".md")
    image = (image
             .add_local_dir(ENV_SERVER / "sweep", "/root/env-server/sweep", ignore=not_code)
             .add_local_dir(ENV_SERVER / "assets", "/root/env-server/assets")
             .add_local_dir(HERE, "/root/training", ignore=lambda p: p.suffix != ".py"))
adapters = modal.Volume.from_name("sweep-training-adapters", create_if_missing=True)
hf_cache = modal.Volume.from_name("sweep-training-hf-cache", create_if_missing=True)
VOLUMES = {"/vol": adapters, "/cache": hf_cache}


def _modules():
    for p in ("/root/training", str(HERE)):
        if p not in sys.path:
            sys.path.insert(0, p)
    import lm, policy_loop, textenv      # noqa: E401, PLC0415
    return lm, policy_loop, textenv


def _log(msg: str):
    print(msg, flush=True)


@app.function(image=image, volumes=VOLUMES, timeout=1800)
def prefetch(model_id: str, revision: str | None) -> str:
    """Download the model once into the cache volume, so the GPU containers do not each fetch it."""
    from huggingface_hub import snapshot_download
    path = snapshot_download(model_id, revision=revision)
    hf_cache.commit()
    return path


@app.function(image=image, gpu=GPU, volumes=VOLUMES, timeout=2 * 3600)
def train(arm: str, examples: list[dict], cfg: dict) -> dict:
    """LoRA fine-tune the base model on one arm's episodes; the adapter goes to the volume at /vol/<run>/<arm>."""
    lm, _, _ = _modules()
    out = f"/vol/{cfg['run']}/{arm}"
    stats = lm.train_lora(cfg["model_id"], cfg["revision"], examples, out, cfg["train"], log=lambda m: _log(f"[train {arm}] {m}"))
    adapters.commit()
    return dict(arm=arm, adapter=out, gpu=GPU, **stats)


@app.function(image=image, gpu=GPU, volumes=VOLUMES, timeout=3 * 3600)
def evaluate(arm: str, seeds: list[int], cfg: dict) -> dict:
    """Load the base model (plus the arm's adapter), let it control the robot on each seed in this container,
    and return the environment's score for every seed."""
    lm, policy_loop, _ = _modules()
    t0 = time.time()
    adapter = None if arm == "A" else f"/vol/{cfg['run']}/{arm}"
    if adapter:
        adapters.reload()
    tok, model = lm.load(cfg["model_id"], cfg["revision"], adapter)
    fn = lm.make_batch_model(tok, model, max_new_tokens=cfg["max_new_tokens"], batch_size=cfg["batch_size"])
    limits = dict(max_calls=cfg["max_calls"]) if cfg.get("max_calls") else {}
    results = policy_loop.run_batch(fn, seeds, cfg["level"], keep_dialogue=True,
                                    progress=lambda m: _log(f"[eval {arm}] {m}"), **limits)
    dialogues = [dict(seed=r["seed"], score=r["score"], messages=r.pop("messages")[1:]) for r in results]   # without the system prompt
    scores = [r["score"] for r in results]
    _log(f"[eval {arm}] mean {sum(scores) / len(scores):.3f}  {scores}")
    return dict(arm=arm, adapter=adapter, seeds=seeds, scores=scores, mean=sum(scores) / len(scores), per_seed=results,
                dialogues=dialogues, wall_s=round(time.time() - t0), gpu=GPU)


# ---------------------------------------------------------------------------------------------------
# Local side
# ---------------------------------------------------------------------------------------------------
def _git() -> dict:
    def run(*a):
        try:
            return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            return ""
    return dict(commit=run("rev-parse", "HEAD"), dirty=bool(run("status", "--porcelain", "--", "training", "probes/sweep")))


def _summary(ev: dict) -> dict:
    """One arm's evaluation without the dialogues, with a few counts that help explain the score."""
    per = ev["per_seed"]
    n = len(per)
    count = lambda key: {k: sum(1 for r in per if r[key] == k) for k in sorted({r[key] for r in per})}
    stones: dict[str, int] = {}
    for r in per:
        for k in r["milestones"]:
            stones[k] = stones.get(k, 0) + 1
    return dict(mean_score=round(ev["mean"], 4), scores={str(r["seed"]): r["score"] for r in per},
                solved=sum(1 for r in per if r["score"] >= 0.99), n=n, stop_reasons=count("stop_reason"),
                mean_turns=round(sum(r["turns"] for r in per) / n, 1), mean_invalid_replies=round(sum(r["invalid"] for r in per) / n, 1),
                mean_robot_time_s=round(sum(r["robot_time_s"] for r in per) / n, 1),
                milestones_reached_in_n_episodes=stones,       # for explanation only: milestones earn no score
                wall_s=ev["wall_s"], gpu=ev["gpu"],
                per_seed=[{k: v for k, v in r.items() if k != "tools"} for r in per])


def _compare(a: list[float], b: list[float]) -> dict:
    d = [x - y for x, y in zip(a, b)]
    return dict(mean_difference=round(sum(d) / len(d), 4), seeds_better=sum(x > 0 for x in d), seeds_equal=sum(x == 0 for x in d),
                seeds_worse=sum(x < 0 for x in d))


@app.local_entrypoint()
def main(smoke: bool = False, model_id: str = MODEL_ID, eval_seeds: str = EVAL_SEEDS, level: int = 1,
         data_dir: str = str(HERE / "data"), run: str = "", epochs: int = 3, lr: float = 2e-4, n: int = 0,
         batch_size: int = 8, max_calls: int = 0, seed: int = 0, max_len: int = 16384):
    """smoke: tiny run to check the path. n: cap on training episodes per arm (0 = all in the files).
    max_len: training episodes longer than this many tokens lose their tail."""
    _, _, T = _modules()
    data = Path(data_dir)
    sets = {arm: [json.loads(line) for line in (data / f"train_{arm}.jsonl").open()] for arm in ("B", "C")}
    meta = json.loads((data / "dataset_meta.json").read_text())
    seeds = T.parse_seeds(eval_seeds)
    train_cfg = dict(epochs=epochs, lr=lr, seed=seed, max_len=max_len)
    if smoke:
        sets = {arm: xs[:4] for arm, xs in sets.items()}
        seeds, max_calls = seeds[:1], max_calls or 12
        train_cfg.update(epochs=2, accum=1, max_steps=6)
    elif n:
        sets = {arm: xs[:n] for arm, xs in sets.items()}
    assert len(sets["B"]) == len(sets["C"]), "the two training sets must hold the same number of episodes"
    overlap = set(seeds) & set(meta["training_seeds"])
    assert not overlap, f"evaluation seeds must be held out; these were used for collection: {sorted(overlap)}"
    assert all(x["level"] == level for xs in sets.values() for x in xs), "the training data is from another level"
    run = run or ("smoke" if smoke else time.strftime("train-%m%d-%H%M"))
    cfg = dict(run=run, model_id=model_id, revision=MODEL_REVISIONS.get(model_id), level=level, max_calls=max_calls or None,
               max_new_tokens=96, batch_size=batch_size, train=train_cfg)

    out = REPO / "results" / "training" / f"{run}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    talk = REPO / "runs" / "training" / run
    talk.mkdir(parents=True, exist_ok=True)
    res = dict(experiment="post-training: base (A) vs reward-selected (B) vs unselected (C) experience", run=run, smoke=smoke,
               started=time.strftime("%Y-%m-%dT%H:%M:%S%z"), git=_git(), model_id=model_id, model_revision=cfg["revision"],
               setting="privileged, text only", level=level, eval_seeds=seeds, gpu=GPU, config=cfg,
               limits=dict(max_calls=max_calls or "policy_loop.MAX_CALLS", decoding="greedy"),
               dataset=dict(source=meta["source"], source_sha256=meta["source_sha256"], pool_episodes=meta["pool_episodes"],
                            pool_mean_score=meta["pool_mean_score"], threshold=meta["threshold"],
                            arms={arm: dict(episodes=len(xs), mean_score=round(sum(x["score"] for x in xs) / len(xs), 4),
                                            share_score_ge_099=round(sum(x["score"] >= 0.99 for x in xs) / len(xs), 4),
                                            assistant_turns=sum(x["n_calls"] + 1 for x in xs), seeds=[x["seed"] for x in xs])
                                  for arm, xs in sets.items()}),
               arms={}, training={}, status="running")
    ref = data / f"eval_reference_l{level}.jsonl"
    if ref.exists():                                   # the scripted reference on the same seeds, if it was collected
        by = {e["seed"]: e["score"] for e in map(json.loads, ref.open()) if e["variant"] == "reference"}
        if all(s in by for s in seeds):
            res["scripted_reference"] = dict(mean_score=round(sum(by[s] for s in seeds) / len(seeds), 4), scores={str(s): by[s] for s in seeds})

    def save():
        out.write_text(json.dumps(res, indent=1))

    def took(ev: dict):
        (talk / f"dialogues_{ev['arm']}.jsonl").write_text("".join(json.dumps(d) + "\n" for d in ev["dialogues"]))
        res["arms"][ev["arm"]] = _summary(ev)
        save()
        print(f"arm {ev['arm']}: mean score {ev['mean']:.3f} over {len(ev['seeds'])} seeds  {ev['scores']}")

    save()
    print(f"run {run}: model {model_id}, level {level}, {len(sets['B'])} training episodes per arm, eval seeds {eval_seeds if not smoke else seeds}")
    prefetch.remote(model_id, cfg["revision"])
    eval_a = evaluate.spawn("A", seeds, cfg)           # A, and the two trainings, run side by side on one GPU each
    trains = {arm: train.spawn(arm, sets[arm], cfg) for arm in ("B", "C")}
    evals = {}
    for arm in ("B", "C"):
        res["training"][arm] = trains[arm].get()
        save()
        print(f"trained {arm}: {res['training'][arm]['steps']} steps, final loss {res['training'][arm]['final_loss']}, {res['training'][arm]['wall_s']} s")
        evals[arm] = evaluate.spawn(arm, seeds, cfg)
    took(eval_a.get())
    for arm in ("B", "C"):
        took(evals[arm].get())

    s = {arm: [res["arms"][arm]["scores"][str(k)] for k in seeds] for arm in "ABC"}
    m = {arm: res["arms"][arm]["mean_score"] for arm in "ABC"}
    res["comparison"] = dict(means=m, B_minus_A=_compare(s["B"], s["A"]), B_minus_C=_compare(s["B"], s["C"]), C_minus_A=_compare(s["C"], s["A"]),
                             reward_selected_beats_base=m["B"] > m["A"], reward_selected_beats_unselected=m["B"] > m["C"])
    res["status"] = "done"
    res["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    save()
    print(f"\nmean score on seeds {seeds[0]}..{seeds[-1]} (level {level}):  A base {m['A']:.3f}   B reward-selected {m['B']:.3f}   C unselected {m['C']:.3f}")
    print(f"results: {out}\ndialogues: {talk}")
