---
name: user-clone-gpt
description: Generates personalized sales, marketing, and presentation content in the user's cloned voice (User-Clone-GPT) via the OpenAI Responses API, using configured instructions, a file-search knowledge base and/or a reusable prompt. Use when the user asks to draft pitch copy, deck layouts, questionnaire answers, buyer emails, blog posts, or other content in their cloned voice, or mentions User-Clone-GPT or OpenAI content generation.
---

# User-Clone-GPT Content Generator

Generate buyer-facing and domain content through **User-Clone-GPT**: your voice (system instructions), your product knowledge (an OpenAI vector store used with `file_search`), and/or a reusable dashboard prompt, run on the **OpenAI Responses API**.

> Version 2.0.0 replaced the OpenAI Assistants API (shut down by OpenAI on 2026-08-26). `OPENAI_ASSISTANT_ID` and `thread_...` IDs no longer work. See the project's `CHANGELOG.md` → *Migrating from 1.x*.

## Inputs to gather

1. **Content type** (required): e.g. pitch deck layout, questionnaire answer, buyer email, blog outline, talking points.
2. **Audience / buyer** (required for sales content): company name, role, context.
3. **Constraints** (optional): length, tone tweaks, must-include proof points, format (markdown bullets, Q&A, prose).
4. **Source material** (optional): RFP questions, call notes, or a file path to fold into the prompt.

If anything required is missing, ask before generating.

## One-time setup

Create `.env` in the project root from `.env.example`:

```bash
OPENAI_API_KEY=sk-...
OPENAI_INSTRUCTIONS_FILE=voice/instructions.md   # your voice / system prompt
OPENAI_VECTOR_STORE_IDS=vs_...                   # knowledge base for file_search (comma-separated)
# OPENAI_PROMPT_ID=pmpt_...                      # optional reusable prompt
# OPENAI_MODEL=gpt-5.5                           # optional; default gpt-5.5
```

At least one of `OPENAI_INSTRUCTIONS_FILE`, `OPENAI_VECTOR_STORE_IDS`, `OPENAI_PROMPT_ID` is required, and `OPENAI_API_KEY` is required for every mode (including `--info`). The project root is the nearest directory above the script containing `.agents` or `.git`; if the skill is installed elsewhere, set `OPENAI_ENV_FILE=/path/to/.env`. Requests use background mode with `store: true`, so OpenAI keeps prompts and responses under your account's retention settings. Check the configuration (no API call, never prints the key):

```bash
SKILL_DIR="<absolute path to .agents/skills/user-clone-gpt>"
python3 "$SKILL_DIR/scripts/ask_user_clone_gpt.py" --info
```

No extra Python packages: the script uses the standard library only.

## Workflow

```
- [ ] 0. Set SKILL_DIR, CONTENT_TYPE, AUDIENCE, OUT_PATH (optional)
- [ ] 1. Confirm configuration with --info
- [ ] 2. Build the prompt from the template below and write it to a file
- [ ] 3. Run ask_user_clone_gpt.py --prompt-file; note the response_id for follow-ups
- [ ] 4. Review output for accuracy (claims, links, proof points)
- [ ] 5. Save to ./output/ or hand off to downstream skills (e.g. pitch-deck-generator)
```

### Step 0: Variables

```bash
SKILL_DIR="<absolute path to .agents/skills/user-clone-gpt>"
CONTENT_TYPE="pitch deck layout"   # from user
AUDIENCE="Acme Corp — VP Engineering"
COMPANY_SLUG="acme_corp"         # short file-name-safe slug: lowercase, [a-z0-9_-] only
OUT_PATH="./output/${COMPANY_SLUG}_user_clone_gpt_${CONTENT_TYPE// /_}.md"
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/user-clone-gpt.XXXXXX")   # private, per run
```

### Step 2: Prompt template

Adapt per request; keep the structure so the output is usable:

