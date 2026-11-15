"""The language-model side: turning dialogues into token ids and labels, LoRA fine-tuning, batched greedy decoding.

Imported inside the Modal container (torch, transformers and peft are there). `render` and `encode_example`
need only a tokenizer, so they can be checked on a laptop:  python training/lm.py --check <train.jsonl> <tokenizer dir>
"""
from __future__ import annotations

import json
import math
import random
import sys
import time

LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def render(tok, messages: list[dict], add_generation_prompt: bool) -> str:
    """The dialogue as the model's own chat template lays it out."""
    try:
        return tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=add_generation_prompt)
    except Exception:
        # a template without a system role: put the system prompt in front of the first user message
        if messages and messages[0]["role"] == "system" and len(messages) > 1:
            folded = [{"role": "user", "content": messages[0]["content"] + "\n\n" + messages[1]["content"]}] + list(messages[2:])
            return tok.apply_chat_template(folded, tokenize=False, add_generation_prompt=add_generation_prompt)
        raise


def encode_example(tok, messages: list[dict], max_len: int) -> dict:
    """input_ids and labels for one episode. Labels are -100 everywhere except on the assistant turns: the
    tokens of each tool call and the end-of-turn token after it. An episode longer than max_len loses its tail."""
    text = render(tok, messages, add_generation_prompt=False)
    spans, pos = [], 0
    for m in messages:                                   # every message appears verbatim, in order
        s = text.find(m["content"], pos)
        if s < 0:
            raise ValueError("the chat template altered a message; cannot place the labels")
        pos = s + len(m["content"])
        if m["role"] == "assistant":
            spans.append((s, pos))
    enc = tok(text, add_special_tokens=False, return_offsets_mapping=True)
    ids, offs = enc["input_ids"], enc["offset_mapping"]
    labels = [-100] * len(ids)
    j = 0
    for i, (a, b) in enumerate(offs):
        while j < len(spans) and spans[j][1] <= a:
            if b > a or ids[i] in tok.all_special_ids:   # first token after the call: the end-of-turn marker
                if i > 0 and labels[i - 1] != -100:
                    labels[i] = ids[i]
            j += 1
        if j < len(spans) and b > spans[j][0] and a < spans[j][1]:
            labels[i] = ids[i]
    truncated = len(ids) > max_len
    return dict(input_ids=ids[:max_len], labels=labels[:max_len], truncated=truncated, tokens=len(ids),
                label_tokens=sum(1 for v in labels[:max_len] if v != -100))


# ---------------------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------------------
def load(model_id: str, revision: str | None = None, adapter: str | None = None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(model_id, revision=revision)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(model_id, revision=revision, torch_dtype=torch.bfloat16)
    model.to("cuda")
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter).merge_and_unload()
    return tok, model


# ---------------------------------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------------------------------
TRAIN_DEFAULTS = dict(epochs=3, lr=2e-4, accum=4, warmup=0.05, max_len=16384, lora_r=32, lora_alpha=32, lora_dropout=0.0,
                      max_steps=None, seed=0, clip=1.0)


