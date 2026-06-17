---
name: user-clone-gpt
description: Generates personalized sales, marketing, and presentation content via the User-Clone-GPT OpenAI Assistant (your configured voice, product docs, and domain knowledge). Uses ChatGPT 5.5 or the latest configured frontier model. Use when the user asks to draft pitch copy, deck layouts, questionnaire answers, buyer emails, blog posts, or other content in their cloned voice, or mentions User-Clone-GPT or OpenAI assistant content generation.
---

# User-Clone-GPT Content Generator

Generate buyer-facing and domain content through **User-Clone-GPT** — an OpenAI Assistant configured with your voice, product knowledge, and file-search sources. Set the assistant ID in `.env` as `OPENAI_ASSISTANT_ID`.

**Underlying model:** **ChatGPT 5.5** (`gpt-5.5`) or the latest frontier model set in `.env` as `OPENAI_MODEL`. Before each run, the CLI tries `gpt-5.5` first, then falls back to the newest model that OpenAI exposes on the **Assistants API** (today often `gpt-4.1` until `gpt-5.5` is enabled for assistants on your account).

## Inputs to gather

1. **Content type** (required) — e.g. pitch deck layout, questionnaire answer, buyer email, blog outline, talking points.
2. **Audience / buyer** (required for sales content) — company name, role, context.
3. **Constraints** (optional) — length, tone tweaks, must-include proof points, format (markdown bullets, Q&A, prose).
4. **Source material** (optional) — paste RFP questions, call notes, or a file path the agent should fold into the prompt.

If anything required is missing, ask before generating.

## One-time setup

Ensure `.env` in the project root contains:

```bash
OPENAI_API_KEY=sk-...
OPENAI_ASSISTANT_ID=asst_...          # your User-Clone-GPT assistant
OPENAI_MODEL=gpt-5.5                  # latest frontier slug when OpenAI ships a newer default
```

Verify connectivity and model:

```bash
SKILL_DIR="<absolute path to .agents/skills/user-clone-gpt>"
python3 "$SKILL_DIR/scripts/ask_user_clone_gpt.py" --info
python3 "$SKILL_DIR/scripts/ask_user_clone_gpt.py" --ensure-model-only
```

No extra Python packages — the script uses the stdlib only.

## Workflow

```
- [ ] 0. Set SKILL_DIR, CONTENT_TYPE, AUDIENCE, OUT_PATH (optional)
- [ ] 1. Confirm .env has OPENAI_API_KEY and OPENAI_ASSISTANT_ID
- [ ] 2. Ensure assistant model is gpt-5.5 (or OPENAI_MODEL)
- [ ] 3. Build the prompt from the template below
- [ ] 4. Run ask_user_clone_gpt.py; capture thread_id for follow-ups
- [ ] 5. Review output for accuracy (claims, links, proof points)
- [ ] 6. Save to ./output/ or hand off to downstream skills (e.g. pitch-deck-generator)
```

### Step 0: Variables

```bash
SKILL_DIR="<absolute path to .agents/skills/user-clone-gpt>"
CONTENT_TYPE="pitch deck layout"   # from user
AUDIENCE="Acme Corp — VP Engineering"
COMPANY_SLUG=$(echo "$AUDIENCE" | tr '[:upper:] ' '[:lower:]_' | tr -cd '[:alnum:]_-' | cut -d_ -f1)
OUT_PATH="./output/${COMPANY_SLUG}_user_clone_gpt_${CONTENT_TYPE// /_}.md"
mkdir -p ./output
```

### Step 2: Ensure ChatGPT 5.5

Always run before first generation in a session (idempotent):

```bash
python3 "$SKILL_DIR/scripts/ask_user_clone_gpt.py" --ensure-model-only
```

