#!/usr/bin/env bash
# Thin wrapper around Albonire/notebooklm-watermark-remover.
# Usage: remove_watermark.sh <input> [output] [-- <extra remover args>]

set -euo pipefail

WM_DIR="${NOTEBOOKLM_WM_DIR:-$HOME/.local/share/notebooklm-watermark-remover}"

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <input.pdf|.pptx|.png|.jpg> [output] [-- <extra remover args>]" >&2
  exit 64
fi

if [ ! -f "$WM_DIR/remover.py" ]; then
  echo "Watermark remover not installed at $WM_DIR." >&2
  echo "Run scripts/setup.sh first (or set NOTEBOOKLM_WM_DIR to your install)." >&2
  exit 1
fi

INPUT="$1"; shift
OUTPUT=""
EXTRA=()

if [ "$#" -gt 0 ] && [ "$1" != "--" ]; then
  OUTPUT="$1"; shift
fi
if [ "$#" -gt 0 ] && [ "$1" = "--" ]; then
  shift
  EXTRA=("$@")
fi

if [ ! -f "$INPUT" ]; then
  echo "Input not found: $INPUT" >&2
  exit 1
fi

VENV_DIR="$WM_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Watermark remover venv missing. Re-run scripts/setup.sh." >&2
  exit 1
fi

# Use absolute paths since we cd into $WM_DIR (the remover writes outputs relative to cwd otherwise).
INPUT_ABS="$(cd "$(dirname "$INPUT")" && pwd)/$(basename "$INPUT")"
OUTPUT_ABS=""
if [ -n "$OUTPUT" ]; then
  mkdir -p "$(dirname "$OUTPUT")"
  OUTPUT_ABS="$(cd "$(dirname "$OUTPUT")" && pwd)/$(basename "$OUTPUT")"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$WM_DIR"

if [ -n "$OUTPUT_ABS" ]; then
  python3 remover.py "$INPUT_ABS" -o "$OUTPUT_ABS" ${EXTRA[@]+"${EXTRA[@]}"}
  echo "Cleaned file: $OUTPUT_ABS"
else
  python3 remover.py "$INPUT_ABS" ${EXTRA[@]+"${EXTRA[@]}"}
  base="${INPUT_ABS%.*}"
  ext="${INPUT_ABS##*.}"
  echo "Cleaned file: ${base}_cleaned.${ext}"
fi
