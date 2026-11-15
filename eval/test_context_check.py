"""Tests for eval/context_check.py. Run: python3 -m unittest discover -s eval -p 'test_*.py'"""
import http.server
import json
import os
import tempfile
import threading
import unittest

import context_check as cc

# Messages in the shapes providers and OpenCode use when a request does not fit the window.
OVERFLOW_MESSAGES = [
    "This model's maximum context length is 32768 tokens. However, you requested 40112 tokens "
    "(35112 in the messages, 5000 in the completion). Please reduce the length of the messages or completion.",
    '{"error":{"code":"context_length_exceeded","message":"Input too long"}}',
    "Prompt is too long: 41000 tokens > 32768 maximum",
    "The input exceeds the model's context window of 32768 tokens",
    "max_tokens (32000) must be at most 4096",
    "Requested tokens (40112) exceed context window of 32768",
    "This model's max_model_len is 32768",
]
NOT_OVERFLOW = [
    "t.responses is not a function. (In 't.responses(i)', 't.responses' is undefined)",
    "Requests that would take your total reserved units above your plan budget are rejected",
    "Request would exceed your plan's concurrency limit (HTTP 429)",
    "Unauthorized: invalid API key",
]


def make_trial(root, events=(), stderr=(), steps=(), exception=None):
    trial = os.path.join(root, "job", "task__x")
    os.makedirs(os.path.join(trial, "agent"))
    with open(os.path.join(trial, "agent", "opencode.txt"), "w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
        for line in stderr:
            f.write(line + "\n")
    with open(os.path.join(trial, "agent", "trajectory.json"), "w") as f:
        json.dump({"steps": [{"metrics": {"prompt_tokens": p}} for p in steps]}, f)
    with open(os.path.join(trial, "result.json"), "w") as f:
        json.dump({"exception_info": exception}, f)
    return trial


def api_error(message):
    """OpenCode's error event for a failed provider call (Vercel AI SDK APICallError)."""
    return {"type": "error", "timestamp": 1, "sessionID": "s",
            "error": {"name": "AI_APICallError", "data": {"message": message, "statusCode": 400,
                                                          "responseBody": json.dumps({"error": {"message": message}})}}}


class AfterRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_overflow_message_is_caught_as_error_event(self):
        for msg in OVERFLOW_MESSAGES:
            with self.subTest(msg=msg), tempfile.TemporaryDirectory() as d:
                r = cc.check_trial(make_trial(d, events=[api_error(msg)], steps=[9000, 31000]), 32768)
                self.assertEqual(r["context"], "overflow")
                self.assertEqual(r["peak_prompt_tokens"], 31000)

    def test_overflow_on_stderr_line(self):
        r = cc.check_trial(make_trial(self.root, stderr=["Error: " + OVERFLOW_MESSAGES[0]]))
        self.assertEqual(r["context"], "overflow")

    def test_overflow_kept_only_in_harbor_exception(self):
        exc = {"exception_type": "NonZeroAgentExitCodeError",
               "exception_message": "Command failed (exit 1): opencode run -- 'instruction'\nstdout: "
                                    + json.dumps(api_error(OVERFLOW_MESSAGES[1]), separators=(",", ":"))}
        r = cc.check_trial(make_trial(self.root, exception=exc))
        self.assertEqual(r["context"], "overflow")

    def test_other_errors_are_not_overflow(self):
        for msg in NOT_OVERFLOW:
            with self.subTest(msg=msg), tempfile.TemporaryDirectory() as d:
                r = cc.check_trial(make_trial(d, events=[api_error(msg)], steps=[9000]), 32768)
                self.assertEqual(r["context"], "ok")

    def test_agent_text_about_context_is_ignored(self):
        talk = {"type": "reasoning", "part": {"type": "reasoning",
                                              "text": "the maximum context length is exceeded if I keep observing"}}
        self.assertEqual(cc.check_trial(make_trial(self.root, events=[talk]))["context"], "ok")

    def test_instruction_inside_exception_is_ignored(self):
        exc = {"exception_message": "Command failed: opencode run -- 'Keep the prompt is too long warning in mind'"}
        self.assertEqual(cc.check_trial(make_trial(self.root, exception=exc))["context"], "ok")

    def test_near_limit(self):
        r = cc.check_trial(make_trial(self.root, steps=[9000, 30000]), 32768)
        self.assertEqual(r["context"], "near_limit")
        r = cc.check_trial(make_trial(os.path.join(self.root, "b"), steps=[9000, 20000]), 32768)
        self.assertEqual(r["context"], "ok")

    def test_trials_under_job_dir(self):
        trial = make_trial(self.root)
        self.assertEqual(cc.trials_under(os.path.join(self.root, "job")), [trial])
        self.assertEqual(cc.trials_under(trial), [trial])


class BeforeRun(unittest.TestCase):
    def test_judge(self):
        self.assertFalse(cc.judge_model({"context_length": 8192})[0])
        self.assertFalse(cc.judge_model({"context_length": 16384})[0])
        ok, msgs, ctx = cc.judge_model({"context_length": 32768, "features": {"tool_use": True}})
        self.assertTrue(ok)
        self.assertEqual(ctx, 32768)
        self.assertTrue(msgs)  # warns: below the largest prompts seen
        self.assertEqual(cc.judge_model({"context_length": 131072}), (True, [], 131072))
        self.assertFalse(cc.judge_model({"context_length": 131072, "features": {"tool_use": False}})[0])
        self.assertFalse(cc.judge_model({"context_length": 131072, "available_on_current_plan": False})[0])
        self.assertTrue(cc.judge_model({})[0])  # unknown window: allowed, checked after the run
        self.assertTrue(cc.judge_model({"context_length": 16384}, min_context=16000)[0])

    def test_preflight_against_a_fake_api(self):
        models = {"Qwen/Qwen3-8B": {"id": "Qwen/Qwen3-8B", "context_length": 16384, "features": {"tool_use": True}},
                  "Qwen/Big": {"id": "Qwen/Big", "context_length": 131072, "features": {"tool_use": True}}}

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                m = models.get(self.path.removeprefix("/v1/models/"))
                self.send_response(200 if m else 404)
                self.end_headers()
                self.wfile.write(json.dumps(m or {"error": "not found"}).encode())

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.addCleanup(srv.server_close)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_port}/v1"
        try:
            self.assertFalse(cc.preflight("featherless/Qwen/Qwen3-8B", "k", base=base)[0])
            self.assertEqual(cc.preflight("featherless/Qwen/Big", "k", base=base)[:2], (True, []))
            ok, msgs, _ = cc.preflight("featherless/Qwen/Nope", "k", base=base)
            self.assertFalse(ok)
            self.assertIn("404", msgs[0])
        finally:
            srv.shutdown()
        # unreachable API: a warning, not a stop
        self.assertTrue(cc.preflight("featherless/Qwen/Qwen3-8B", "k", base="http://127.0.0.1:9/v1")[0])


if __name__ == "__main__":
    unittest.main()
