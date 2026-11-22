#!/usr/bin/env python3
"""Backwards-compatible entry point for the user-clone-gpt CLI.

Equivalent to running .agents/skills/user-clone-gpt/scripts/ask_user_clone_gpt.py
with the same arguments; kept so older invocations keep working.
"""

import runpy
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / ".agents/skills/user-clone-gpt/scripts/ask_user_clone_gpt.py"

if __name__ == "__main__":
    runpy.run_path(str(TARGET), run_name="__main__")
