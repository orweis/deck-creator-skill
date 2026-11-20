#!/usr/bin/env python3
"""Generate content in your cloned voice with the OpenAI Responses API.

User-Clone-GPT is your configured voice: system instructions, an optional
file-search knowledge base (vector store), and/or a reusable dashboard prompt.
Configuration is read from the environment and from the project's ``.env``:

  OPENAI_API_KEY            required
  OPENAI_MODEL              model to run (default: gpt-5.5)
  OPENAI_INSTRUCTIONS_FILE  path to a text/markdown file with the system prompt
  OPENAI_VECTOR_STORE_IDS   comma-separated vector store IDs for file_search
  OPENAI_PROMPT_ID          reusable prompt ID (optional, pmpt_...)
  OPENAI_PROMPT_VERSION     reusable prompt version (optional)
  OPENAI_RUN_TIMEOUT        max seconds to wait for a response (default: 300)
  OPENAI_ENV_FILE           explicit .env path (default: <project root>/.env)

At least one of OPENAI_INSTRUCTIONS_FILE, OPENAI_VECTOR_STORE_IDS or
OPENAI_PROMPT_ID must be set, otherwise the output would not be in your voice.

Only the Python standard library is used. Version 1.x of this script used the
OpenAI Assistants API, which OpenAI shut down on 2026-08-26; see the CHANGELOG
for the migration steps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

__version__ = "2.0.0"

API_BASE = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.5"
DEFAULT_RUN_TIMEOUT_SEC = 300
POLL_INTERVAL_SEC = 2.0
REQUEST_TIMEOUT_SEC = 60
MAX_RETRIES = 4
RETRY_BASE_DELAY_SEC = 1.0
MAX_ERROR_BODY_CHARS = 500
MAX_PROMPT_FILE_BYTES = 1_000_000

RETRYABLE_ANY_METHOD = {429}
RETRYABLE_IDEMPOTENT = {500, 502, 503, 504}
TERMINAL_FAILURE_STATUSES = {"failed", "cancelled"}
PENDING_STATUSES = {"queued", "in_progress"}

# IDs end up in URL paths; reject anything that could change the endpoint.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

MIGRATION_HINT = (
    "The OpenAI Assistants API was shut down on 2026-08-26, so OPENAI_ASSISTANT_ID "
    "is no longer used. Copy your assistant's instructions into a file and set "
    "OPENAI_INSTRUCTIONS_FILE, and/or set OPENAI_VECTOR_STORE_IDS to the vector "
    "store(s) that held its knowledge, and/or set OPENAI_PROMPT_ID. "
    "See the user-clone-gpt SKILL.md and CHANGELOG.md."
)


class ConfigError(RuntimeError):
    """Raised for missing or invalid local configuration."""


class OpenAIError(RuntimeError):
    """Raised when the OpenAI API returns an error or an unusable response."""


# --------------------------------------------------------------------------
# Environment / configuration
# --------------------------------------------------------------------------


def find_project_root(start: Path | None = None) -> Path:
    """Return the repository root that contains this skill.

    Walks up from the script and stops at the first directory that contains
    ``.agents`` or ``.git``. The search never goes above that directory, so a
    ``.env`` in an unrelated parent directory (for example ``$HOME``) is never
    loaded by accident.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        if (candidate / ".agents").is_dir() or (candidate / ".git").exists():
            return candidate
    # Layout: <root>/.agents/skills/user-clone-gpt/scripts/<this file>
    parents = here.parents
    return parents[min(4, len(parents) - 1)]


def parse_env_line(line: str) -> tuple[str, str] | None:
    """Parse one ``.env`` line into (key, value); return None for non-assignments.

    Supports ``export KEY=value``, single/double quoted values, and trailing
    ``# comments`` on unquoted values.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].lstrip()
    key, sep, value = line.partition("=")
    key = key.strip()
    if not sep or not key or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return None
    value = value.strip()
    if value[:1] in {"'", '"'}:
        quote = value[0]
        end = value.find(quote, 1)
        value = value[1:end] if end != -1 else value[1:]
    else:
        comment = re.search(r"\s+#", value)
        if comment:
            value = value[: comment.start()]
        value = value.strip()
    return key, value


def load_env(path: Path) -> None:
    """Load ``path`` into ``os.environ`` without overriding existing variables."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        parsed = parse_env_line(raw)
        if parsed:
            os.environ.setdefault(*parsed)


