"""Shared fixtures. No test in this suite talks to a real network service."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PITCH_SKILL = REPO_ROOT / ".agents" / "skills" / "pitch-deck-generator"
CLONE_SKILL = REPO_ROOT / ".agents" / "skills" / "user-clone-gpt"


def load_script(path: Path, name: str):
    """Import a standalone script (its path has dashes, so it is not a package)."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def clone_mod():
    return load_script(CLONE_SKILL / "scripts" / "ask_user_clone_gpt.py", "ask_user_clone_gpt")


@pytest.fixture(scope="session")
def render_mod():
    return load_script(PITCH_SKILL / "scripts" / "render_prompt.py", "render_prompt")


@pytest.fixture(scope="session")
def flatten_mod():
    return load_script(PITCH_SKILL / "scripts" / "flatten_pdf_pages.py", "flatten_pdf_pages")


@pytest.fixture
def clean_openai_env(monkeypatch, tmp_path):
    """Remove OPENAI_* variables and point .env loading at an empty temp file."""
    import os

    for key in list(os.environ):
        if key.startswith("OPENAI_"):
            monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("OPENAI_ENV_FILE", str(env_file))
    return env_file


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail loudly if any test reaches the real urllib opener."""
    import urllib.request

    def _blocked(*args, **kwargs):
        raise AssertionError("tests must not make real network calls")

    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
