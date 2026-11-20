#!/usr/bin/env python3
"""
Re-save a PDF so each page is one full-page raster (single image xobject).

NotebookLM watermark removal patches PDFs by pasting a bitmap into a rect over
the old watermark. Some tools (including Canva PDF imports and Presentation
resize) treat that as a separate layer and can nudge it vs the slide. Flatten
to a merged bitmap per page so there is no separate overlay layer.

Requires PyMuPDF (``pip install pymupdf``). flatten_pdf_for_canva.sh runs this
script inside the watermark-remover venv, which already has it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_SCALE = 2.0
MAX_SCALE = 8.0  # beyond this, page bitmaps get very large (memory / file size)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=(__doc__ or "").strip().split("\n\n")[0])
    p.add_argument("input_pdf", help="PDF (e.g. watermark-cleaned deck)")
    p.add_argument(
        "-o",
        "--output",
        required=True,
        help="Output PDF path (one embedded image per page)",
    )
    p.add_argument(
        "--scale",
        type=float,
        default=DEFAULT_SCALE,
        help=f"Render scale vs PDF points (default {DEFAULT_SCALE}; max {MAX_SCALE})",
    )
    return p.parse_args(argv)


def flatten(input_pdf: str | Path, output_pdf: str | Path, scale: float = DEFAULT_SCALE) -> int:
    """Rasterize every page of ``input_pdf`` into ``output_pdf``; return the page count."""
    import fitz  # PyMuPDF; imported lazily so --help works without it

    src = fitz.open(str(input_pdf))
    dst = fitz.open()
    try:
        matrix = fitz.Matrix(scale, scale)
        for page in src:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            new_page = dst.new_page(width=page.rect.width, height=page.rect.height)
            new_page.insert_image(new_page.rect, pixmap=pix, keep_proportion=False)
        n_pages = dst.page_count
        dst.save(str(output_pdf), garbage=4, deflate=True)
    finally:
        src.close()
        dst.close()
    return n_pages


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not 0 < args.scale <= MAX_SCALE:
        print(f"--scale must be > 0 and <= {MAX_SCALE}", file=sys.stderr)
        return 2
    if not Path(args.input_pdf).is_file():
        print(f"Input not found: {args.input_pdf}", file=sys.stderr)
        return 1
    if Path(args.input_pdf).resolve() == Path(args.output).resolve():
        print("Output must differ from input", file=sys.stderr)
        return 2

    try:
        import fitz  # noqa: F401
    except ImportError:
        print(
            "PyMuPDF (fitz) is required. Run via flatten_pdf_for_canva.sh (uses the "
            "notebooklm-watermark-remover venv) or: pip install pymupdf",
            file=sys.stderr,
        )
        return 1

    try:
        n_pages = flatten(args.input_pdf, args.output, args.scale)
    except Exception as exc:  # PyMuPDF raises its own exception types
        print(f"Failed to flatten {args.input_pdf}: {exc}", file=sys.stderr)
        return 1

    print(f"Flattened: {args.output} ({n_pages} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
