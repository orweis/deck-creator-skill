"""Tests for ask_user_clone_gpt.py. All HTTP is faked; no real API calls."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import urllib.error
from email.message import Message

import pytest
from conftest import CLONE_SKILL, REPO_ROOT

SCRIPT = CLONE_SKILL / "scripts" / "ask_user_clone_gpt.py"
FAKE_KEY = "sk-test-not-a-real-key"


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload):
        self._raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body=b"", headers=None):
    msg = Message()
    for k, v in (headers or {}).items():
        msg[k] = v
    return urllib.error.HTTPError("https://api.openai.com/v1/x", code, "err", msg, io.BytesIO(body))


class FakeOpener:
    """Returns queued results in order and records every request."""

    def __init__(self, *results):
        self.results = list(results)
        self.requests = []

    def __call__(self, req, timeout=None):
        body = json.loads(req.data) if req.data else None
        self.requests.append(
            {"method": req.get_method(), "url": req.full_url, "body": body, "headers": dict(req.headers)}
        )
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return FakeResponse(result)


def make_client(mod, *results):
    opener = FakeOpener(*results)
    sleeps = []
    client = mod.OpenAIClient(FAKE_KEY, opener=opener, sleep=sleeps.append)
    return client, opener, sleeps


def completed(text="Hello", rid="resp_123"):
    return {
        "id": rid,
        "status": "completed",
        "output": [
            {"type": "file_search_call", "id": "fs_1"},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]},
        ],
    }


# --------------------------------------------------------------------------
# .env parsing and project root
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("KEY=value", ("KEY", "value")),
        ("export KEY=value", ("KEY", "value")),
        ("  KEY = value  ", ("KEY", "value")),
        ("KEY='quoted # not a comment'", ("KEY", "quoted # not a comment")),
        ('KEY="double"  # trailing comment', ("KEY", "double")),
        ("KEY=value # comment", ("KEY", "value")),
        ("KEY=sk-abc#def", ("KEY", "sk-abc#def")),
        ("KEY=", ("KEY", "")),
        ("KEY=a=b", ("KEY", "a=b")),
        ("# comment", None),
        ("", None),
        ("no_equals_sign", None),
        ("1BAD=x", None),
        ("BAD KEY=x", None),
    ],
)
def test_parse_env_line(clone_mod, line, expected):
    assert clone_mod.parse_env_line(line) == expected


def test_load_env_does_not_override_existing(clone_mod, tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("OPENAI_MODEL=from-file\nexport OPENAI_X_TEST=1\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_MODEL", "from-env")
    monkeypatch.delenv("OPENAI_X_TEST", raising=False)
    clone_mod.load_env(env)
    import os

    assert os.environ["OPENAI_MODEL"] == "from-env"
    assert os.environ["OPENAI_X_TEST"] == "1"


def test_load_env_missing_file_is_noop(clone_mod, tmp_path):
    clone_mod.load_env(tmp_path / "nope.env")


def test_project_root_is_repo_root(clone_mod):
    assert clone_mod.find_project_root() == REPO_ROOT


def test_project_root_does_not_escape_to_parent_env(clone_mod, tmp_path):
    """A .env above the project must never be picked up."""
    (tmp_path / ".env").write_text("OPENAI_API_KEY=parent-secret\n")
    project = tmp_path / "proj"
    script = project / ".agents" / "skills" / "user-clone-gpt" / "scripts" / "x.py"
    script.parent.mkdir(parents=True)
    script.write_text("")
    assert clone_mod.find_project_root(script) == project


def test_env_path_honours_override(clone_mod, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_ENV_FILE", str(tmp_path / "custom.env"))
    assert clone_mod.env_path() == tmp_path / "custom.env"


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def test_config_requires_api_key(clone_mod, clean_openai_env):
    with pytest.raises(clone_mod.ConfigError, match="OPENAI_API_KEY"):
        clone_mod.load_config()


def test_config_requires_a_voice(clone_mod, clean_openai_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    with pytest.raises(clone_mod.ConfigError, match="No voice configured"):
        clone_mod.load_config()


def test_config_legacy_assistant_id_gets_migration_hint(clone_mod, clean_openai_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_ASSISTANT_ID", "asst_abc")
    with pytest.raises(clone_mod.ConfigError, match="Assistants API was shut down"):
        clone_mod.load_config()


def test_config_full(clone_mod, clean_openai_env, monkeypatch, tmp_path):
    instructions = tmp_path / "voice.md"
    instructions.write_text("  Be concise.  \n")
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_INSTRUCTIONS_FILE", str(instructions))
    monkeypatch.setenv("OPENAI_VECTOR_STORE_IDS", "vs_a, vs_b,,")
    monkeypatch.setenv("OPENAI_PROMPT_ID", "pmpt_1")
    monkeypatch.setenv("OPENAI_PROMPT_VERSION", "3")
    monkeypatch.setenv("OPENAI_MODEL", "my-model")
    cfg = clone_mod.load_config()
    assert cfg.instructions == "Be concise."
    assert cfg.vector_store_ids == ["vs_a", "vs_b"]
    assert cfg.model == "my-model"
    assert clone_mod.load_config("override").model == "override"
    desc = cfg.describe()
    assert FAKE_KEY not in json.dumps(desc)
    assert desc["instructions_chars"] == len("Be concise.")


def test_config_default_model(clone_mod, clean_openai_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_VECTOR_STORE_IDS", "vs_a")
    assert clone_mod.load_config().model == clone_mod.DEFAULT_MODEL


def test_config_relative_instructions_resolve_from_project_root(clone_mod, clean_openai_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_INSTRUCTIONS_FILE", "README.md")
    assert clone_mod.load_config().instructions.startswith("# Deck Creator")


def test_config_missing_instructions_file(clone_mod, clean_openai_env, monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_INSTRUCTIONS_FILE", str(tmp_path / "missing.md"))
    with pytest.raises(clone_mod.ConfigError, match="not found"):
        clone_mod.load_config()


@pytest.mark.parametrize("bad", ["vs_../../assistants", "asst_123", "vs_a?x=1", "vs_a/b"])
def test_config_rejects_bad_vector_store_ids(clone_mod, clean_openai_env, monkeypatch, bad):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_VECTOR_STORE_IDS", bad)
    with pytest.raises(clone_mod.ConfigError, match="vector store ID"):
        clone_mod.load_config()


@pytest.mark.parametrize(
    ("raw", "ok"), [("", True), ("12", True), ("0", False), ("-3", False), ("abc", False)]
)
def test_env_int(clone_mod, monkeypatch, raw, ok):
    monkeypatch.setenv("OPENAI_RUN_TIMEOUT", raw)
    if ok:
        assert clone_mod.env_int("OPENAI_RUN_TIMEOUT", 300) == (int(raw) if raw else 300)
    else:
        with pytest.raises(clone_mod.ConfigError):
            clone_mod.env_int("OPENAI_RUN_TIMEOUT", 300)


# --------------------------------------------------------------------------
# HTTP client
# --------------------------------------------------------------------------


def test_client_sends_auth_and_json(clone_mod):
    client, opener, _ = make_client(clone_mod, {"ok": True})
    assert client.request("POST", "/responses", {"a": 1}) == {"ok": True}
    req = opener.requests[0]
    assert req["url"] == "https://api.openai.com/v1/responses"
    assert req["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert req["body"] == {"a": 1}
    assert "Openai-beta" not in req["headers"]


def test_client_rejects_non_https_base(clone_mod):
    with pytest.raises(clone_mod.ConfigError):
        clone_mod.OpenAIClient(FAKE_KEY, base_url="http://example.com")


def test_client_retries_429_for_post_and_honours_retry_after(clone_mod):
    client, opener, sleeps = make_client(clone_mod, http_error(429, headers={"Retry-After": "7"}), {"ok": 1})
    assert client.request("POST", "/responses", {}) == {"ok": 1}
    assert sleeps == [7.0]
    assert len(opener.requests) == 2


def test_client_does_not_retry_5xx_for_post(clone_mod):
    client, opener, sleeps = make_client(clone_mod, http_error(500, b'{"error":{"message":"boom"}}'))
    with pytest.raises(clone_mod.OpenAIError, match="500: boom"):
        client.request("POST", "/responses", {})
    assert sleeps == []


def test_client_retries_5xx_and_network_errors_for_get_with_backoff(clone_mod):
    client, opener, sleeps = make_client(
        clone_mod, http_error(503), urllib.error.URLError("reset"), TimeoutError(), {"ok": 1}
    )
    assert client.request("GET", "/responses/resp_1") == {"ok": 1}
    assert sleeps == [1.0, 2.0, 4.0]


def test_client_gives_up_after_max_retries(clone_mod):
    errors = [http_error(429) for _ in range(clone_mod.MAX_RETRIES + 1)]
    client, opener, sleeps = make_client(clone_mod, *errors)
    with pytest.raises(clone_mod.OpenAIError, match="429"):
        client.request("POST", "/responses", {})
    assert len(sleeps) == clone_mod.MAX_RETRIES


def test_client_network_error_on_post_is_not_retried(clone_mod):
    client, _, sleeps = make_client(clone_mod, urllib.error.URLError("dns"))
    with pytest.raises(clone_mod.OpenAIError, match="Network error.*dns"):
        client.request("POST", "/responses", {})
    assert sleeps == []


def test_client_truncates_and_summarizes_error_body(clone_mod):
    big = b"x" * 5000
    client, _, _ = make_client(clone_mod, http_error(400, big))
    with pytest.raises(clone_mod.OpenAIError) as info:
        client.request("POST", "/responses", {})
    assert len(str(info.value)) < clone_mod.MAX_ERROR_BODY_CHARS + 50
    assert FAKE_KEY not in str(info.value)


def test_client_invalid_json(clone_mod):
    client, _, _ = make_client(clone_mod, b"<html>")
    with pytest.raises(clone_mod.OpenAIError, match="invalid JSON"):
        client.request("GET", "/x")


# --------------------------------------------------------------------------
# Responses API helpers
# --------------------------------------------------------------------------


def make_config(clone_mod, **kw):
    base = {"api_key": FAKE_KEY, "model": "m", "instructions": "voice"}
    base.update(kw)
    return clone_mod.Config(**base)


def test_build_request_body_minimal(clone_mod):
    body = clone_mod.build_request_body(make_config(clone_mod), "hi")
    assert body == {"model": "m", "input": "hi", "store": True, "background": True, "instructions": "voice"}


def test_build_request_body_full(clone_mod):
    cfg = make_config(
        clone_mod, instructions=None, vector_store_ids=["vs_1"], prompt_id="pmpt_1", prompt_version="2"
    )
    body = clone_mod.build_request_body(cfg, "hi", previous_response_id="resp_9")
    assert "instructions" not in body
    assert body["tools"] == [{"type": "file_search", "vector_store_ids": ["vs_1"]}]
    assert body["prompt"] == {"id": "pmpt_1", "version": "2"}
    assert body["previous_response_id"] == "resp_9"


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_wait_for_response_polls_until_done(clone_mod):
    client, opener, _ = make_client(clone_mod, {"id": "resp_1", "status": "in_progress"}, completed())
    clock = FakeClock()
    result = clone_mod.wait_for_response(
        client, {"id": "resp_1", "status": "queued"}, timeout_sec=60, clock=clock, sleep=clock.sleep
    )
    assert result["status"] == "completed"
    assert [r["url"] for r in opener.requests] == ["https://api.openai.com/v1/responses/resp_1"] * 2


def test_wait_for_response_returns_immediately_when_done(clone_mod):
    client, opener, _ = make_client(clone_mod)
    assert clone_mod.wait_for_response(client, completed(), timeout_sec=1)["status"] == "completed"
    assert opener.requests == []


def test_wait_for_response_times_out(clone_mod):
    pending = {"id": "resp_1", "status": "in_progress"}
    client, _, _ = make_client(clone_mod, *[pending] * 10)
    clock = FakeClock()
    with pytest.raises(TimeoutError, match="5s"):
        clone_mod.wait_for_response(
            client, pending, timeout_sec=5, poll_interval=2, clock=clock, sleep=clock.sleep
        )


def test_wait_for_response_rejects_unsafe_id(clone_mod):
    client, _, _ = make_client(clone_mod)
    with pytest.raises(clone_mod.ConfigError):
        clone_mod.wait_for_response(
            client, {"id": "../files", "status": "queued"}, timeout_sec=5, sleep=lambda s: None
        )


def test_extract_output_text_joins_message_parts(clone_mod):
    resp = completed("A")
    resp["output"].append(
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "B"}]}
    )
    assert clone_mod.extract_output_text(resp) == "A\nB"


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_extract_output_text_failure(clone_mod, status):
    with pytest.raises(clone_mod.OpenAIError, match=f"{status}: bad"):
        clone_mod.extract_output_text({"status": status, "error": {"message": "bad"}})


def test_extract_output_text_no_text(clone_mod):
    with pytest.raises(clone_mod.OpenAIError, match="No assistant text"):
        clone_mod.extract_output_text({"status": "completed", "output": [{"type": "reasoning"}]})


def test_extract_output_text_incomplete_warns(clone_mod, capsys):
    resp = completed("partial")
    resp["status"] = "incomplete"
    resp["incomplete_details"] = {"reason": "max_output_tokens"}
    assert clone_mod.extract_output_text(resp) == "partial"
    assert "max_output_tokens" in capsys.readouterr().err


def test_cancel_failure_is_only_a_warning(clone_mod, capsys):
    client, _, _ = make_client(clone_mod, http_error(404, b'{"error":{"message":"gone"}}'))
    clone_mod.cancel_response(client, "resp_1")
    assert "could not cancel" in capsys.readouterr().err


def test_ask_end_to_end(clone_mod):
    client, opener, _ = make_client(
        clone_mod, {"id": "resp_7", "status": "queued"}, completed("Deck!", "resp_7")
    )
    reply, rid = clone_mod.ask(client, make_config(clone_mod), "prompt", sleep=lambda s: None)
    assert (reply, rid) == ("Deck!", "resp_7")
    assert opener.requests[0]["method"] == "POST"
    assert opener.requests[0]["body"]["input"] == "prompt"


# --------------------------------------------------------------------------
# Prompt input
# --------------------------------------------------------------------------


def test_read_prompt_arg_text_and_file(clone_mod, tmp_path, capsys):
    f = tmp_path / "p.md"
    f.write_text("from file")
    assert clone_mod.read_prompt_arg(str(f)) == "from file"
    assert "reading prompt from file" in capsys.readouterr().err
    assert clone_mod.read_prompt_arg("just text") == "just text"
    assert clone_mod.read_prompt_arg("x" * 10000) == "x" * 10000


@pytest.mark.parametrize("name", [".env", ".env.local", "id.pem", "server.key"])
def test_read_prompt_refuses_secret_files(clone_mod, tmp_path, name):
    f = tmp_path / name
    f.write_text("OPENAI_API_KEY=secret")
    with pytest.raises(clone_mod.ConfigError, match="secrets file"):
        clone_mod.read_prompt_arg(str(f))


def test_read_prompt_file_limits(clone_mod, tmp_path, monkeypatch):
    with pytest.raises(clone_mod.ConfigError, match="not found"):
        clone_mod.read_prompt_file(str(tmp_path / "missing"))
    big = tmp_path / "big.md"
    big.write_bytes(b"x" * (clone_mod.MAX_PROMPT_FILE_BYTES + 1))
    with pytest.raises(clone_mod.ConfigError, match="larger"):
        clone_mod.read_prompt_file(str(big))
    monkeypatch.setattr("sys.stdin", io.StringIO("stdin prompt"))
    assert clone_mod.read_prompt_file("-") == "stdin prompt"


# --------------------------------------------------------------------------
# main()
# --------------------------------------------------------------------------


@pytest.fixture
def configured(clean_openai_env, monkeypatch, tmp_path):
    voice = tmp_path / "voice.md"
    voice.write_text("Write like me.")
    clean_openai_env.write_text(
        f"OPENAI_API_KEY={FAKE_KEY}\nOPENAI_INSTRUCTIONS_FILE={voice}\nOPENAI_MODEL=test-model\n"
    )
    return clean_openai_env


def factory_for(clone_mod, *results):
    opener = FakeOpener(*results)

    def factory(api_key):
        return clone_mod.OpenAIClient(api_key, opener=opener, sleep=lambda s: None)

    factory.opener = opener
    return factory


def test_main_writes_output_file(clone_mod, configured, tmp_path, capsys):
    factory = factory_for(clone_mod, completed("Layout", "resp_42"))
    out = tmp_path / "nested" / "dir" / "out.md"
    assert clone_mod.main(["Make a deck", "-o", str(out)], client_factory=factory) == 0
    assert out.read_text() == "Layout\n"
    err = capsys.readouterr().err
    assert "[response_id=resp_42]" in err
    body = factory.opener.requests[0]["body"]
    assert body["model"] == "test-model"
    assert body["instructions"] == "Write like me."


def test_main_prints_to_stdout_and_supports_follow_up(clone_mod, configured, capsys):
    factory = factory_for(clone_mod, completed("Short"))
    rc = clone_mod.main(["Tighten", "--thread-id", "resp_prev", "--model", "other"], client_factory=factory)
    assert rc == 0
    assert capsys.readouterr().out == "Short\n"
    body = factory.opener.requests[0]["body"]
    assert body["previous_response_id"] == "resp_prev"
    assert body["model"] == "other"


def test_main_prompt_file(clone_mod, configured, tmp_path):
    p = tmp_path / "prompt.md"
    p.write_text("file prompt")
    factory = factory_for(clone_mod, completed())
    assert clone_mod.main(["--prompt-file", str(p)], client_factory=factory) == 0
    assert factory.opener.requests[0]["body"]["input"] == "file prompt"


@pytest.mark.parametrize(
    ("argv", "rc", "message"),
    [
        ([], 2, "Provide a prompt"),
        (["a", "--prompt-file", "b"], 2, "not both"),
        (["   "], 2, "empty"),
        (["x", "--thread-id", "thread_abc"], 1, "resp_"),
        (["x", "--timeout", "0"], 1, "positive"),
    ],
)
def test_main_usage_errors(clone_mod, configured, capsys, argv, rc, message):
    factory = factory_for(clone_mod)
    assert clone_mod.main(argv, client_factory=factory) == rc
    assert message in capsys.readouterr().err
    assert factory.opener.requests == []


def test_main_bad_timeout_env(clone_mod, configured, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_RUN_TIMEOUT", "ten")
    assert clone_mod.main(["x"]) == 1
    assert "OPENAI_RUN_TIMEOUT" in capsys.readouterr().err


def test_main_missing_key(clone_mod, clean_openai_env, capsys):
    assert clone_mod.main(["x"]) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().err


def test_main_info_never_prints_key(clone_mod, configured, capsys):
    assert clone_mod.main(["--info"]) == 0
    out = capsys.readouterr().out
    assert FAKE_KEY not in out
    assert json.loads(out)["model"] == "test-model"


def test_main_ensure_model_only_is_offline(clone_mod, configured, capsys):
    assert clone_mod.main(["--ensure-model-only", "--skip-model-check"]) == 0
    assert "test-model" in capsys.readouterr().err


def test_main_api_error_is_reported_cleanly(clone_mod, configured, capsys):
    factory = factory_for(clone_mod, http_error(401, b'{"error":{"message":"Incorrect API key"}}'))
    assert clone_mod.main(["x"], client_factory=factory) == 1
    err = capsys.readouterr().err
    assert "401" in err and "Incorrect API key" in err
    assert "Traceback" not in err


def test_main_timeout_is_reported_and_cancels(clone_mod, configured, capsys, monkeypatch):
    pending = {"id": "resp_1", "status": "in_progress"}
    factory = factory_for(clone_mod, pending, pending, pending, {"id": "resp_1", "status": "cancelled"})
    clock = FakeClock()
    monkeypatch.setattr(clone_mod.time, "monotonic", clock)
    monkeypatch.setattr(clone_mod.time, "sleep", clock.sleep)
    assert clone_mod.main(["x", "--timeout", "3"], client_factory=factory) == 1
    err = capsys.readouterr().err
    assert "did not complete within 3s" in err
    assert "[cancelled] resp_1" in err
    assert clock.now >= 3
    last = factory.opener.requests[-1]
    assert (last["method"], last["url"]) == ("POST", "https://api.openai.com/v1/responses/resp_1/cancel")


# --------------------------------------------------------------------------
# Process-level smoke tests (no network: these exit before any API call)
# --------------------------------------------------------------------------


def run_cli(*args, env_file):
    env = {"PATH": "/usr/bin:/bin", "OPENAI_ENV_FILE": str(env_file)}
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, env=env, timeout=30, check=False
    )


def test_cli_version_and_help(tmp_path):
    env_file = tmp_path / "e.env"
    env_file.write_text("")
    r = run_cli(str(SCRIPT), "--version", env_file=env_file)
    assert r.returncode == 0 and "2.0.0" in r.stdout
    r = run_cli(str(SCRIPT), "--help", env_file=env_file)
    assert r.returncode == 0 and "--prompt-file" in r.stdout


def test_back_compat_shim_delegates(tmp_path):
    env_file = tmp_path / "e.env"
    env_file.write_text("")
    r = run_cli(str(REPO_ROOT / "scripts" / "openai_assistant.py"), "--version", env_file=env_file)
    assert r.returncode == 0 and "2.0.0" in r.stdout


def test_cli_missing_key_exit_code(tmp_path):
    env_file = tmp_path / "e.env"
    env_file.write_text("")
    r = run_cli(str(SCRIPT), "hello", env_file=env_file)
    assert r.returncode == 1
    assert "OPENAI_API_KEY is not set" in r.stderr
