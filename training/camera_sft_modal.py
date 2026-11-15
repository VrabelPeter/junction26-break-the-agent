"""Fine-tune Qwen3.5-9B on camera-task conversations (camera_chats.py) and save a model vLLM can serve.

    .venv/bin/modal run training/camera_sft_modal.py --smoke                         # a few minutes: checks the whole path
    .venv/bin/modal run --detach training/camera_sft_modal.py --n 600 --budget-min 60   # the training

One H100. LoRA on every linear layer, one whole episode per forward pass, loss on the assistant turns only
(the tool calls, the sentence that names the pixel, the closing sentence). The text is laid out by the model's
own chat template with OpenCode's tool list, thinking off, pictures through the model's own processor: the same
path vLLM takes when the model is served. Training stops when the time budget is used.

Checks on held-out rooms (the last --held chats of the file), before the adapter is merged:
  - teacher-forced: share of assistant turns whose every token is predicted right
  - free generation of the turn after the picture: distance between the pixel named and the label

The merged model is written to the volume `sweep-hf-cache` at ft/<run>, where serving/qwen_vl_modal.py
(MODEL_VARIANT=qwen35-9b-ft, FT_RUN=<run>) picks it up. Weights & Biases is used when the Modal secret `wandb`
exists (WANDB_API_KEY).
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import time
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
MODEL_ID = "Qwen/Qwen3.5-9B"
GPU = "H100"
DATA = "/data"

app = modal.App("sweep-camera-sft")
image = (modal.Image.from_registry("nvidia/cuda:12.8.0-devel-ubuntu22.04", add_python="3.12").entrypoint([])
         .pip_install("vllm==0.33.0", "peft", "wandb", "pillow")
         # the model's fast kernels; without them transformers falls back to slow reference code (47 s per episode)
         .run_commands("pip install flash-linear-attention", "pip install causal-conv1d || echo 'causal-conv1d not built'")
         .env({"PYTHONUNBUFFERED": "1", "TOKENIZERS_PARALLELISM": "false"}))
if modal.is_local():
    image = image.add_local_dir(os.environ.get("CHATS_DIR", str(REPO / "runs/training/camera/chats2_l1")), DATA)
hf_cache = modal.Volume.from_name("sweep-hf-cache", create_if_missing=True)
SECRETS = [modal.Secret.from_name("wandb")] if os.environ.get("USE_WANDB", "1") == "1" else []

DEFAULTS = dict(n=600, held=40, epochs=1, lr=1e-4, accum=4, warmup=0.05, lora_r=32, lora_alpha=32, clip=1.0, seed=0,
                budget_s=3600, max_tokens=40000, num_weight=5.0, merge=True, gen_check=16)


def _log(m: str):
    print(m, flush=True)


@app.function(image=image, gpu=GPU, volumes={"/root/.cache/huggingface": hf_cache}, secrets=SECRETS, timeout=4 * 3600)
def train(cfg: dict) -> dict:
    import torch
    from peft import LoraConfig, get_peft_model
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor
    import transformers
    c = {**DEFAULTS, **cfg}
    run = c["run"]
    random.seed(c["seed"])
    torch.manual_seed(c["seed"])
    t0 = time.time()
    tools = json.loads(Path(f"{DATA}/tools.json").read_text())
    chats = [json.loads(line) for line in open(f"{DATA}/chats.jsonl")]
    held = chats[-c["held"]:]
    pool = chats[:-c["held"]][:c["n"]]
    _log(f"transformers {transformers.__version__}, torch {torch.__version__}; {len(pool)} training chats, {len(held)} held out")

    proc = AutoProcessor.from_pretrained(MODEL_ID)
    tok = proc.tokenizer
    model = AutoModelForImageTextToText.from_pretrained(MODEL_ID, dtype=torch.bfloat16, device_map="cuda")
    _log(f"model {type(model).__name__} loaded in {time.time() - t0:.0f} s")
    im_start, im_end = tok.convert_tokens_to_ids("<|im_start|>"), tok.convert_tokens_to_ids("<|im_end|>")
    head = tok.encode("assistant\n", add_special_tokens=False)

    def prepared(messages: list[dict]) -> list[dict]:
        out = []
        for m in messages:
            m = dict(m)
            if isinstance(m["content"], list):
                m["content"] = [dict(type="image", image=Image.open(f"{DATA}/images/{p['path']}").convert("RGB")) if p["type"] == "image" else p
                                for p in m["content"]]
            if m.get("tool_calls"):          # the template wants the arguments as an object, as vLLM hands them over
                m["tool_calls"] = [dict(t, function=dict(t["function"], arguments=json.loads(t["function"]["arguments"]))) for t in m["tool_calls"]]
            out.append(m)
        return out

    def encode(messages: list[dict], gen: bool = False) -> dict:
        enc = proc.apply_chat_template(prepared(messages), tools=tools, add_generation_prompt=gen, tokenize=True,
                                       return_dict=True, return_tensors="pt", enable_thinking=False)
        ids = enc["input_ids"][0].tolist()
        labels, spans, i = [-100] * len(ids), [], 0
        while i < len(ids):
            if ids[i] == im_start and ids[i + 1:i + 1 + len(head)] == head:
                a = i + 1 + len(head)
                b = a
                while b < len(ids) and ids[b] != im_end:
                    b += 1
                if b < len(ids):
                    labels[a:b + 1] = ids[a:b + 1]
                    spans.append((a, b + 1))
                i = b
            i += 1
        enc["labels"] = torch.tensor([labels])
        # Numbers decide whether the brush meets the trash, and they are few: they count `num_weight` times.
        # Not the fixed numbers inside the long shell script (only its first 40 tokens: the pixel sentence).
        w = torch.ones(len(ids))
        for a, b in spans:
            end = b if b - a < 400 else a + 40
            seg = torch.tensor(ids[a:end])
            w[a:end][has_digit[seg]] = c["num_weight"]
        return dict(enc=enc, spans=spans, tokens=len(ids), weight=w)

    has_digit = torch.tensor([any(ch.isdigit() for ch in t) for t in tok.convert_ids_to_tokens(list(range(len(tok))))])
    first = encode(pool[0]["messages"])
    ids0 = first["enc"]["input_ids"][0].tolist()
    a, b = first["spans"][5]
    _log(f"first chat: {first['tokens']} tokens, {len(first['spans'])} assistant turns, {sum(e - s for s, e in first['spans'])} tokens trained on")
    _log("text around the turn after the picture:\n" + tok.decode(ids0[a - 40:b + 5]).replace("<|image_pad|>", ""))
    _log("a later turn: " + repr(tok.decode(ids0[first["spans"][9][0] - 6:first["spans"][9][1]])))
    gen0 = encode(pool[0]["messages"][:2], gen=True)["enc"]["input_ids"][0].tolist()
    _log("generation prompt ends with: " + repr(tok.decode(gen0[-12:])))

    wb = None
    if os.environ.get("WANDB_API_KEY"):
        import wandb
        wb = wandb.init(project="sweep-qwen35-sft", name=run, config={k: v for k, v in c.items()})
        _log(f"wandb: {wb.url}")

    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model = get_peft_model(model, LoraConfig(r=c["lora_r"], lora_alpha=c["lora_alpha"], lora_dropout=0.0,
                                             target_modules="all-linear", task_type="CAUSAL_LM"))
    try:
        model.enable_input_require_grads()
    except Exception as e:                     # noqa: BLE001
        _log(f"enable_input_require_grads not available: {e!r}")
    params = [p for p in model.parameters() if p.requires_grad]
    _log(f"trainable parameters: {sum(p.numel() for p in params) / 1e6:.1f} M")
    opt = torch.optim.AdamW(params, lr=c["lr"], weight_decay=0.0)

    def forward(e):
        """Loss and predictions on the trained-on positions only: logits for the whole 26,000-token episode do not fit."""
        enc = {k: v.to("cuda") for k, v in e["enc"].items() if k != "labels"}
        lab = e["enc"]["labels"][0].to("cuda")
        pos = (lab != -100).nonzero().squeeze(1)
        inner = model.base_model.model
        with torch.autocast("cuda", dtype=torch.bfloat16):
            h = inner.model(**enc).last_hidden_state[0]
            logits = inner.lm_head(h[pos - 1])
        wt = e["weight"].to("cuda")[pos]
        loss = (torch.nn.functional.cross_entropy(logits.float(), lab[pos], reduction="none") * wt).sum() / wt.sum()
        return loss, logits.argmax(-1), pos

    def held_check(tag: str) -> dict:
        """Teacher-forced on held-out rooms: are whole assistant turns predicted right?"""
        model.eval()
        turns = right = tok_n = tok_ok = num_n = num_ok = 0
        by_pos: dict[int, list[int]] = {}
        with torch.inference_mode():
            for x in held[:c["gen_check"]]:
                e = encode(x["messages"])
                _, pred, pos = forward(e)
                good = torch.zeros(e["tokens"], dtype=torch.bool)
                good[pos.cpu()] = (pred == e["enc"]["labels"][0].to("cuda")[pos]).cpu()
                heavy = e["weight"] > 1
                num_n, num_ok = num_n + int(heavy.sum()), num_ok + int(good[heavy].sum())
                for k, (s, t) in enumerate(e["spans"]):
                    ok = bool(good[s:t].all())
                    turns, right = turns + 1, right + ok
                    tok_n, tok_ok = tok_n + (t - s), tok_ok + int(good[s:t].sum())
                    by_pos.setdefault(k, []).append(int(ok))
        model.train()
        res = dict(turns_exact=round(right / turns, 4), token_accuracy=round(tok_ok / tok_n, 4),
                   number_tokens=num_n, number_token_accuracy=round(num_ok / max(1, num_n), 4),
                   exact_by_turn=[round(sum(v) / len(v), 2) for _, v in sorted(by_pos.items())][:60])
        _log(f"[{tag}] held-out, teacher-forced: {res['turns_exact']:.1%} of {turns} turns exact, token accuracy {res['token_accuracy']:.2%}")
        _log(f"[{tag}] number tokens right: {res['number_token_accuracy']:.2%} of {num_n}")
        _log(f"[{tag}] exact by turn number: {res['exact_by_turn']}")
        return res

    def pointing(tag: str) -> dict:
        """Free generation of the turn after the picture: which pixel does the model name?"""
        model.eval()
        errs, shown, missing = [], 0, 0
        with torch.inference_mode():
            for x in held[:c["gen_check"]]:
                k = next(i for i, m in enumerate(x["messages"]) if isinstance(m["content"], list))
                enc = {kk: v.to("cuda") for kk, v in encode(x["messages"][:k + 1], gen=True)["enc"].items() if kk != "labels"}
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    out = model.generate(**enc, max_new_tokens=260, do_sample=False)
                text = tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=False)
                if shown < 2:
                    _log(f"[{tag}] seed {x['seed']} label {x['pixel']} generated: {text[:600]!r}")
                    shown += 1
                m = re.search(r"pixel \((\d+), (\d+)\)", text)
                if m:
                    errs.append(math.hypot(int(m[1]) - x["pixel"][0], int(m[2]) - x["pixel"][1]))
                else:
                    missing += 1
        model.train()
        errs.sort()
        res = dict(n=len(errs), no_pixel=missing, median_px=errs[len(errs) // 2] if errs else None, max_px=errs[-1] if errs else None,
                   within_5px=sum(e <= 5 for e in errs), errors_px=[round(e, 1) for e in errs])
        _log(f"[{tag}] pointing on held-out rooms: {res}")
        return res

    checks = {}
    order = []
    rng = random.Random(c["seed"])
    for _ in range(c["epochs"]):
        idx = list(range(len(pool)))
        rng.shuffle(idx)
        order += idx
    model.train()
    t_train = time.time()
    done, losses, curve, step, planned = 0, [], [], 0, len(order)
    opt.zero_grad(set_to_none=True)
    for n, i in enumerate(order, 1):
        e = encode(pool[i]["messages"])
        if e["tokens"] > c["max_tokens"]:
            continue
        loss = forward(e)[0]
        (loss / c["accum"]).backward()
        losses.append(float(loss))
        done += 1
        if done == 8:                         # the pace is known now: how many episodes fit the budget?
            pace = (time.time() - t_train) / done
            planned = min(len(order), int(c["budget_s"] / pace))
            _log(f"{pace:.1f} s per episode, {torch.cuda.max_memory_allocated() / 2**30:.1f} GB peak; "
                 f"{planned} of {len(order)} episode passes fit the budget of {c['budget_s']} s")
            t_mark = time.time()
        if done > 8 and done % 30 == 0:       # the first episodes are slow: judge the pace again from the last 30
            pace, t_mark = (time.time() - t_mark) / (30 if done > 30 else 22), time.time()
            planned = min(len(order), done + int((c["budget_s"] - (time.time() - t_train)) / pace))
            _log(f"{pace:.1f} s per episode now: {planned} of {len(order)} episode passes fit the budget")
        if done % c["accum"] == 0:
            frac = min(1.0, done / max(1, planned))
            warm = c["warmup"]
            lr = c["lr"] * (frac / warm if frac < warm else 0.5 * (1 + math.cos(math.pi * (frac - warm) / (1 - warm))))
            for g in opt.param_groups:
                g["lr"] = max(lr, c["lr"] * 0.02)
            torch.nn.utils.clip_grad_norm_(params, c["clip"])
            opt.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            if step % 5 == 0:
                mean = sum(losses) / len(losses)
                curve.append(dict(step=step, episodes=done, loss=round(mean, 4)))
                _log(f"step {step}  episodes {done}/{planned}  loss {mean:.4f}  lr {lr:.2e}  {time.time() - t_train:.0f} s")
                if wb:
                    wb.log(dict(loss=mean, lr=lr, episodes=done, seconds=time.time() - t_train), step=step)
                losses = []
        if done >= planned or (c.get("max_passes") and done >= c["max_passes"]):
            break
    train_s = round(time.time() - t_train)
    checks["held"] = held_check("after")
    checks["pointing"] = pointing("after")
    if wb:
        wb.log({"held/turns_exact": checks["held"]["turns_exact"], "held/token_accuracy": checks["held"]["token_accuracy"],
                "held/pointing_median_px": checks["pointing"]["median_px"] or -1})
    out = f"/root/.cache/huggingface/ft/{run}"
    model.save_pretrained(out + "-adapter")
    if c["merge"]:
        merged = model.merge_and_unload()
        merged.config.use_cache = True
        merged.save_pretrained(out, safe_serialization=True)
        proc.save_pretrained(out)
        _log(f"merged model written to {out}: {sorted(os.listdir(out))}")
    hf_cache.commit()
    if wb:
        wb.finish()
    return dict(run=run, model=MODEL_ID, gpu=GPU, episodes_seen=done, steps=step, train_s=train_s, wall_s=round(time.time() - t0),
                loss_curve=curve, final_loss=curve[-1]["loss"] if curve else None, checks=checks, merged=out if c["merge"] else None,
                config=c, training_seeds=[pool[i]["seed"] for i in order[:n]], held_seeds=[x["seed"] for x in held])


@app.local_entrypoint()
def main(smoke: bool = False, n: int = 600, budget_min: float = 60, run: str = "", lr: float = 1e-4, epochs: int = 1, held: int = 40):
    run = run or ("smoke" if smoke else time.strftime("sft-%m%d-%H%M"))
    cfg = dict(run=run, n=n, budget_s=int(budget_min * 60), lr=lr, epochs=epochs, held=held)
    if smoke:
        cfg.update(n=12, max_passes=12, accum=2, gen_check=3, held=4)
    res = train.remote(cfg)
    out = REPO / "results" / "training" / f"camera-{run}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("run", "episodes_seen", "steps", "train_s", "final_loss", "checks", "merged")}, indent=1)[:3000])
    print(f"results: {out}")