If `gpt-5.5` is unavailable on Assistants API, the script auto-selects the next best compatible model (`gpt-4.1`, then `gpt-4o`). Check [OpenAI models](https://developers.openai.com/api/docs/models) for the latest frontier slug and set `OPENAI_MODEL` in `.env` when a newer model ships.

### Step 3: Prompt template

Adapt per request; keep structure consistent so User-Clone-GPT returns usable copy:

```markdown
Write in the voice and style configured for this assistant.

**Content type:** {CONTENT_TYPE}
**Audience:** {AUDIENCE}

**Task:**
{Specific deliverable — e.g. "Produce a 10-slide deck layout as markdown bullets with title + 3–5 bullets per slide."}

**Constraints:**
- Match the tone from prior transcripts and approved copy in the assistant's knowledge base.
- Cite product documentation with links where relevant.
- Do not invent customer logos, metrics, or certifications.

**Context from user:**
{Paste RFP items, call notes, product angles, or competitor context}
```

Write the filled prompt to a temp file when it is long:

```bash
PROMPT_PATH="/tmp/user-clone-gpt-${COMPANY_SLUG}.md"
# ... write prompt to $PROMPT_PATH ...
```

### Step 4: Generate

```bash
python3 "$SKILL_DIR/scripts/ask_user_clone_gpt.py" "$PROMPT_PATH" -o "$OUT_PATH"
# Or inline:
python3 "$SKILL_DIR/scripts/ask_user_clone_gpt.py" "Short one-shot question here"

# Follow-up on same thread (refine tone, shorten, add slide):
python3 "$SKILL_DIR/scripts/ask_user_clone_gpt.py" "Tighten slide 3 to 4 bullets max." --thread-id thread_...
```

Long runs (multi-slide decks, long questionnaires) may take several minutes. Default timeout is 300s; override with `--timeout 600` if needed.

### Step 5: Review checklist

Before delivering to the user:

- [ ] Claims match known facts from your product docs and knowledge base.
- [ ] Links point to real documentation paths when cited.
- [ ] No fabricated case studies or customer names unless provided in context.
- [ ] Format matches what the user asked for (bullets vs prose vs Q&A).

### Step 6: Downstream handoff

| Generated content | Next step |
|-------------------|-----------|
| Pitch deck layout / slide bullets | Feed as `--deck-layout` input to **pitch-deck-generator** skill |
| Questionnaire answers | Deliver as markdown or paste into customer's portal |
| Email / blog draft | Edit lightly for recipient-specific details |

## Content types — quick prompts

**Pitch deck layout** — "Produce a {N}-slide deck layout for {Company}. Each slide: title + 3–5 bullets. Lead with their pain, map to your product value, close with proof points and next steps."

**Questionnaire** — Paste each question. Ask for concise answers with doc links.

**Buyer email** — Subject line + body under 200 words. One clear CTA. Reference one relevant capability for their stack.

**Talking points** — 5–7 bullets for a {duration} call with {role} at {Company}.

## Files in this skill

| File | Purpose |
|------|---------|
| `scripts/ask_user_clone_gpt.py` | CLI: load `.env`, ensure `gpt-5.5`, run assistant, optional `-o` output |
| `SKILL.md` | This workflow |

## Troubleshooting

- **`OPENAI_API_KEY is not set`** — Add key to project root `.env`.
- **`OPENAI_ASSISTANT_ID is not set`** — Add your User-Clone-GPT assistant ID to `.env`.
- **Model update fails** — Confirm the account has access to frontier models; the script falls back automatically. Set `OPENAI_MODEL` to a supported Assistants slug if needed.
- **Run timeout** — Increase `--timeout`; split long questionnaires into batches on one `--thread-id`.
- **Generic or off-brand tone** — Add transcript excerpts or prior approved copy to the prompt context; use a follow-up on the same thread to tighten voice.
- **Wrong claim** — Reply on the same thread with the correction and ask for a rewrite.

## References

- OpenAI Assistants API — https://platform.openai.com/docs/assistants
- GPT-5.5 model — https://developers.openai.com/api/docs/models/gpt-5.5