def env_path() -> Path:
    explicit = os.environ.get("OPENAI_ENV_FILE", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return find_project_root() / ".env"


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
    if value <= 0:
        raise ConfigError(f"{name} must be positive, got {value}")
    return value


def validate_id(value: str, *, label: str, prefix: str | None = None) -> str:
    value = value.strip()
    if not _ID_RE.fullmatch(value):
        raise ConfigError(f"Invalid {label}: {value!r}")
    if prefix and not value.startswith(prefix):
        raise ConfigError(f"Invalid {label}: {value!r} (expected an ID starting with {prefix!r})")
    return value


def split_ids(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass
class Config:
    api_key: str
    model: str
    instructions: str | None = None
    vector_store_ids: list[str] = field(default_factory=list)
    prompt_id: str | None = None
    prompt_version: str | None = None

    @property
    def has_voice(self) -> bool:
        return bool(self.instructions or self.vector_store_ids or self.prompt_id)

    def describe(self) -> dict[str, Any]:
        """Non-secret summary of the configuration (safe to print)."""
        return {
            "api": "responses",
            "model": self.model,
            "instructions_chars": len(self.instructions or ""),
            "vector_store_ids": self.vector_store_ids,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "script_version": __version__,
        }


def load_config(model_override: str | None = None) -> Config:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ConfigError("OPENAI_API_KEY is not set. Add it to .env in the project root.")

    model = (model_override or os.environ.get("OPENAI_MODEL", "") or DEFAULT_MODEL).strip()

    instructions = None
    instructions_file = os.environ.get("OPENAI_INSTRUCTIONS_FILE", "").strip()
    if instructions_file:
        path = Path(instructions_file).expanduser()
        if not path.is_absolute():
            path = find_project_root() / path
        if not path.is_file():
            raise ConfigError(f"OPENAI_INSTRUCTIONS_FILE not found: {path}")
        instructions = path.read_text(encoding="utf-8").strip() or None

    vector_store_ids = [
        validate_id(v, label="vector store ID", prefix="vs_")
        for v in split_ids(os.environ.get("OPENAI_VECTOR_STORE_IDS", ""))
    ]

    prompt_id = os.environ.get("OPENAI_PROMPT_ID", "").strip() or None
    if prompt_id:
        prompt_id = validate_id(prompt_id, label="OPENAI_PROMPT_ID")
    prompt_version = os.environ.get("OPENAI_PROMPT_VERSION", "").strip() or None

    config = Config(
        api_key=api_key,
        model=model,
        instructions=instructions,
        vector_store_ids=vector_store_ids,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
    )
    if not config.has_voice:
        if os.environ.get("OPENAI_ASSISTANT_ID", "").strip():
            raise ConfigError(MIGRATION_HINT)
        raise ConfigError(
            "No voice configured. Set OPENAI_INSTRUCTIONS_FILE, OPENAI_VECTOR_STORE_IDS "
            "and/or OPENAI_PROMPT_ID in .env (see .env.example)."
        )
    return config


# --------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------


def _summarize_error_body(body: str) -> str:
    """Return the API error message (not the raw body), truncated."""
    try:
        data = json.loads(body)
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            parts = [str(err.get(k)) for k in ("type", "code", "message") if err.get(k)]
            if parts:
                body = ": ".join(parts)
    except (ValueError, AttributeError):
        pass
    body = " ".join(body.split())
    if len(body) > MAX_ERROR_BODY_CHARS:
        body = body[:MAX_ERROR_BODY_CHARS] + "..."
    return body


class OpenAIClient:
    """Minimal JSON client for the OpenAI REST API with retry/backoff."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = API_BASE,
        opener: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ConfigError("The OpenAI API base URL must use https://")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep
        self._max_retries = max_retries

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float = REQUEST_TIMEOUT_SEC,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        idempotent = method.upper() in {"GET", "HEAD"}
        attempt = 0
        while True:
            # The URL is always https:// (checked in __init__).
            req = urllib.request.Request(  # noqa: S310
                url,
                data=data,
                method=method,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": f"user-clone-gpt/{__version__}",
                },
            )
            try:
                with self._opener(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
                try:
                    return json.loads(raw)
                except ValueError as exc:
                    raise OpenAIError(f"OpenAI API returned invalid JSON for {method} {path}") from exc
            except urllib.error.HTTPError as exc:
                retryable = exc.code in RETRYABLE_ANY_METHOD or (
                    idempotent and exc.code in RETRYABLE_IDEMPOTENT
                )
                if retryable and attempt < self._max_retries:
                    self._sleep(self._retry_delay(attempt, exc))
                    attempt += 1
                    continue
                body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
                raise OpenAIError(f"OpenAI API {exc.code}: {_summarize_error_body(body)}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if idempotent and attempt < self._max_retries:
                    self._sleep(self._retry_delay(attempt, None))
                    attempt += 1
                    continue
                reason = getattr(exc, "reason", exc)
                raise OpenAIError(f"Network error calling OpenAI API: {reason}") from exc

    @staticmethod
    def _retry_delay(attempt: int, exc: urllib.error.HTTPError | None) -> float:
        if exc is not None and exc.headers is not None:
            retry_after = exc.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(max(float(retry_after), 0.0), 60.0)
                except ValueError:
                    pass
        return min(RETRY_BASE_DELAY_SEC * (2**attempt), 30.0)


# --------------------------------------------------------------------------
# Responses API
# --------------------------------------------------------------------------


def build_request_body(
    config: Config, prompt: str, *, previous_response_id: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": config.model,
        "input": prompt,
        "store": True,
        "background": True,
    }
    if config.instructions:
        body["instructions"] = config.instructions
    if config.vector_store_ids:
        body["tools"] = [{"type": "file_search", "vector_store_ids": config.vector_store_ids}]
    if config.prompt_id:
        prompt_ref: dict[str, Any] = {"id": config.prompt_id}
        if config.prompt_version:
            prompt_ref["version"] = config.prompt_version
        body["prompt"] = prompt_ref
    if previous_response_id:
        body["previous_response_id"] = previous_response_id
    return body


def wait_for_response(
    client: OpenAIClient,
    response: dict[str, Any],
    *,
    timeout_sec: float,
    poll_interval: float = POLL_INTERVAL_SEC,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Poll a background response until it leaves the queued/in_progress states."""
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    deadline = clock() + timeout_sec
    while response.get("status") in PENDING_STATUSES:
        if clock() >= deadline:
            raise TimeoutError(f"Response {response.get('id')} did not complete within {timeout_sec:g}s")
        sleep(poll_interval)
        response_id = validate_id(str(response.get("id", "")), label="response ID")
        response = client.request("GET", f"/responses/{urllib.parse.quote(response_id, safe='')}")
    return response


def extract_output_text(response: dict[str, Any]) -> str:
    """Return the concatenated assistant text from a Responses API object."""
    status = response.get("status")
    if status in TERMINAL_FAILURE_STATUSES:
        error = response.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else error
        raise OpenAIError(f"Response {status}: {message or 'no error details'}")

    parts: list[str] = []
    for item in response.get("output") or []:
        if item.get("type") != "message" or item.get("role", "assistant") != "assistant":
            continue
        for block in item.get("content") or []:
            if block.get("type") == "output_text" and block.get("text"):
                parts.append(block["text"])
    if not parts:
        raise OpenAIError("No assistant text in the response")
    if status == "incomplete":
        reason = (response.get("incomplete_details") or {}).get("reason", "unknown")
        print(f"[warning] response is incomplete (reason: {reason})", file=sys.stderr)
    return "\n".join(parts)


def ask(
    client: OpenAIClient,
    config: Config,
    prompt: str,
    *,
    previous_response_id: str | None = None,
    timeout_sec: float = DEFAULT_RUN_TIMEOUT_SEC,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> tuple[str, str]:
    """Send ``prompt`` and return (reply_text, response_id)."""
    body = build_request_body(config, prompt, previous_response_id=previous_response_id)
    response = client.request("POST", "/responses", body)
    try:
        response = wait_for_response(client, response, timeout_sec=timeout_sec, sleep=sleep, clock=clock)
    except TimeoutError:
        cancel_response(client, str(response.get("id", "")))
        raise
    return extract_output_text(response), str(response.get("id", ""))


def cancel_response(client: OpenAIClient, response_id: str) -> None:
    """Best-effort cancel of a background response so it stops consuming tokens."""
    try:
        response_id = validate_id(response_id, label="response ID")
        client.request("POST", f"/responses/{urllib.parse.quote(response_id, safe='')}/cancel", {})
        print(f"[cancelled] {response_id}", file=sys.stderr)
    except (OpenAIError, ConfigError) as exc:
        print(f"[warning] could not cancel {response_id}: {exc}", file=sys.stderr)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _refuse_sensitive_file(path: Path) -> None:
    name = path.name.lower()
    if name == ".env" or name.startswith(".env.") or name.endswith((".pem", ".key")):
        raise ConfigError(f"Refusing to send {path} to OpenAI: it looks like a secrets file")


def read_prompt_file(spec: str) -> str:
    if spec == "-":
        return sys.stdin.read()
    path = Path(spec).expanduser()
    if not path.is_file():
        raise ConfigError(f"Prompt file not found: {spec}")
    _refuse_sensitive_file(path)
    if path.stat().st_size > MAX_PROMPT_FILE_BYTES:
        raise ConfigError(f"Prompt file is larger than {MAX_PROMPT_FILE_BYTES} bytes: {spec}")
    return path.read_text(encoding="utf-8")


def read_prompt_arg(value: str) -> str:
    """Positional prompt: a path to an existing file is read, otherwise used as text.

    Kept for backwards compatibility; prefer ``--prompt-file`` to be explicit.
    """
    path = Path(value).expanduser()
    try:
        is_file = path.is_file()
    except OSError:  # e.g. a very long prompt string is not a valid path
        is_file = False
    if is_file:
        print(f"[prompt] reading prompt from file {value}", file=sys.stderr)
        return read_prompt_file(value)
    return value


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        epilog="Environment variables are documented in the module docstring and .env.example.",
    )
    p.add_argument("prompt", nargs="?", help="Prompt text, or path to a file containing the prompt")
    p.add_argument("--prompt-file", help="Read the prompt from this file ('-' for stdin)")
    p.add_argument("--model", default=None, help=f"Model to use (default: OPENAI_MODEL or {DEFAULT_MODEL})")
    p.add_argument(
        "--previous-response-id",
        "--thread-id",
        dest="previous_response_id",
        help="Continue from an earlier response (resp_...) for follow-ups. "
        "--thread-id is a compatibility alias; thread_... IDs no longer work.",
    )
    p.add_argument(
        "--timeout", type=int, default=None, help="Max seconds to wait (default: OPENAI_RUN_TIMEOUT or 300)"
    )
    p.add_argument("-o", "--output", help="Write the reply to this file (parent dirs are created)")
    p.add_argument(
        "--info", action="store_true", help="Print the resolved, non-secret configuration and exit"
    )
    p.add_argument(
        "--ensure-model-only",
        action="store_true",
        help="Validate configuration and print the model, then exit (no API call)",
    )
    p.add_argument(
        "--skip-model-check",
        action="store_true",
        help="Deprecated no-op (kept for compatibility with 1.x invocations)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(
    argv: list[str] | None = None, *, client_factory: Callable[[str], OpenAIClient] = OpenAIClient
) -> int:
    args = build_parser().parse_args(argv)

    try:
        load_env(env_path())
        config = load_config(args.model)
        timeout = (
            args.timeout
            if args.timeout is not None
            else env_int("OPENAI_RUN_TIMEOUT", DEFAULT_RUN_TIMEOUT_SEC)
        )
        if timeout <= 0:
            raise ConfigError("--timeout must be positive")
        previous = (
            validate_id(args.previous_response_id, label="previous response ID", prefix="resp_")
            if args.previous_response_id
            else None
        )
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR

    if args.info:
        print(json.dumps(config.describe(), indent=2))
        return EXIT_OK

    if args.ensure_model_only:
        print(f"Model: {config.model}", file=sys.stderr)
        return EXIT_OK

    if args.prompt and args.prompt_file:
        print("Pass either a positional prompt or --prompt-file, not both.", file=sys.stderr)
        return EXIT_USAGE
    try:
        if args.prompt_file:
            prompt = read_prompt_file(args.prompt_file)
        elif args.prompt:
            prompt = read_prompt_arg(args.prompt)
        else:
            print("Provide a prompt, --prompt-file, or use --info / --ensure-model-only.", file=sys.stderr)
            return EXIT_USAGE
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR
    if not prompt.strip():
        print("Prompt is empty.", file=sys.stderr)
        return EXIT_USAGE

    client = client_factory(config.api_key)
    try:
        reply, response_id = ask(
            client,
            config,
            prompt,
            previous_response_id=previous,
            timeout_sec=timeout,
        )
    except (OpenAIError, ConfigError, TimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_ERROR

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(reply + "\n", encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(reply)

    print(f"[response_id={response_id}]", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
