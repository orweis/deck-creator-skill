#!/usr/bin/env bash
# One-time installer for the pitch-deck-generator skill.
# Idempotent: safe to re-run.

set -euo pipefail

log() { printf '\033[1;36m[setup]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[setup]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[setup]\033[0m %s\n' "$*" >&2; }

# ---- 1. notebooklm-py CLI -------------------------------------------------

if command -v notebooklm >/dev/null 2>&1; then
  log "notebooklm CLI already installed ($(notebooklm --version 2>/dev/null || echo unknown))"
else
  log "Installing notebooklm-py[browser] ..."
  if command -v uv >/dev/null 2>&1; then
    uv tool install "notebooklm-py[browser]"
  elif command -v pipx >/dev/null 2>&1; then
    pipx install "notebooklm-py[browser]"
  else
    PIP=$(command -v pip3 || command -v pip || true)
    if [ -z "$PIP" ]; then
      err "No pip/pipx/uv on PATH. Install one of them and retry."
      exit 1
    fi
    "$PIP" install --user "notebooklm-py[browser]"
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

PW_BIN=""
if [ -n "$NB_VENV_BIN" ] && [ -x "$NB_VENV_BIN/playwright" ]; then
  PW_BIN="$NB_VENV_BIN/playwright"
elif command -v uv >/dev/null 2>&1; then
  PW_BIN="uv tool run --from notebooklm-py playwright"
elif command -v playwright >/dev/null 2>&1; then
  warn "Could not find playwright inside notebooklm's venv; falling back to system 'playwright' (this may install Chromium into the wrong cache)."
  PW_BIN="playwright"
fi

if [ -n "$PW_BIN" ]; then
  log "Installing Playwright Chromium via: $PW_BIN install chromium"
  # shellcheck disable=SC2086
  $PW_BIN install chromium || warn "Chromium install failed; retry manually before running 'notebooklm login'."
else
  warn "No playwright entry point found. Re-install with: uv tool install --reinstall 'notebooklm-py[browser]'"
fi

# ---- 2. Watermark remover -------------------------------------------------

WM_DIR="${NOTEBOOKLM_WM_DIR:-$HOME/.local/share/notebooklm-watermark-remover}"
WM_REPO="https://github.com/Albonire/notebooklm-watermark-remover.git"
WM_BRANCH="bibi"

if [ ! -d "$WM_DIR/.git" ]; then
  log "Cloning watermark remover into $WM_DIR ..."
  mkdir -p "$(dirname "$WM_DIR")"
  git clone --branch "$WM_BRANCH" --depth 1 "$WM_REPO" "$WM_DIR"
else
  log "Watermark remover already present at $WM_DIR; pulling latest ..."
  git -C "$WM_DIR" fetch --depth 1 origin "$WM_BRANCH"
  git -C "$WM_DIR" reset --hard "origin/$WM_BRANCH"
fi

VENV_DIR="$WM_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  log "Creating venv for watermark remover ..."
  python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
log "Installing watermark remover deps ..."
pip install --quiet --upgrade pip
pip install --quiet -r "$WM_DIR/requirements.txt"
deactivate

# ---- 3. Quick auth check --------------------------------------------------

if notebooklm auth check --json >/dev/null 2>&1; then
  log "NotebookLM auth OK."
else
  warn "NotebookLM not authenticated yet. Run: notebooklm login"
fi

log "Setup complete."
log "  - notebooklm CLI: $(command -v notebooklm)"
log "  - watermark remover: $WM_DIR (venv: $VENV_DIR)"
