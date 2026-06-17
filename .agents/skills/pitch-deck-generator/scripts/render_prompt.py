#!/usr/bin/env python3
"""Render the pitch-deck prompt template.

Substitutes:
  <Company Name> -> --company
  <Deck Layout>  -> contents of --deck-layout file (or '-' for stdin)

Fails (exit 2) if any unsubstituted <...> placeholders remain, so the agent
never silently ships a half-rendered prompt to NotebookLM.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"<[^<>\n]{1,80}>")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--template", required=True, help="Path to deck-prompt-template.md")
    p.add_argument("--company", required=True, help="Target company name")
    p.add_argument(
        "--deck-layout",
        required=True,
        help="Path to a file containing the deck layout / pitch description (or '-' for stdin)",
    )
    p.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Don't fail if unsubstituted <...> placeholders remain (not recommended)",
    )
    return p.parse_args()


def read_layout(spec: str) -> str:
    if spec == "-":
        return sys.stdin.read()
    return Path(spec).read_text(encoding="utf-8")


def main() -> int:
    args = parse_args()
    template = Path(args.template).read_text(encoding="utf-8")
    layout = read_layout(args.deck_layout)

    rendered = template.replace("<Company Name>", args.company).replace(
        "<Deck Layout>", layout
    )

    if not args.allow_placeholders:
        leftovers = sorted(set(PLACEHOLDER_RE.findall(rendered)))
        if leftovers:
            sys.stderr.write(
                "render_prompt.py: unsubstituted placeholders remain:\n  "
                + "\n  ".join(leftovers)
                + "\nFill them in the template or pass --allow-placeholders to override.\n"
            )
            return 2

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
