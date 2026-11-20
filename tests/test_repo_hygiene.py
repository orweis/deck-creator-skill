"""Repository-level checks: versioning, duplicated files, and secret hygiene."""

from __future__ import annotations

import re
import subprocess

from conftest import PITCH_SKILL, REPO_ROOT

SECRET_PATTERNS = [
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),  # OpenAI keys
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key IDs
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),  # GitHub tokens
]


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / line for line in out.splitlines() if (REPO_ROOT / line).is_file()]


def test_version_file_matches_cli_version(clone_mod):
    assert (REPO_ROOT / "VERSION").read_text().strip() == clone_mod.__version__


def test_changelog_mentions_current_version():
    version = (REPO_ROOT / "VERSION").read_text().strip()
    assert f"## [{version}]" in (REPO_ROOT / "CHANGELOG.md").read_text()


def test_top_level_template_mirrors_skill_template():
    """The top-level copy is kept for compatibility and must not drift."""
    top = REPO_ROOT / "deck-prompt-template.md"
    assert top.read_text(encoding="utf-8") == (PITCH_SKILL / "deck-prompt-template.md").read_text(
        encoding="utf-8"
    )


def test_no_secrets_in_repository():
    offenders = []
    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern.pattern}")
    assert offenders == []


def test_env_files_are_ignored_but_example_is_not():
    def ignored(name):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=REPO_ROOT, check=False)
        return r.returncode == 0

    assert ignored(".env")
    assert ignored(".env.local")
    assert ignored("output/deck.pdf")
    assert not ignored(".env.example")
