#!/usr/bin/env bash
# One-time installer for the pitch-deck-generator skill.
# Idempotent: safe to re-run.
#
# Installs:
#   1. the notebooklm-py CLI (pinned version) and Playwright Chromium for login
#   2. the third-party notebooklm-watermark-remover, pinned to a reviewed commit,
#      into its own venv
#
# This script installs and later runs third-party code. Both sources are pinned;
# review the pinned commit before changing it.
#
# Environment overrides:
#   NOTEBOOKLM_PY_SPEC   pip requirement for the CLI (default: pinned below)
#   NOTEBOOKLM_WM_DIR    watermark remover install dir
#                        (default: ~/.local/share/notebooklm-watermark-remover)
#   NOTEBOOKLM_WM_REF    commit SHA of the watermark remover to install
#                        (default: pinned below)

set -euo pipefail

NOTEBOOKLM_PY_SPEC="${NOTEBOOKLM_PY_SPEC:-notebooklm-py[browser]==0.8.6}"
WM_REPO="https://github.com/Albonire/notebooklm-watermark-remover.git"
# Head of the upstream 'bibi' branch at the time of review.
WM_REF_DEFAULT="fbe9d0a3ad042891d008379dd4e993331b70dd60"
WM_REF="${NOTEBOOKLM_WM_REF:-$WM_REF_DEFAULT}"
WM_DIR="${NOTEBOOKLM_WM_DIR:-$HOME/.local/share/notebooklm-watermark-remover}"

log()  { printf '\033[1;36m[setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[setup]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[setup]\033[0m %s\n' "$*" >&2; }

if ! [[ "$WM_REF" =~ ^[0-9a-f]{40}$ ]]; then
  err "NOTEBOOKLM_WM_REF must be a full 40-character commit SHA (got '$WM_REF')."
  exit 1
fi

for tool in git python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    err "'$tool' is required but not on PATH."
    exit 1
  fi
done

# ---- 1. notebooklm-py CLI -------------------------------------------------

if command -v notebooklm >/dev/null 2>&1; then
  log "notebooklm CLI already installed ($(notebooklm --version 2>/dev/null || echo unknown))"
else
  log "Installing $NOTEBOOKLM_PY_SPEC ..."
  if command -v uv >/dev/null 2>&1; then
    uv tool install "$NOTEBOOKLM_PY_SPEC"
  elif command -v pipx >/dev/null 2>&1; then
    pipx install "$NOTEBOOKLM_PY_SPEC"
  else
    PIP=$(command -v pip3 || command -v pip || true)
    if [ -z "$PIP" ]; then
      err "No pip/pipx/uv on PATH. Install one of them and retry."
      exit 1
    fi
    if ! "$PIP" install --user "$NOTEBOOKLM_PY_SPEC"; then
      err "pip install failed. On systems with an externally managed Python (PEP 668),"
      err "install uv or pipx and re-run this script."
      exit 1
    fi
  fi
fi

# Resolve the playwright that lives in the SAME venv as `notebooklm`.
# `uv tool install` / `pipx` only expose the `notebooklm` entry point on $PATH,
# but `notebooklm login` needs the playwright bundled inside that same venv to
# have downloaded Chromium. Calling a global `playwright` would target the
# wrong cache and login fails with "Executable doesn't exist".
resolve_path() {
  if command -v readlink >/dev/null 2>&1 && readlink -f "$1" >/dev/null 2>&1; then
    readlink -f "$1"
  else
    python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$1"
  fi
}

NB_BIN="$(command -v notebooklm || true)"
NB_VENV_BIN=""
if [ -n "$NB_BIN" ]; then
  NB_VENV_BIN="$(dirname "$(resolve_path "$NB_BIN")")"
fi

PW_CMD=()
if [ -n "$NB_VENV_BIN" ] && [ -x "$NB_VENV_BIN/playwright" ]; then
  PW_CMD=("$NB_VENV_BIN/playwright")
elif command -v uv >/dev/null 2>&1; then
  PW_CMD=(uv tool run --from "$NOTEBOOKLM_PY_SPEC" playwright)
elif command -v playwright >/dev/null 2>&1; then
  warn "Could not find playwright inside notebooklm's venv; falling back to system 'playwright' (this may install Chromium into the wrong cache)."
  PW_CMD=(playwright)
fi

if [ "${#PW_CMD[@]}" -gt 0 ]; then
  log "Installing Playwright Chromium via: ${PW_CMD[*]} install chromium"
  "${PW_CMD[@]}" install chromium || warn "Chromium install failed; retry manually before running 'notebooklm login'."
else
  warn "No playwright entry point found. Re-install with: uv tool install --reinstall '$NOTEBOOKLM_PY_SPEC'"
fi

# ---- 2. Watermark remover (pinned commit) ---------------------------------

if [ ! -d "$WM_DIR/.git" ]; then
  log "Cloning watermark remover into $WM_DIR ..."
  mkdir -p "$WM_DIR"
  git -C "$WM_DIR" init --quiet
  git -C "$WM_DIR" remote add origin "$WM_REPO"
fi

current_ref="$(git -C "$WM_DIR" rev-parse --verify --quiet HEAD || true)"
if [ "$current_ref" != "$WM_REF" ]; then
  if [ -n "$(git -C "$WM_DIR" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
    err "$WM_DIR has local modifications; refusing to overwrite them."
    err "Commit/stash them or remove the directory, then re-run."
    exit 1
  fi
  log "Checking out watermark remover at pinned commit $WM_REF ..."
  git -C "$WM_DIR" fetch --quiet --depth 1 origin "$WM_REF"
  git -C "$WM_DIR" checkout --quiet --detach FETCH_HEAD
fi

actual_ref="$(git -C "$WM_DIR" rev-parse HEAD)"
if [ "$actual_ref" != "$WM_REF" ]; then
  err "Watermark remover HEAD is $actual_ref, expected $WM_REF."
  exit 1
fi
log "Watermark remover at $actual_ref"

VENV_DIR="$WM_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  log "Creating venv for watermark remover ..."
  python3 -m venv "$VENV_DIR"
fi

log "Installing watermark remover deps ..."
"$VENV_DIR/bin/python3" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/python3" -m pip install --quiet -r "$WM_DIR/requirements.txt"
# flatten_pdf_pages.py needs PyMuPDF; install it explicitly instead of relying
# on the remover's requirements to keep pulling it in.
"$VENV_DIR/bin/python3" -m pip install --quiet pymupdf

# ---- 3. Quick auth check --------------------------------------------------

if command -v notebooklm >/dev/null 2>&1 && notebooklm auth check --json >/dev/null 2>&1; then
  log "NotebookLM auth OK."
else
  warn "NotebookLM not authenticated yet. Run: notebooklm login"
fi

log "Setup complete."
log "  - notebooklm CLI: $(command -v notebooklm || echo 'not on PATH (open a new shell)')"
log "  - watermark remover: $WM_DIR (venv: $VENV_DIR)"
