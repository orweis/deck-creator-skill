#!/usr/bin/env python3
"""Chat with User-Clone-GPT (OpenAI Assistant) for personalized content generation.

Loads OPENAI_API_KEY, OPENAI_ASSISTANT_ID, and optional OPENAI_MODEL from .env.
Ensures the assistant runs on the configured frontier model before each run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.5"
# Newest frontier models may not be on Assistants API yet; try in order.
ASSISTANT_MODEL_FALLBACKS = (
    "gpt-5.5",
    "gpt-5",
    "gpt-4.1",
    "gpt-4o",
)
POLL_INTERVAL_SEC = 1.0
DEFAULT_RUN_TIMEOUT_SEC = 300


def project_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".env").is_file():
            return candidate
    return here.parents[4]


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def require_assistant_id() -> str:
    assistant_id = os.environ.get("OPENAI_ASSISTANT_ID", "").strip()
    if not assistant_id:
        raise RuntimeError(
            "OPENAI_ASSISTANT_ID is not set. Add it to .env in the project root."
        )
    return assistant_id


def api_request(
    method: str,
    path: str,
    *,
    api_key: str,
    payload: dict | None = None,
) -> dict:
    url = f"{API_BASE}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API {exc.code}: {body}") from exc


def get_assistant(api_key: str, assistant_id: str) -> dict:
    return api_request("GET", f"/assistants/{assistant_id}", api_key=api_key)


def ensure_model(api_key: str, assistant_id: str, model: str) -> str:
    """Return the model in use; update assistant to `model` or best available fallback."""
    assistant = get_assistant(api_key, assistant_id)
    current = assistant.get("model", "")

    candidates: list[str] = []
    for candidate in (model, *ASSISTANT_MODEL_FALLBACKS):
        if candidate not in candidates:
            candidates.append(candidate)

    if current in candidates:
        preferred_idx = candidates.index(model) if model in candidates else 0
        current_idx = candidates.index(current)
        if current_idx <= preferred_idx:
            return current

    last_error = ""
    for candidate in candidates:
        try:
            updated = api_request(
                "POST",
                f"/assistants/{assistant_id}",
                api_key=api_key,
                payload={"model": candidate},
            )
            chosen = updated["model"]
            if chosen != current:
                note = "" if chosen == model else f" ({model} not available on Assistants API yet)"
                print(f"[model] updated {current!r} -> {chosen!r}{note}", file=sys.stderr)
            return chosen
        except RuntimeError as exc:
            last_error = str(exc)
            if "unsupported_model" not in last_error and "cannot be used with the Assistants API" not in last_error:
                raise

    raise RuntimeError(
        f"Could not set assistant model. Tried: {', '.join(candidates)}. Last error: {last_error}"
    )


def create_thread(api_key: str) -> str:
    return api_request("POST", "/threads", api_key=api_key, payload={})["id"]


def add_message(api_key: str, thread_id: str, content: str) -> None:
    api_request(
        "POST",
        f"/threads/{thread_id}/messages",
        api_key=api_key,
        payload={"role": "user", "content": content},
    )


def run_assistant(api_key: str, thread_id: str, assistant_id: str) -> str:
    return api_request(
        "POST",
        f"/threads/{thread_id}/runs",
        api_key=api_key,
        payload={"assistant_id": assistant_id},
    )["id"]


def wait_for_run(api_key: str, thread_id: str, run_id: str, *, timeout_sec: int) -> dict:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        run = api_request(
            "GET",
            f"/threads/{thread_id}/runs/{run_id}",
            api_key=api_key,
        )
        status = run.get("status")
        if status == "completed":
            return run
        if status in {"failed", "cancelled", "expired"}:
            raise RuntimeError(f"Run {status}: {run.get('last_error')}")
        time.sleep(POLL_INTERVAL_SEC)
    raise TimeoutError(f"Run did not complete within {timeout_sec}s")


def latest_assistant_message(api_key: str, thread_id: str) -> str:
    data = api_request("GET", f"/threads/{thread_id}/messages?limit=10", api_key=api_key)
    for message in data.get("data", []):
        if message.get("role") != "assistant":
            continue
        parts = []
        for block in message.get("content", []):
            if block.get("type") == "text":
                parts.append(block["text"]["value"])
        if parts:
            return "\n".join(parts)
    raise RuntimeError("No assistant reply found on thread")


def ask(
    api_key: str,
    assistant_id: str,
    prompt: str,
    *,
    thread_id: str | None = None,
    timeout_sec: int,
    model: str,
    skip_model_check: bool = False,
) -> tuple[str, str]:
    if not skip_model_check:
        ensure_model(api_key, assistant_id, model)
    thread_id = thread_id or create_thread(api_key)
    add_message(api_key, thread_id, prompt)
    run_id = run_assistant(api_key, thread_id, assistant_id)
    wait_for_run(api_key, thread_id, run_id, timeout_sec=timeout_sec)
    return latest_assistant_message(api_key, thread_id), thread_id


def read_prompt_arg(value: str) -> str:
    path = Path(value)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return value


def parse_args() -> argparse.Namespace:
    load_env(project_root() / ".env")

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "prompt",
        nargs="?",
        help="Prompt text, or path to a file containing the prompt",
    )
    p.add_argument(
        "--model",
        default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        help=f"Target model (default: OPENAI_MODEL or {DEFAULT_MODEL})",
    )
    p.add_argument("--thread-id", help="Reuse an existing thread for follow-ups")
    p.add_argument(
        "--timeout",
        type=int,
        default=int(os.environ.get("OPENAI_RUN_TIMEOUT", DEFAULT_RUN_TIMEOUT_SEC)),
        help="Max seconds to wait for a run to complete",
    )
    p.add_argument("-o", "--output", help="Write response to this file path")
    p.add_argument("--info", action="store_true", help="Print assistant metadata")
    p.add_argument(
        "--ensure-model-only",
        action="store_true",
        help="Update assistant model if needed, then exit",
    )
    p.add_argument(
        "--skip-model-check",
        action="store_true",
        help="Do not verify or update the assistant model before running",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY is not set. Add it to .env in the project root.", file=sys.stderr)
        return 1

    try:
        assistant_id = require_assistant_id()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.info:
        assistant = get_assistant(api_key, assistant_id)
        print(json.dumps(assistant, indent=2))
        return 0

    if args.ensure_model_only:
        model = ensure_model(api_key, assistant_id, args.model)
        print(f"Assistant model: {model}", file=sys.stderr)
        return 0

    if not args.prompt:
        print("Provide a prompt (or file path) or use --info / --ensure-model-only.", file=sys.stderr)
        return 1

    prompt = read_prompt_arg(args.prompt)
    try:
        reply, thread_id = ask(
            api_key,
            assistant_id,
            prompt,
            thread_id=args.thread_id,
            timeout_sec=args.timeout,
            model=args.model,
            skip_model_check=args.skip_model_check,
        )
    except (RuntimeError, TimeoutError, urllib.error.URLError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.output:
        Path(args.output).write_text(reply + "\n", encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(reply)

    print(f"[thread_id={thread_id}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
