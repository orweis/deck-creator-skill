"""Tests for pitch-deck-generator/scripts/render_prompt.py."""

from __future__ import annotations

import subprocess
import sys

import pytest
from conftest import PITCH_SKILL

SCRIPT = PITCH_SKILL / "scripts" / "render_prompt.py"
TEMPLATE = PITCH_SKILL / "deck-prompt-template.md"


def run(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


@pytest.fixture
def layout(tmp_path):
    p = tmp_path / "layout.md"
    p.write_text("## Slide 1: Why now\n- Point A\n", encoding="utf-8")
    return p


def test_render_bundled_template(layout):
    r = run("--template", str(TEMPLATE), "--company", "Acme Corp", "--deck-layout", str(layout))
    assert r.returncode == 0, r.stderr
    assert "<Company Name>" not in r.stdout and "<Deck Layout>" not in r.stdout
    assert r.stdout.count("Acme Corp") >= 3
    assert r.stdout.rstrip().endswith("- Point A")


def test_render_from_stdin():
    r = run("--template", str(TEMPLATE), "--company", "Acme", "--deck-layout", "-", stdin="## Slide 1: Hi\n")
    assert r.returncode == 0, r.stderr
    assert "## Slide 1: Hi" in r.stdout


def test_leftover_placeholder_fails(tmp_path, layout):
    tpl = tmp_path / "t.md"
    tpl.write_text("Pitch to <Company Name> about <Product Name>\n<Deck Layout>")
    r = run("--template", str(tpl), "--company", "Acme", "--deck-layout", str(layout))
    assert r.returncode == 2
    assert "<Product Name>" in r.stderr
    assert r.stdout == ""


def test_allow_placeholders_override(tmp_path, layout):
    tpl = tmp_path / "t.md"
    tpl.write_text("<Company Name> <Other>\n<Deck Layout>")
    r = run("--template", str(tpl), "--company", "Acme", "--deck-layout", str(layout), "--allow-placeholders")
    assert r.returncode == 0
    assert "<Other>" in r.stdout


def test_values_are_not_re_substituted(render_mod):
    """A company name containing a placeholder token must be inserted literally."""
    out = render_mod.render("<Company Name>|<Deck Layout>", "<Deck Layout>", "L")
    assert out == "<Deck Layout>|L"


def test_placeholder_regex_ignores_long_or_multiline_spans(render_mod):
    assert render_mod.find_leftovers("a < b and c > d") == ["< b and c >"]
    assert render_mod.find_leftovers("<\nnot>") == []
    assert render_mod.find_leftovers("<" + "x" * 81 + ">") == []


@pytest.mark.parametrize(
    ("company", "layout_text", "rc"),
    [("   ", "## Slide", 2), ("Acme", "   \n", 2)],
)
def test_empty_inputs_rejected(tmp_path, company, layout_text, rc):
    lay = tmp_path / "l.md"
    lay.write_text(layout_text)
    r = run("--template", str(TEMPLATE), "--company", company, "--deck-layout", str(lay))
    assert r.returncode == rc


def test_missing_files_exit_1_without_traceback(tmp_path, layout):
    r = run("--template", str(tmp_path / "nope.md"), "--company", "A", "--deck-layout", str(layout))
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    r = run("--template", str(TEMPLATE), "--company", "A", "--deck-layout", str(tmp_path / "nope.md"))
    assert r.returncode == 1


def test_missing_required_args_is_usage_error():
    r = run("--company", "A")
    assert r.returncode == 2
    assert "usage" in r.stderr.lower()
