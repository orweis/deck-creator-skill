#!/usr/bin/env python3
"""Thin wrapper — delegates to the user-clone-gpt skill CLI."""

from pathlib import Path
import runpy

runpy.run_path(
    str(
        Path(__file__).resolve().parents[1]
        / ".agents/skills/user-clone-gpt/scripts/ask_user_clone_gpt.py"
    ),
    run_name="__main__",
)