```markdown
Write in the voice and style configured for this assistant.

**Content type:** {CONTENT_TYPE}
**Audience:** {AUDIENCE}

**Task:**
{Specific deliverable — e.g. "Produce a 10-slide deck layout as markdown bullets with title + 3–5 bullets per slide."}

**Constraints:**
- Match the tone from prior transcripts and approved copy in the knowledge base.
- Cite product documentation with links where relevant.
- Do not invent customer logos, metrics, or certifications.

**Context from user:**
{Paste RFP items, call notes, product angles, or competitor context}
```

Write the filled prompt to `"$WORK_DIR/prompt.md"`.

### Step 3: Generate

```bash
python3 "$SKILL_DIR/scripts/ask_user_clone_gpt.py" --prompt-file "$WORK_DIR/prompt.md" -o "$OUT_PATH"
# Or inline:
python3 "$SKILL_DIR/scripts/ask_user_clone_gpt.py" "Short one-shot question here"

# Follow-up that continues the previous answer (refine tone, shorten, add slide):
python3 "$SKILL_DIR/scripts/ask_user_clone_gpt.py" "Tighten slide 3 to 4 bullets max." \
  --previous-response-id resp_... -o "$OUT_PATH"
```

Each run prints `[response_id=resp_...]` on stderr; pass it to `--previous-response-id` for follow-ups. Long runs may take several minutes. The default timeout is 300s; override with `--timeout 600`.

Prefer `--prompt-file`. A positional argument that names an existing file is also read as a file (compatibility); secrets files (`.env*`, `*.pem`, `*.key`) are always refused.

Exit codes: `0` success, `1` configuration/API/network/timeout error (message on stderr), `2` usage error.

### Step 4: Review checklist

Before delivering to the user:

- [ ] Claims match known facts from your product docs and knowledge base.
- [ ] Links point to real documentation paths when cited.
- [ ] No fabricated case studies or customer names unless provided in context.
- [ ] Format matches what the user asked for (bullets vs prose vs Q&A).

### Step 5: Downstream handoff

| Generated content | Next step |
|-------------------|-----------|
| Pitch deck layout / slide bullets | Feed as `--deck-layout` input to **pitch-deck-generator** skill |
| Questionnaire answers | Deliver as markdown or paste into customer's portal |
| Email / blog draft | Edit lightly for recipient-specific details |

## Content types — quick prompts

**Pitch deck layout**: "Produce a {N}-slide deck layout for {Company}. Each slide: title + 3–5 bullets. Lead with their pain, map to your product value, close with proof points and next steps."

**Questionnaire**: paste each question. Ask for concise answers with doc links.

**Buyer email**: subject line + body under 200 words. One clear CTA. Reference one relevant capability for their stack.

**Talking points**: 5–7 bullets for a {duration} call with {role} at {Company}.

## Files in this skill

| File | Purpose |
|------|---------|
| `scripts/ask_user_clone_gpt.py` | CLI: loads `.env`, calls the Responses API (background mode + polling, retries on 429/5xx), optional `-o` output |
| `SKILL.md` | This workflow |

## Troubleshooting

- **`OPENAI_API_KEY is not set`**: add the key to the project root `.env`.
- **`The OpenAI Assistants API was shut down ...`**: you still have only `OPENAI_ASSISTANT_ID`; follow the migration steps in `CHANGELOG.md`.
- **`No voice configured`**: set `OPENAI_INSTRUCTIONS_FILE`, `OPENAI_VECTOR_STORE_IDS` and/or `OPENAI_PROMPT_ID`.
- **`OpenAI API 404` / model errors**: set `OPENAI_MODEL` to a model your account can use (see [OpenAI models](https://developers.openai.com/api/docs/models)).
- **Timeout**: increase `--timeout`; split long questionnaires into batches chained with `--previous-response-id`.
- **Generic or off-brand tone**: add transcript excerpts or approved copy to the prompt; refine with a follow-up.
- **Wrong claim**: follow up with the correction and ask for a rewrite.

## References

- OpenAI Responses API — https://platform.openai.com/docs/api-reference/responses
- Migrating from the Assistants API — https://platform.openai.com/docs/assistants/migration
- File search — https://platform.openai.com/docs/guides/tools-file-search
