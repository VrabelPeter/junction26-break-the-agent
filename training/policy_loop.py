"""Run a language model as the robot's controller, in-process, and return the environment's score.

The model is a function: chat messages in, text out. Each turn it gets the system prompt and the dialogue so
far (its own tool calls, each followed by the tool's compact reply) and must answer with one JSON tool call.
The loop parses it, applies it to the simulator's World, and feeds the compact reply back. It ends on
{"tool":"done"}, on the call limit, when robot time is used up, when the dialogue outgrows the context
budget, or after a streak of replies that are not tool calls. The score is World.score(): the environment's own.

    Episode          one episode as a state machine (messages -> step(text) -> ... -> result)
    run_episode      one model function, one seed
    run_batch        many seeds in lockstep with a batched model function (how the GPU evaluation runs)

Stand-ins for a model, to test the loop without a GPU:
    ReplayModel      says the recorded calls of an episode one after the other
    reference_through_text   the scripted reference, allowed to see only the compact text replies

Checks (no GPU, a few seconds per episode):
    python training/policy_loop.py --replay training/data/check_l1.jsonl --n 4
    python training/policy_loop.py --text-reference --seeds 1-4 --level 1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textenv as T      # noqa: E402

MAX_CALLS = {1: 120, 2: 400, 3: 700}       # about twice what the reference needs at each level
MAX_PROMPT_CHARS = {1: 45_000, 2: 120_000, 3: 220_000}   # the context budget, in characters so it does not depend on the tokenizer (2.5 characters per
                                            # token: 18k tokens at level 1, where the reference needs at most about 9.5k)
MAX_INVALID_STREAK = 8                      # this many replies in a row that are not tool calls end the episode
KEEP_TEXT = 300                             # a model's reply is kept in the dialogue up to this many characters


class Episode:
    """One episode of the privileged, text-only setting."""

    def __init__(self, seed: int, level: int = 1, max_calls: int | None = None, max_prompt_chars: int | None = None,
                 max_invalid_streak: int = MAX_INVALID_STREAK):
        sim, _, _ = T.import_sweep()
        self.seed, self.level = seed, level
        self.world = sim.World(seed, level, privileged=True)
        self.time_limit = sim.TIME_LIMIT
        self.max_calls = max_calls or MAX_CALLS.get(level, 400)
        self.max_prompt_chars = max_prompt_chars or MAX_PROMPT_CHARS.get(level, 220_000)
        self.max_invalid_streak = max_invalid_streak
        self.messages = T.start_messages(level)
        self.calls: list[dict] = []
        self.turns = self.invalid = self.streak = self.failed = 0
        self.stop_reason: str | None = None
        self._result: dict | None = None

    @property
    def done(self) -> bool:
        return self.stop_reason is not None

    def step(self, text: str) -> str | None:
        """Apply the model's reply. Returns the tool's compact reply (None when the episode ended on this turn)."""
        if self.done:
            return None
        self.turns += 1
        text = text.strip()
        try:
            tool, args = T.parse_call(text)
        except T.BadCall as e:
            self.invalid += 1
            self.streak += 1
            reply = json.dumps({"ok": False, "error": f"{e}. Reply with exactly one JSON tool call."}, separators=(",", ":"))
            self.calls.append(dict(tool=None, text=text[:KEEP_TEXT], reply=reply))
        else:
            self.streak = 0
            if tool == T.DONE:
                self.messages.append({"role": "assistant", "content": T.format_call(T.DONE)})
                self.stop_reason = "done"
                return None
            t0 = round(self.world.robot_time, 2)
            r = self.world.call(tool, **args)
            reply = T.compact_reply(tool, args, r)
            self.failed += 0 if r.get("ok") else 1
            self.calls.append(dict(tool=tool, args=args, t=t0, reply=reply))
        self.messages.append({"role": "assistant", "content": text[:KEEP_TEXT]})
        self.messages.append({"role": "user", "content": reply})
        if self.world.robot_time >= self.time_limit:
            self.stop_reason = "robot_time"
        elif self.turns >= self.max_calls:
            self.stop_reason = "call_limit"
        elif self.streak >= self.max_invalid_streak:
            self.stop_reason = "invalid_streak"
        elif sum(len(m["content"]) for m in self.messages) > self.max_prompt_chars:
            self.stop_reason = "context"
        return None if self.done else reply

    def result(self) -> dict:
        """The environment's score for where the room ended up (asking for it ends the episode)."""
        if self._result is None:
            if not self.done:
                self.stop_reason = "aborted"
            s = self.world.score()
            self._result = dict(seed=self.seed, level=self.level, score=s["score"], trash_in_bin=s["trash_in_bin"],
                                trash_total=s["trash_total"], mistakes=s["mistakes"], milestones=s["milestones"],
                                robot_time_s=s["robot_time_s"], stop_reason=self.stop_reason, turns=self.turns,
                                invalid=self.invalid, failed_calls=self.failed,
                                tools=[c["tool"] for c in self.calls])
        return self._result


