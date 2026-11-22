"""Tests for pitch-deck-generator/scripts/flatten_pdf_pages.py."""

from __future__ import annotations

import subprocess
import sys

import pytest
from conftest import PITCH_SKILL

SCRIPT = PITCH_SKILL / "scripts" / "flatten_pdf_pages.py"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60, check=False
    )


def test_help_works_without_pymupdf():
    r = run("--help")
    assert r.returncode == 0
    assert "--scale" in r.stdout


@pytest.mark.parametrize("scale", ["0", "-1", "9"])
def test_scale_bounds(tmp_path, scale):
    src = tmp_path / "in.pdf"
    src.write_bytes(b"%PDF-1.4")
    r = run(str(src), "-o", str(tmp_path / "out.pdf"), "--scale", scale)
    assert r.returncode == 2
    assert "--scale" in r.stderr


def test_missing_input(tmp_path):
    r = run(str(tmp_path / "missing.pdf"), "-o", str(tmp_path / "out.pdf"))
    assert r.returncode == 1
    assert "Input not found" in r.stderr


def test_output_must_differ_from_input(tmp_path):
    src = tmp_path / "in.pdf"
    src.write_bytes(b"%PDF-1.4")
    r = run(str(src), "-o", str(src))
    assert r.returncode == 2


def test_corrupt_pdf_reports_error(tmp_path):
    pytest.importorskip("fitz")
    src = tmp_path / "in.pdf"
    src.write_bytes(b"this is not a pdf")
    r = run(str(src), "-o", str(tmp_path / "out.pdf"))
    assert r.returncode == 1
    assert "Failed to flatten" in r.stderr
    assert "Traceback" not in r.stderr


def test_flatten_produces_one_image_per_page(tmp_path, flatten_mod):
    fitz = pytest.importorskip("fitz")
    src = tmp_path / "deck.pdf"
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page(width=400, height=225)
        page.insert_text((40, 100), f"Slide {i + 1}", fontsize=24)
        page.draw_rect(fitz.Rect(300, 180, 390, 220), color=(1, 0, 0), fill=(1, 0, 0))
    doc.save(str(src))
    doc.close()

    out = tmp_path / "flat.pdf"
    assert flatten_mod.flatten(src, out, scale=1.0) == 3

    flat = fitz.open(str(out))
    try:
        assert flat.page_count == 3
        for page in flat:
            assert page.rect.width == pytest.approx(400)
            assert page.rect.height == pytest.approx(225)
            assert len(page.get_images()) == 1
            assert page.get_text().strip() == ""  # text is baked into pixels
    finally:
        flat.close()


def test_cli_success_message(tmp_path):
    fitz = pytest.importorskip("fitz")
    src = tmp_path / "deck.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(src))
    doc.close()
    r = run(str(src), "-o", str(tmp_path / "out.pdf"), "--scale", "0.5")
    assert r.returncode == 0, r.stderr
    assert "(1 pages)" in r.stdout
