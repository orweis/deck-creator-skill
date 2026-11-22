# Agent skills

Project skills live under **`.agents/skills/`**. Cursor and other agents in this repo discover them here — no symlinks under `.cursor/skills/` required.

| Skill | Path | Use when |
|-------|------|----------|
| **pitch-deck-generator** | [`skills/pitch-deck-generator/SKILL.md`](skills/pitch-deck-generator/SKILL.md) | Creating a buyer-specific pitch deck (NotebookLM → PDF → Canva) |
| **user-clone-gpt** | [`skills/user-clone-gpt/SKILL.md`](skills/user-clone-gpt/SKILL.md) | Drafting personalized sales, marketing, and presentation copy in the user's voice via User-Clone-GPT (OpenAI Responses API) |

Typical pipeline: **pitch-deck-generator** calls **user-clone-gpt** automatically when no deck layout is provided (research + slide bullets), then builds the deck in NotebookLM.

Ground rules for agents using these skills:

- Never print or commit secrets from `.env`; never pass `.env` or key files as prompts.
- Ask the user before uploading a deck to any public host (the Canva import step).
- Run `python -m pytest` after changing scripts (see the README's *Development and testing*).
