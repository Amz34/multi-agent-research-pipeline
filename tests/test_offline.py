"""Offline verification suite for the multi-agent research pipeline.

Every test here runs with **no network access and no API key**, so CI can prove
the crashproof guarantees on each push rather than trusting the README:

* JSON extraction survives fenced / prose-wrapped / broken model output;
* the search leg degrades to "" / [] instead of raising;
* the LLM retry rail backs off on 5xx and gives up with a clear error;
* the coordinator caps the evaluator loop and never raises out of the API;
* the HTTP contract answers 200 / 400 / 500 exactly as documented;
* the deployment artifacts (systemd unit + deploy.sh) exist and render.

Run: python3 -m unittest discover -s tests -q
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from agents import llm, search  # noqa: E402
from agents.coordinator import run_pipeline_safe  # noqa: E402


# --------------------------------------------------------------------------
# fakes
# --------------------------------------------------------------------------
class _Resp:
    def __init__(self, status, payload=None, text="upstream error"):
        self.status_code = status
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class _Client:
    """Stand-in for httpx.Client that replays a scripted list of responses."""

    scripted = []
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, *args, **kwargs):
        _Client.calls += 1
        if _Client.scripted:
            return _Client.scripted.pop(0)
        return _Resp(500)


class _BoomDDGS:
    def __init__(self, *args, **kwargs):
        pass

    def text(self, *args, **kwargs):
        raise RuntimeError("search backend unreachable")


def _chat_with(responses, **kwargs):
    _Client.scripted = list(responses)
    _Client.calls = 0
    with mock.patch.object(llm, "API_KEY", "test-key"), \
         mock.patch.object(llm.httpx, "Client", _Client), \
         mock.patch.object(llm.time, "sleep", lambda *_: None):
        return llm.chat([{"role": "user", "content": "hello"}], **kwargs)


# --------------------------------------------------------------------------
# 1. model output parsing
# --------------------------------------------------------------------------
class TestExtractJson(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(llm.extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_block(self):
        out = '```json\n{"title": "t", "keyPoints": ["a"]}\n```'
        self.assertEqual(llm.extract_json(out)["title"], "t")

    def test_prose_wrapped_object(self):
        out = 'Sure! Here is the JSON:\n{"verdict": "APPROVED"}\nHope that helps.'
        self.assertEqual(llm.extract_json(out), {"verdict": "APPROVED"})

    def test_nested_object_is_preserved(self):
        out = '{"meta": {"kept": true}, "n": 2}'
        self.assertEqual(llm.extract_json(out)["meta"], {"kept": True})

    def test_empty_output_raises(self):
        with self.assertRaises(ValueError):
            llm.extract_json("")

    def test_output_without_json_raises(self):
        with self.assertRaises(ValueError):
            llm.extract_json("I could not answer that.")


# --------------------------------------------------------------------------
# 2. search leg degrades gracefully
# --------------------------------------------------------------------------
class TestSearchDegradation(unittest.TestCase):
    def test_strip_html_removes_scripts_styles_and_tags(self):
        raw = "<html><head><style>p{color:red}</style><script>var x=1;</script></head>" \
              "<body><p>Hello&nbsp;<b>world</b> &amp; friends</p></body></html>"
        text = search._strip_html(raw)
        self.assertIn("Hello", text)
        self.assertIn("world & friends", text)
        self.assertNotIn("var x", text)
        self.assertNotIn("color:red", text)
        self.assertNotIn("<b>", text)

    def test_strip_html_respects_limit(self):
        self.assertLessEqual(len(search._strip_html("<p>" + "x" * 5000 + "</p>", limit=100)), 100)

    def test_search_returns_empty_list_when_backend_fails(self):
        with mock.patch.object(search, "DDGS", _BoomDDGS), \
             mock.patch.object(search.time, "sleep", lambda *_: None):
            self.assertEqual(search.search("anything", retries=0), [])

    def test_fetch_page_returns_empty_string_on_failure(self):
        # port 9 (discard) is closed in CI; the call must degrade, not raise.
        self.assertEqual(search.fetch_page("http://127.0.0.1:9/", timeout=1.0), "")

    def test_research_notes_is_never_empty(self):
        with mock.patch.object(search, "search", lambda *a, **k: []):
            notes = search.research_notes("a topic with no results")
        self.assertIn("a topic with no results", notes)


# --------------------------------------------------------------------------
# 3. the LLM rail
# --------------------------------------------------------------------------
class TestLlmRail(unittest.TestCase):
    def test_missing_api_key_gives_actionable_error(self):
        with mock.patch.object(llm, "API_KEY", ""):
            with self.assertRaises(llm.LLMError) as ctx:
                llm.chat([{"role": "user", "content": "hi"}])
        self.assertIn("DEEPSEEK_API_KEY", str(ctx.exception))

    def test_successful_call_returns_content(self):
        payload = {"choices": [{"message": {"content": "  grounded answer  "}}]}
        self.assertEqual(_chat_with([_Resp(200, payload)]), "grounded answer")

    def test_empty_content_falls_back_to_reasoning_content(self):
        payload = {"choices": [{"message": {"content": "", "reasoning_content": "thought"}}]}
        self.assertEqual(_chat_with([_Resp(200, payload)]), "thought")

    def test_retries_exhausted_on_repeated_5xx(self):
        with self.assertRaises(llm.LLMError) as ctx:
            _chat_with([_Resp(503), _Resp(503)], retries=1)
        self.assertIn("retries exhausted", str(ctx.exception))
        self.assertEqual(_Client.calls, 2, "one initial attempt plus one retry")

    def test_permanent_error_is_not_retried(self):
        with self.assertRaises(llm.LLMError) as ctx:
            _chat_with([_Resp(401, text="bad key")], retries=3)
        self.assertIn("401", str(ctx.exception))
        self.assertEqual(_Client.calls, 1, "a 4xx must fail fast, not burn retries")


# --------------------------------------------------------------------------
# 4. coordinator: retry cap + never-raising entry point
# --------------------------------------------------------------------------
class TestCoordinator(unittest.TestCase):
    def _patch(self, verdict, calls):
        def fake_summarize(notes):
            calls.append("summarize")
            return {"title": "t", "keyPoints": ["a", "b", "c"], "takeaway": "k"}

        def fake_evaluate(notes, summary):
            calls.append("evaluate")
            return verdict

        return mock.patch.multiple(
            "agents.coordinator",
            research=lambda topic: "notes",
            summarize=fake_summarize,
            evaluate=fake_evaluate,
        )

    def test_approved_on_first_pass_runs_one_iteration(self):
        calls = []
        with self._patch("APPROVED", calls):
            from agents.coordinator import run_pipeline
            result = run_pipeline("topic")
        self.assertEqual(result["iterations"], 1)
        self.assertEqual(result["verdict"], "APPROVED")
        self.assertEqual(calls.count("summarize"), 1)

    def test_revise_loop_is_capped_at_max_iterations(self):
        calls = []
        with self._patch("REVISE", calls):
            from agents.coordinator import run_pipeline
            result = run_pipeline("topic", max_iterations=3)
        self.assertEqual(result["iterations"], 3)
        self.assertEqual(result["verdict"], "REVISE")
        self.assertEqual(calls.count("summarize"), 3, "the evaluator must not loop forever")

    def test_safe_entry_point_never_raises(self):
        with mock.patch("agents.coordinator.research", side_effect=RuntimeError("search exploded")):
            result = run_pipeline_safe("topic")
        self.assertEqual(result["status"], "error")
        self.assertIn("search exploded", result["error"])
        self.assertEqual(result["topic"], "topic")

    def test_safe_entry_point_maps_success(self):
        with mock.patch("agents.coordinator.run_pipeline",
                        return_value={"topic": "t", "summary": {}, "iterations": 1, "verdict": "APPROVED"}):
            result = run_pipeline_safe("t")
        self.assertEqual(result["status"], "ok")


# --------------------------------------------------------------------------
# 5. HTTP contract
# --------------------------------------------------------------------------
class TestHttpApi(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})

    def test_index_lists_endpoints(self):
        body = self.client.get("/").get_json()
        self.assertIn("POST /run", body["endpoints"])

    def test_run_rejects_missing_topic(self):
        resp = self.client.post("/run", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"], "topic is required")

    def test_run_rejects_non_json_body(self):
        resp = self.client.post("/run", data="not json", content_type="text/plain")
        self.assertEqual(resp.status_code, 400)

    def test_run_rejects_overlong_topic(self):
        resp = self.client.post("/run", json={"topic": "x" * (server.MAX_TOPIC_LEN + 1)})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("too long", resp.get_json()["error"])

    def test_run_accepts_topic_at_the_limit(self):
        payload = {"status": "ok", "topic": "t" * server.MAX_TOPIC_LEN, "summary": {}, "iterations": 1}
        with mock.patch.object(server, "run_pipeline_safe", return_value=payload):
            resp = self.client.post("/run", json={"topic": "t" * server.MAX_TOPIC_LEN})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")

    def test_pipeline_failure_becomes_500_not_a_traceback(self):
        with mock.patch.object(server, "run_pipeline_safe",
                               return_value={"status": "error", "topic": "t", "error": "boom"}):
            resp = self.client.post("/run", json={"topic": "t"})
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_json()["error"], "boom")

    def test_topic_is_whitespace_stripped(self):
        seen = {}

        def fake(topic, *a, **k):
            seen["topic"] = topic
            return {"status": "ok", "topic": topic}

        with mock.patch.object(server, "run_pipeline_safe", fake):
            self.client.post("/run", json={"topic": "  spaced topic  "})
        self.assertEqual(seen["topic"], "spaced topic")


# --------------------------------------------------------------------------
# 6. deployment artifacts
# --------------------------------------------------------------------------
def _run_deploy(*args):
    return subprocess.run(["bash", str(ROOT / "deploy.sh"), *args],
                          capture_output=True, text=True, timeout=60)


class TestDeploymentArtifacts(unittest.TestCase):
    def test_unit_template_exists_and_is_crashproof(self):
        unit = (ROOT / "systemd" / "multi-agent-research.service").read_text(encoding="utf-8")
        self.assertIn("Restart=always", unit)
        self.assertIn("RestartSec=", unit)
        self.assertIn("MemoryMax=", unit)
        self.assertIn("ExecStart=@REPO_DIR@/.venv/bin/python", unit)

    def test_deploy_script_is_executable(self):
        self.assertTrue(os.access(ROOT / "deploy.sh", os.X_OK),
                        "deploy.sh must be committed with the executable bit set")

    def test_deploy_script_syntax_is_valid(self):
        proc = subprocess.run(["bash", "-n", str(ROOT / "deploy.sh")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_dry_run_renders_a_complete_unit(self):
        proc = _run_deploy("--dry-run", "--port", "18088")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Restart=always", proc.stdout)
        self.assertNotIn("@REPO_DIR@", proc.stdout, "placeholders must be substituted")
        self.assertNotIn("@RUN_USER@", proc.stdout)
        self.assertIn(str(ROOT), proc.stdout)

    def test_help_and_bad_flag_exit_codes(self):
        self.assertEqual(_run_deploy("--help").returncode, 0)
        self.assertEqual(_run_deploy("--nonsense").returncode, 2)

    def test_readme_documents_the_deploy_path(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("deploy.sh", readme)
        self.assertTrue((ROOT / "deploy.sh").exists())


# --------------------------------------------------------------------------
# 7. repo hygiene
# --------------------------------------------------------------------------
class TestRepoHygiene(unittest.TestCase):
    def test_requirements_cover_every_third_party_import(self):
        reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        for dep in ("ddgs", "httpx", "flask", "python-dotenv"):
            self.assertIn(dep, reqs)

    def test_gitignore_blocks_secrets_and_venv(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for entry in (".env", ".venv", "logs/"):
            self.assertIn(entry, ignored)

    def test_no_tracked_env_file(self):
        proc = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            self.skipTest("not a git working tree")
        tracked = proc.stdout.split()
        self.assertNotIn(".env", tracked)
        self.assertFalse([f for f in tracked if f.endswith(".env") and f != ".env.example"])

    def test_no_obvious_secrets_in_tracked_text_files(self):
        proc = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        if proc.returncode != 0:
            self.skipTest("not a git working tree")
        pattern = re.compile(r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,})")
        offenders = []
        for name in proc.stdout.split():
            if not name.endswith((".py", ".md", ".yml", ".yaml", ".txt", ".sh", ".example", ".json")):
                continue
            text = (ROOT / name).read_text(encoding="utf-8", errors="ignore")
            if pattern.search(text):
                offenders.append(name)
        self.assertEqual(offenders, [], f"possible secrets tracked in: {offenders}")

    def test_cli_imports_and_has_a_main(self):
        proc = subprocess.run([sys.executable, str(ROOT / "cli.py"), "--help"],
                              cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("topic", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
