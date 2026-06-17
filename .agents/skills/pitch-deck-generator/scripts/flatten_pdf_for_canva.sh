#!/usr/bin/env bash
# Raster-merge each PDF page into a single full-page image (PyMuPDF).
# Uses the same venv as the NotebookLM watermark remover (already has pymupdf).
#
# Usage: flatten_pdf_for_canva.sh <input.pdf> <output.pdf> [-- --scale 2.5 ...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WM_DIR="${NOTEBOOKLM_WM_DIR:-$HOME/.local/share/notebooklm-watermark-remover}"

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <input.pdf> <output.pdf> [-- extra-args for flatten_pdf_pages.py]" >&2
  exit 64
fi

VENV_DIR="$WM_DIR/.venv"
if [ ! -x "$VENV_DIR/bin/python3" ]; then
  echo "Watermark remover venv not found at $VENV_DIR. Run scripts/setup.sh." >&2
  exit 1
fi

INPUT="$1"
OUTPUT="$2"
shift 2
EXTRA=()
if [ "$#" -gt 0 ] && [ "$1" = "--" ]; then
  shift
  EXTRA=("$@")
fi

if [ ! -f "$INPUT" ]; then
  echo "Input not found: $INPUT" >&2
  exit 1
fi

INPUT_ABS="$(cd "$(dirname "$INPUT")" && pwd)/$(basename "$INPUT")"
mkdir -p "$(dirname "$OUTPUT")"
OUTPUT_ABS="$(cd "$(dirname "$OUTPUT")" && pwd)/$(basename "$OUTPUT")"

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python3 "$SCRIPT_DIR/flatten_pdf_pages.py" "$INPUT_ABS" -o "$OUTPUT_ABS" ${EXTRA[@]+"${EXTRA[@]}"}
