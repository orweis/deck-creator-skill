"""Tests for the bash scripts. External tools (notebooklm, the watermark
remover) are replaced by stubs; nothing is installed or downloaded."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from conftest import PITCH_SKILL, REPO_ROOT

pytestmark = pytest.mark.shell

SCRIPTS = PITCH_SKILL / "scripts"
BATCH = REPO_ROOT / "scripts" / "run_batch_decks.sh"
ALL_SHELL = sorted([*SCRIPTS.glob("*.sh"), *(REPO_ROOT / "scripts").glob("*.sh")])


def bash(*args, env=None, cwd=None):
    full_env = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/tmp")}
    full_env.update(env or {})
    return subprocess.run(
        ["bash", *args], capture_output=True, text=True, env=full_env, cwd=cwd, timeout=60, check=False
    )


@pytest.mark.parametrize("script", ALL_SHELL, ids=lambda p: p.name)
def test_bash_syntax(script):
    assert bash("-n", str(script)).returncode == 0


@pytest.mark.parametrize("script", ALL_SHELL, ids=lambda p: p.name)
def test_shellcheck_clean(script):
    if not shutil.which("shellcheck"):
        pytest.skip("shellcheck not installed (pip install shellcheck-py)")
    r = subprocess.run(["shellcheck", "-x", str(script)], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout


@pytest.mark.parametrize("script", ALL_SHELL, ids=lambda p: p.name)
def test_strict_mode(script):
    assert "set -euo pipefail" in script.read_text()


# ---------------------------------------------------------------- watermark


@pytest.fixture
def fake_wm(tmp_path):
    """A fake watermark-remover install whose remover.py records its argv."""
    wm = tmp_path / "wm"
    (wm / ".venv" / "bin").mkdir(parents=True)
    (wm / ".venv" / "bin" / "activate").write_text("# fake venv\n")
    py = wm / ".venv" / "bin" / "python3"
    py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    (wm / "remover.py").write_text(
        textwrap.dedent(
            """
            import json, os, sys
            with open(os.environ["ARGV_LOG"], "w") as f:
                json.dump({"argv": sys.argv[1:], "cwd": os.getcwd()}, f)
            """
        )
    )
    return wm


def test_remove_watermark_usage():
    r = bash(str(SCRIPTS / "remove_watermark.sh"))
    assert r.returncode == 64
    assert "Usage" in r.stderr


def test_remove_watermark_not_installed(tmp_path):
    r = bash(str(SCRIPTS / "remove_watermark.sh"), "x.pdf", env={"NOTEBOOKLM_WM_DIR": str(tmp_path)})
    assert r.returncode == 1
    assert "not installed" in r.stderr


def test_remove_watermark_missing_input(fake_wm, tmp_path):
    r = bash(
        str(SCRIPTS / "remove_watermark.sh"),
        str(tmp_path / "missing.pdf"),
        env={"NOTEBOOKLM_WM_DIR": str(fake_wm)},
    )
    assert r.returncode == 1
    assert "Input not found" in r.stderr


def test_remove_watermark_passes_absolute_paths_and_extra_args(fake_wm, tmp_path):
    import json

    src = tmp_path / "in dir" / "deck.pdf"
    src.parent.mkdir()
    src.write_bytes(b"%PDF")
    log = tmp_path / "argv.json"
    r = bash(
        str(SCRIPTS / "remove_watermark.sh"),
        "in dir/deck.pdf",
        "out/clean.pdf",
        "--",
        "--margin-x",
        "400",
        env={"NOTEBOOKLM_WM_DIR": str(fake_wm), "ARGV_LOG": str(log)},
        cwd=tmp_path,
    )
    assert r.returncode == 0, r.stderr
    rec = json.loads(log.read_text())
    assert rec["argv"] == [str(src), "-o", str(tmp_path / "out" / "clean.pdf"), "--margin-x", "400"]
    assert Path(rec["cwd"]) == fake_wm
    assert (tmp_path / "out").is_dir()


def test_remove_watermark_default_output_name(fake_wm, tmp_path):
    src = tmp_path / "deck.pdf"
    src.write_bytes(b"%PDF")
    r = bash(
        str(SCRIPTS / "remove_watermark.sh"),
        str(src),
        env={"NOTEBOOKLM_WM_DIR": str(fake_wm), "ARGV_LOG": str(tmp_path / "a.json")},
    )
    assert r.returncode == 0, r.stderr
    assert f"Cleaned file: {tmp_path}/deck_cleaned.pdf" in r.stdout


# ---------------------------------------------------------------- flatten


def test_flatten_wrapper_usage():
    r = bash(str(SCRIPTS / "flatten_pdf_for_canva.sh"), "only-one-arg")
    assert r.returncode == 64


def test_flatten_wrapper_missing_venv(tmp_path):
    r = bash(
        str(SCRIPTS / "flatten_pdf_for_canva.sh"), "a.pdf", "b.pdf", env={"NOTEBOOKLM_WM_DIR": str(tmp_path)}
    )
    assert r.returncode == 1
    assert "setup.sh" in r.stderr


def test_flatten_wrapper_runs_python_script(fake_wm, tmp_path):
    pytest.importorskip("fitz")
    import fitz

    src = tmp_path / "deck.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.save(str(src))
    doc.close()
    r = bash(
        str(SCRIPTS / "flatten_pdf_for_canva.sh"),
        str(src),
        str(tmp_path / "out" / "flat.pdf"),
        "--",
        "--scale",
        "0.5",
        env={
            "NOTEBOOKLM_WM_DIR": str(fake_wm),
            "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}",
        },
    )
    assert r.returncode == 0, r.stderr
    assert "(2 pages)" in r.stdout


# ---------------------------------------------------------------- setup.sh


@pytest.mark.parametrize("ref", ["bibi", "main", "fbe9d0a", "../../etc"])
def test_setup_rejects_non_sha_ref_before_doing_anything(tmp_path, ref):
    r = bash(
        str(SCRIPTS / "setup.sh"),
        env={"NOTEBOOKLM_WM_REF": ref, "NOTEBOOKLM_WM_DIR": str(tmp_path / "wm"), "HOME": str(tmp_path)},
    )
    assert r.returncode == 1
    assert "40-character commit SHA" in r.stderr
    assert not (tmp_path / "wm").exists()


def test_setup_pins_versions():
    text = (SCRIPTS / "setup.sh").read_text()
    assert "notebooklm-py[browser]==" in text
    assert "reset --hard" not in text
    import re

    assert re.search(r'WM_REF_DEFAULT="[0-9a-f]{40}"', text)


# ---------------------------------------------------------------- batch


def source_batch(snippet, env=None, tmp_path=None):
    script = f'source "{BATCH}"\n{snippet}\n'
    return bash("-c", script, env=env)


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Acme Corp", "acme_corp"),
        ("Example Inc.", "example_inc"),
        ("AT&T", "att"),
        ("dash-ok_1", "dash-ok_1"),
    ],
)
def test_slugify(name, slug):
    r = source_batch(f'slugify "{name}"')
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == slug


def test_slugify_never_empty_and_is_stable():
    r = source_batch('slugify "日本"; slugify "日本"; slugify "中国"')
    a, b, c = r.stdout.split()
    assert a == b and a.startswith("company_") and a != c


def test_sourcing_batch_script_has_no_side_effects(tmp_path):
    r = source_batch("echo sourced", env={"OUTPUT_DIR": str(tmp_path / "o")})
    assert r.returncode == 0 and r.stdout.strip() == "sourced"
    assert not (tmp_path / "o").exists()


def test_work_dir_is_private(tmp_path):
    r = source_batch("work_dir_for acme", env={"WORK_ROOT": str(tmp_path / "work")})
    assert r.returncode == 0, r.stderr
    d = Path(r.stdout.strip())
    assert d == tmp_path / "work" / "acme"
    assert stat.S_IMODE(d.stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "work").stat().st_mode) == 0o700


def test_load_companies_file(tmp_path):
    f = tmp_path / "companies.txt"
    f.write_text("# header\n\nAcme|Context one\nNoContext\nLast|with | pipe")
    r = source_batch(
        f'load_companies_file "{f}"; printf "%s\\n" "${{COMPANIES[@]}}"; echo "n=${{#COMPANIES[@]}}"'
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["Acme|Context one", "NoContext", "Last|with | pipe", "n=3"]


def test_load_companies_file_missing(tmp_path):
    r = source_batch(f'load_companies_file "{tmp_path}/nope" || echo failed')
    assert "failed" in r.stdout


def test_find_logo(tmp_path):
    env = {"WORK_ROOT": str(tmp_path / "w")}
    r = source_batch("find_logo Acme acme", env=env)
    assert r.stdout.strip() == "" and "No logo" in r.stderr
    (tmp_path / "w" / "acme" / "acme_logo.jpg").write_bytes(b"x")
    r = source_batch("find_logo Acme acme", env=env)
    assert r.stdout.strip() == str(tmp_path / "w" / "acme" / "acme_logo.jpg")


def test_cached_layout_still_produces_pitch_file(tmp_path):
    """Regression: with a cached layout the pitch file used to be missing."""
    out = tmp_path / "out"
    out.mkdir()
    (out / "acme_corp_user_clone_gpt_deck_layout.md").write_text("## Slide 1: Hi\n")
    env = {"OUTPUT_DIR": str(out), "WORK_ROOT": str(tmp_path / "work")}
    r = source_batch('generate_user_clone_gpt_layout "Acme Corp" "ctx"', env=env)
    assert r.returncode == 0, r.stderr
    pitch = Path(r.stdout.strip())
    assert pitch.read_text() == "# Acme Corp — buyer pitch description\n\n## Slide 1: Hi\n"


def test_prompt_values_are_not_executed(tmp_path):
    """Company names / context are inserted literally into the prompt."""
    out = tmp_path / "out"
    out.mkdir()
    marker = tmp_path / "pwned"
    stub_dir = tmp_path / "stub"
    # Stub the User-Clone-GPT call: copy the prompt file to the -o target.
    fake_root = tmp_path / "repo"
    fake_script = fake_root / ".agents/skills/user-clone-gpt/scripts/ask_user_clone_gpt.py"
    fake_script.parent.mkdir(parents=True)
    fake_script.write_text(
        "import sys, shutil\n"
        "a = sys.argv[1:]\n"
        "shutil.copy(a[a.index('--prompt-file') + 1], a[a.index('-o') + 1])\n"
    )
    stub_dir.mkdir()
    company = f"Evil $(touch {marker}) `touch {marker}`"
    snippet = (
        f'USER_CLONE_GPT_SKILL_DIR="{fake_root}/.agents/skills/user-clone-gpt"\n'
        f"generate_user_clone_gpt_layout '{company}' '$(touch {marker})'"
    )
    r = source_batch(snippet, env={"OUTPUT_DIR": str(out), "WORK_ROOT": str(tmp_path / "w")})
    assert r.returncode == 0, r.stderr
    assert not marker.exists()
    pitch = Path(r.stdout.strip()).read_text()
    assert f"$(touch {marker})" in pitch


def test_batch_main_requires_tools(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "OUTPUT_DIR": str(tmp_path / "o")}
    if shutil.which("notebooklm", path=env["PATH"]):
        pytest.skip("notebooklm is installed system-wide")
    r = bash(str(BATCH), env=env)
    assert r.returncode != 0
    assert "Required tool not found on PATH: notebooklm" in r.stderr
