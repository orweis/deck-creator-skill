#!/usr/bin/env python3
"""
Re-save a PDF so each page is one full-page raster (single image xobject).

NotebookLM watermark removal patches PDFs by pasting a bitmap into a rect over
the old watermark. Some tools (including Canva PDF imports and Presentation
resize) treat that as a separate layer and can nudge it vs the slide. Flatten
to a merged bitmap per page so there is no separate overlay layer.
"""

from __future__ import annotations

import argparse
import sys

try:
    import fitz  # PyMuPDF
except ImportError as e:  # pragma: no cover
    print(
        "PyMuPDF (fitz) is required. Use the notebooklm-watermark-remover venv "
        "(see scripts/flatten_pdf_for_canva.sh) or: pip install pymupdf",
        file=sys.stderr,
    )
    raise SystemExit(1) from e


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
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
        default=2.0,
        help="Render scale vs PDF points (default 2.0 — good tradeoff size vs sharpness)",
    )
    args = p.parse_args()

    if args.scale <= 0:
        print("--scale must be positive", file=sys.stderr)
        return 2

    src = fitz.open(args.input_pdf)
    dst = fitz.open()
    try:
        mat = fitz.Matrix(args.scale, args.scale)
        for page in src:
            w, h = page.rect.width, page.rect.height
            pix = page.get_pixmap(matrix=mat, alpha=False)
            np = dst.new_page(width=w, height=h)
            np.insert_image(
                np.rect,
                pixmap=pix,
                keep_proportion=False,
            )
        n_pages = dst.page_count
        dst.save(args.output, garbage=4, deflate=True)
    finally:
        src.close()
        dst.close()

    print(f"Flattened: {args.output} ({n_pages} pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
