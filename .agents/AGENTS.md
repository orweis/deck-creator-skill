# Agent skills

Project skills live under **`.agents/skills/`**. Cursor and other agents in this repo discover them here — no symlinks under `.cursor/skills/` required.

| Skill | Path | Use when |
|-------|------|----------|
| **pitch-deck-generator** | [`skills/pitch-deck-generator/SKILL.md`](skills/pitch-deck-generator/SKILL.md) | Creating a buyer-specific pitch deck (NotebookLM → PDF → Canva) |
| **user-clone-gpt** | [`skills/user-clone-gpt/SKILL.md`](skills/user-clone-gpt/SKILL.md) | Drafting personalized sales, marketing, and presentation copy via User-Clone-GPT (OpenAI Assistant, ChatGPT 5.5 / latest) |

Typical pipeline: **pitch-deck-generator** calls **user-clone-gpt** automatically when no deck layout is provided (research + slide bullets), then builds the deck in NotebookLM.