def train_lora(model_id: str, revision: str | None, examples: list[dict], out_dir: str, cfg: dict | None = None, log=print) -> dict:
    """LoRA fine-tuning on whole episodes, one episode per forward pass, loss on the assistant turns only."""
    import torch
    from peft import LoraConfig, get_peft_model
    c = {**TRAIN_DEFAULTS, **(cfg or {})}
    random.seed(c["seed"])
    torch.manual_seed(c["seed"])
    torch.cuda.manual_seed_all(c["seed"])
    t0 = time.time()
    tok, model = load(model_id, revision)
    encs = [encode_example(tok, x["messages"], c["max_len"]) for x in examples]
    log(f"{len(encs)} episodes, {sum(e['tokens'] for e in encs)} tokens, {sum(e['label_tokens'] for e in encs)} trained on, "
        f"{sum(e['truncated'] for e in encs)} cut at {c['max_len']} tokens, longest {max(e['tokens'] for e in encs)}")
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model = get_peft_model(model, LoraConfig(r=c["lora_r"], lora_alpha=c["lora_alpha"], lora_dropout=c["lora_dropout"],
                                             target_modules=LORA_TARGETS, task_type="CAUSAL_LM"))
    model.enable_input_require_grads()                   # gradient checkpointing needs an input that requires grad
    params = [p for p in model.parameters() if p.requires_grad]
    log(f"trainable parameters: {sum(p.numel() for p in params) / 1e6:.1f} M")
    opt = torch.optim.AdamW(params, lr=c["lr"], weight_decay=0.0)
    passes = len(encs) * c["epochs"]
    steps = math.ceil(passes / c["accum"])
    if c["max_steps"]:
        steps = min(steps, c["max_steps"])
    warm = max(1, int(c["warmup"] * steps))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warm if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, steps - warm))))
    rng = random.Random(c["seed"])
    order = []
    for _ in range(c["epochs"]):
        idx = list(range(len(encs)))
        rng.shuffle(idx)
        order += idx
    model.train()
    step, losses, curve = 0, [], []
    opt.zero_grad(set_to_none=True)
    for n, i in enumerate(order, 1):
        e = encs[i]
        ids = torch.tensor([e["input_ids"]], device="cuda")
        lab = torch.tensor([e["labels"]], device="cuda")
        with torch.autocast("cuda", dtype=torch.bfloat16):
            loss = model(input_ids=ids, labels=lab).loss
        (loss / c["accum"]).backward()
        losses.append(float(loss))
        if n % c["accum"] == 0 or n == len(order):
            torch.nn.utils.clip_grad_norm_(params, c["clip"])
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            if step % 10 == 0 or step == steps:
                mean = sum(losses) / len(losses)
                curve.append(dict(step=step, loss=round(mean, 4)))
                log(f"step {step}/{steps}  loss {mean:.4f}  lr {sched.get_last_lr()[0]:.2e}  {time.time() - t0:.0f} s")
                losses = []
            if step >= steps:
                break
    model.save_pretrained(out_dir)
    return dict(episodes=len(encs), tokens=sum(e["tokens"] for e in encs), label_tokens=sum(e["label_tokens"] for e in encs),
                truncated=sum(e["truncated"] for e in encs), steps=step, loss_curve=curve,
                final_loss=curve[-1]["loss"] if curve else None, wall_s=round(time.time() - t0), config=c)


# ---------------------------------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------------------------------
def make_batch_model(tok, model, max_new_tokens: int = 96, batch_size: int = 8):
    """A function for policy_loop.run_batch: a list of dialogues in, the model's next reply for each out. Greedy."""
    import torch
    tok.padding_side = "left"
    model.eval()
    model.config.use_cache = True

    def fn(dialogues: list[list[dict]]) -> list[str]:
        out: list[str] = []
        for k in range(0, len(dialogues), batch_size):
            texts = [render(tok, m, add_generation_prompt=True) for m in dialogues[k:k + batch_size]]
            enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to("cuda")
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                gen = model.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, temperature=None, top_p=None,
                                     top_k=None, pad_token_id=tok.pad_token_id)
            out += tok.batch_decode(gen[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
        return out
    return fn


# ---------------------------------------------------------------------------------------------------
if __name__ == "__main__" and len(sys.argv) >= 4 and sys.argv[1] == "--check":
    # python training/lm.py --check training/data/train_B.jsonl <dir with tokenizer.json and tokenizer_config.json>
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(sys.argv[3])
    lens = []
    for line in list(open(sys.argv[2]))[:8]:
        x = json.loads(line)
        e = encode_example(tok, x["messages"], 10**9)
        said = [m["content"] for m in x["messages"] if m["role"] == "assistant"]
        got, cur = [], []
        for t, l in zip(e["input_ids"], e["labels"]):
            if l != -100:
                cur.append(t)
            elif cur:
                got.append(tok.decode(cur))
                cur = []
        if cur:
            got.append(tok.decode(cur))
        eot = {g[len(s):] for g, s in zip(got, said)}
        ok = len(got) == len(said) and all(g.startswith(s) for g, s in zip(got, said)) and len(eot) == 1
        lens.append(e["tokens"])
        print(f"seed {x['seed']}: {e['tokens']} tokens, {e['label_tokens']} labelled, {len(said)} assistant turns, "
              f"labelled spans = the calls + {eot}: {'OK' if ok else 'WRONG'}")
        assert ok
        prefix = render(tok, x["messages"][:4], True)
        assert render(tok, x["messages"], False).startswith(prefix), "generation prompt is not a prefix of the training text"
    print("labels check passed; the generation prompt is a prefix of the training text; tokens per episode", lens)