def run_episode(model: Callable[[list[dict]], str], seed: int, level: int = 1, keep_dialogue: bool = False, **limits) -> dict:
    ep = Episode(seed, level, **limits)
    while not ep.done:
        ep.step(model(ep.messages))
    out = ep.result()
    if keep_dialogue:
        out["messages"] = ep.messages
    return out


def run_batch(batch_model: Callable[[list[list[dict]]], list[str]], seeds: list[int], level: int = 1,
              keep_dialogue: bool = False, progress: Callable[[str], None] | None = None, **limits) -> list[dict]:
    """All seeds at once: every turn the model answers for every episode still running."""
    eps = [Episode(s, level, **limits) for s in seeds]
    turn, t = 0, time.time()
    while True:
        live = [e for e in eps if not e.done]
        if not live:
            break
        for e, text in zip(live, batch_model([e.messages for e in live])):
            e.step(text)
        turn += 1
        if progress and turn % 10 == 0:
            progress(f"turn {turn}: {len(live)} of {len(eps)} episodes running, {time.time() - t:.0f} s")
    out = []
    for e in eps:
        r = e.result()
        if keep_dialogue:
            r["messages"] = e.messages
        out.append(r)
    return out


# ---------------------------------------------------------------------------------------------------
# Stand-ins for a model
# ---------------------------------------------------------------------------------------------------
class ReplayModel:
    """Says a recorded episode's calls in order, then done. Ignores what it is shown."""

    def __init__(self, calls: list[dict]):
        self.lines = [T.format_call(c["tool"], c["args"]) for c in calls] + [T.format_call(T.DONE)]
        self.i = 0

    def __call__(self, messages: list[dict]) -> str:
        line = self.lines[min(self.i, len(self.lines) - 1)]
        self.i += 1
        return line


def reference_through_text(seed: int, level: int = 1) -> dict:
    """The scripted reference with the text interface in between: every call it makes is written as text and
    parsed back, and all it ever reads is the compact reply. If it still solves the room, the compact
    replies carry everything needed."""
    _, policies, _ = T.import_sweep()
    ep = Episode(seed, level, max_calls=10_000, max_prompt_chars=10**9)

    class Robot:
        scene = ep.world.scene

        def _say(self, tool, **args):
            reply = ep.step(T.format_call(tool, args))
            if reply is None:
                raise RuntimeError(ep.stop_reason)
            c = json.loads(reply)
            if not c.get("ok"):
                raise RuntimeError(c.get("error"))
            return T.expand_observe(reply) if tool == "observe" else c

        def observe(self): return self._say("observe")
        def drive_to(self, x, y, heading): return self._say("drive_to", x=x, y=y, heading=heading)
        def move_arm(self, arm, x, y, z, yaw): return self._say("move_arm", arm=arm, x=x, y=y, z=z, yaw=yaw)
        def home_arm(self, arm): return self._say("home_arm", arm=arm)
        def grasp(self, arm): return self._say("grasp", arm=arm)
        def release(self, arm): return self._say("release", arm=arm)
        def look(self, pan, tilt): return self._say("look", pan=pan, tilt=tilt)
        def set_torso(self, height): return self._say("set_torso", height=height)
        def score(self): return {}

    policies.reference_privileged(Robot())
    if not ep.done:
        ep.step(T.format_call(T.DONE))
    return ep.result()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", help="episodes JSONL from collect.py: replay each through the text loop and compare scores")
    ap.add_argument("--n", type=int, default=4, help="how many episodes of the file to replay (spread over the file)")
    ap.add_argument("--text-reference", action="store_true", help="run the scripted reference through the text interface")
    ap.add_argument("--seeds", default="1-4")
    ap.add_argument("--level", type=int, default=1)
    a = ap.parse_args()
    os.environ.setdefault("MUJOCO_GL", "egl")
    ok = True
    if a.replay:
        eps = [json.loads(line) for line in open(a.replay)]
        step = max(1, len(eps) // a.n)
        for e in eps[::step][:a.n]:
            r = run_episode(ReplayModel(e["calls"]), e["seed"], e["level"], max_calls=10_000, max_prompt_chars=10**9)
            same = abs(r["score"] - e["score"]) < 1e-9
            ok &= same
            print(f"replay seed {e['seed']} {e['variant']:12s}: recorded {e['score']:g}, through text {r['score']:g}, "
                  f"{r['turns']} turns, stop {r['stop_reason']}  {'OK' if same else 'DIFFERENT'}")
    if a.text_reference:
        scores = []
        for s in T.parse_seeds(a.seeds):
            r = reference_through_text(s, a.level)
            scores.append(r["score"])
            print(f"reference through text, seed {s} level {a.level}: score {r['score']:g}, {r['turns']} turns, robot time {r['robot_time_s']} s")
        print(f"reference through text: mean {sum(scores) / len(scores):.3f} over {len(scores)} seeds")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
