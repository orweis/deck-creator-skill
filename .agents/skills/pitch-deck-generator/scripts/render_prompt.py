#!/usr/bin/env python3
"""Render the pitch-deck prompt template.

Substitutes:
  <Company Name> -> --company
  <Deck Layout>  -> contents of --deck-layout file (or '-' for stdin)

Fails (exit 2) if any unsubstituted <...> placeholders remain, so the agent
never silently ships a half-rendered prompt to NotebookLM. Note that the
check also covers the substituted deck layout, so a layout containing text
such as ``<TBD>`` is rejected too; edit the layout or pass
--allow-placeholders. Exit codes: 0 ok, 1 unreadable input, 2 invalid input.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PLACEHOLDER_RE = re.compile(r"<[^<>\n]{1,80}>")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
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
    return p.parse_args(argv)


def read_layout(spec: str) -> str:
    if spec == "-":
        return sys.stdin.read()
    return Path(spec).read_text(encoding="utf-8")


def render(template: str, company: str, layout: str) -> str:
    """Substitute both placeholders in a single pass.

    A single regex pass means text inside the company name or the layout is
    never itself treated as a placeholder to substitute.
    """
    values = {"<Company Name>": company, "<Deck Layout>": layout}
    return re.sub("|".join(re.escape(k) for k in values), lambda m: values[m.group(0)], template)


def find_leftovers(rendered: str) -> list[str]:
    return sorted(set(PLACEHOLDER_RE.findall(rendered)))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    company = args.company
    if not company.strip():
        sys.stderr.write("render_prompt.py: --company must not be empty\n")
        return 2
    try:
        template = Path(args.template).read_text(encoding="utf-8")
        layout = read_layout(args.deck_layout)
    except OSError as exc:
        sys.stderr.write(f"render_prompt.py: {exc}\n")
        return 1
    if not layout.strip():
        sys.stderr.write("render_prompt.py: deck layout is empty\n")
        return 2

    rendered = render(template, company, layout)

    if not args.allow_placeholders:
        leftovers = find_leftovers(rendered)
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
