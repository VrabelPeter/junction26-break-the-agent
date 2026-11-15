"""Turn collected episodes into training examples for next-tool-call prediction, and build the two training sets.

    python training/dataset.py --episodes training/data/episodes_l1.jsonl --out-dir training/data

One example is one whole episode as a chat: the system prompt, then for every call an assistant turn (the call as
one JSON object) and a user turn (the tool's compact reply), ending with the assistant saying {"tool":"done"}.
The model is trained on the assistant turns only. Replies are shortened by textenv.compact_reply, the same
function the evaluation loop uses.

Two sets of the same number of episodes, drawn from the same pool:
    B  selected by the reward: episodes whose environment score is >= --threshold (default 0.99)
    C  not selected: drawn at random from all episodes, whatever their score
Arm A (the untrained model) needs no data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textenv as T      # noqa: E402


def episode_to_messages(ep: dict) -> list[dict]:
    msgs = T.start_messages(ep["level"])
    for c in ep["calls"]:
        msgs.append({"role": "assistant", "content": T.format_call(c["tool"], c["args"])})
        msgs.append({"role": "user", "content": T.compact_reply(c["tool"], c["args"], c["result"])})
    msgs.append({"role": "assistant", "content": T.format_call(T.DONE)})
    return msgs


def episode_to_example(ep: dict) -> dict:
    return dict(seed=ep["seed"], level=ep["level"], variant=ep["variant"], score=ep["score"],
                n_calls=len(ep["calls"]), messages=episode_to_messages(ep))


def build_sets(episodes: list[dict], threshold: float = 0.99, n: int | None = None, seed: int = 0) -> tuple[list[dict], list[dict]]:
    """(B, C): reward-selected episodes, and the same number drawn at random from all of them."""
    good = [e for e in episodes if e["score"] >= threshold]
    rng = random.Random(seed)
    n = min(n or len(good), len(good))
    b = sorted(rng.sample(good, n), key=lambda e: e["seed"])
    c = sorted(random.Random(seed + 1).sample(episodes, n), key=lambda e: e["seed"])
    return b, c


# ---- token counts ---------------------------------------------------------------------------------
def chatml(messages: list[dict]) -> str:
    """How Qwen's chat template lays a dialogue out (used for counting only; training uses the model's own template)."""
    return "".join(f"<|im_start|>{m['role']}\n{m['content']}<|im_end|>\n" for m in messages)


def token_counter(tokenizer_json: str | None):
    if tokenizer_json:
        from tokenizers import Tokenizer      # noqa: PLC0415
        tok = Tokenizer.from_file(tokenizer_json)
        return (lambda text: len(tok.encode(text, add_special_tokens=False).ids)), f"tokenizer {tokenizer_json}"
    return T.approx_tokens, f"approximation: characters / {T.CHARS_PER_TOKEN}"


def describe(name: str, examples: list[dict], count) -> dict:
    total = [count(chatml(x["messages"])) for x in examples]
    said = [sum(count(m["content"]) for m in x["messages"] if m["role"] == "assistant") for x in examples]
    q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * len(v)))]
    scores = [x["score"] for x in examples]
    d = dict(arm=name, episodes=len(examples), assistant_turns=sum(x["n_calls"] + 1 for x in examples),
             mean_score=round(statistics.mean(scores), 4), share_score_ge_099=round(sum(s >= 0.99 for s in scores) / len(scores), 4),
             variants=dict(sorted(Counter(x["variant"] for x in examples).items())),
             tokens_per_episode=dict(min=min(total), median=q(total, 0.5), p90=q(total, 0.9), max=max(total), total=sum(total)),
             assistant_tokens_total=sum(said), seeds=[x["seed"] for x in examples])
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", default=str(T.HERE / "data" / "episodes_l1.jsonl"))
    ap.add_argument("--out-dir", default=str(T.HERE / "data"))
    ap.add_argument("--threshold", type=float, default=0.99, help="B keeps episodes with score >= this")
    ap.add_argument("--n", type=int, default=None, help="episodes per arm (default: every episode that passes the threshold)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tokenizer-json", default=None, help="a tokenizer.json to count tokens exactly (needs the `tokenizers` package)")
    a = ap.parse_args()

    raw = Path(a.episodes).read_bytes()
    episodes = [json.loads(line) for line in raw.splitlines() if line.strip()]
    b, c = build_sets(episodes, a.threshold, a.n, a.seed)
    count, how = token_counter(a.tokenizer_json)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = dict(source=str(a.episodes), source_sha256=hashlib.sha256(raw).hexdigest(), pool_episodes=len(episodes),
                pool_mean_score=round(statistics.mean(e["score"] for e in episodes), 4),
                pool_share_score_ge_threshold=round(sum(e["score"] >= a.threshold for e in episodes) / len(episodes), 4),
                levels=sorted({e["level"] for e in episodes}), threshold=a.threshold, seed=a.seed, token_count=how,
                system_prompt_tokens=count(T.SYSTEM_PROMPT), training_seeds=sorted({e["seed"] for e in episodes}), arms={})
    for name, eps in (("B", b), ("C", c)):
        examples = [episode_to_example(e) for e in eps]
        path = out / f"train_{name}.jsonl"
        with path.open("w") as f:
            for x in examples:
                f.write(json.dumps(x, separators=(",", ":")) + "\n")
        d = describe(name, examples, count)
        d["file"] = path.name
        meta["arms"][name] = d
        t = d["tokens_per_episode"]
        print(f"{name}: {d['episodes']} episodes, {d['assistant_turns']} assistant turns, mean score {d['mean_score']}, "
              f"share >= 0.99: {d['share_score_ge_099']}\n   tokens per episode: min {t['min']}, median {t['median']}, p90 {t['p90']}, max {t['max']}; "
              f"total {t['total']}, of which trained on (assistant) {d['assistant_tokens_total']}\n   variants {d['variants']}")
    (out / "dataset_meta.json").write_text(json.dumps(meta, indent=1))
    print(f"pool: {len(episodes)} episodes, mean score {meta['pool_mean_score']}, share >= {a.threshold}: {meta['pool_share_score_ge_threshold']}; "
          f"system prompt {meta['system_prompt_tokens']} tokens ({how})\nwrote {out}/train_B.jsonl, train_C.jsonl, dataset_meta.json")


if __name__ == "__main__":
    main()
