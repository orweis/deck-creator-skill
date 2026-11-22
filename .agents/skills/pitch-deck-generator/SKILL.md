---
name: pitch-deck-generator
description: Generates a buyer-specific pitch deck via Google NotebookLM. Use when the user asks to "create a pitch deck for <Company>", "build a pitch for <Company>", "generate a buyer pitch", or otherwise wants a tailored sales deck for a target company. When no deck layout is provided, uses the user-clone-gpt skill (User-Clone-GPT / ask_user_clone_gpt.py) to research the buyer and produce a slide layout first. Resolves a NotebookLM notebook by name (default "Pitch Decks"), downloads the target company's logo from the web, uploads the logo and pitch description as sources, selects only the relevant sources (ignoring other companies' prior pitches), renders the bundled deck-prompt-template with the company name and deck layout, generates the slide deck, downloads it as PDF, removes the NotebookLM watermark, raster-merges each page (single flat image per slide) for stable Canva imports, and by default (after the user consents to a temporary public upload) imports that flattened PDF into Canva via MCP and converts it to a native Presentation for presenter mode (skippable).
---

# Pitch Deck Generator (NotebookLM)

End-to-end automation for producing a buyer-specific pitch deck. Drives [`teng-lin/notebooklm-py`](https://github.com/teng-lin/notebooklm-py) for the slide-deck generation, and [`Albonire/notebooklm-watermark-remover`](https://github.com/Albonire/notebooklm-watermark-remover) (pinned to a reviewed commit of branch `bibi` by `setup.sh`) for cleanup.

After the cleaned PDF exists, **raster-merge each page** (see Step 10) so the inpaint patch is no longer a separate vector layer—then **by default** push that **flattened** PDF into **Canva** using the **Canva MCP**: **after the user explicitly agrees** to a short-lived public HTTPS upload (Step 11), import from that URL, then **resize** the imported design to the **`presentation`** preset so each page behaves as a proper slide in **Canva presenter mode**. Skip this block when the user opts out or declines the public upload, the Canva MCP is unavailable, or public upload fails after reasonable retries.

## Inputs to gather from the user

1. **Company name** (required) — substituted into every `<Company Name>` placeholder in the prompt template. Example: `"Acme Corp"`.
2. **Deck layout / pitch description** (optional) — the condensed slide list and any buyer-specific notes (this becomes `<Deck Layout>` in the template). Accept inline text or a file path. **If missing, run Step 2.5** — use **user-clone-gpt** (`ask_user_clone_gpt.py`) to research the company and auto-generate the layout before continuing.
3. **Notebook name** (optional, default `"Pitch Decks"`) — NotebookLM notebook to use.
4. **Logo URL** (optional) — if the user already has the logo URL, skip the web search.
5. **Canva post-processing** (optional opt-out) — by default, run flatten → Canva import → Presentation resize after watermark removal. If the user asks to skip Canva, set `SKIP_CANVA=1` or note "skip Canva" and omit steps **11–12** (also skip step **10** flatten unless they still want a flat PDF for another tool).

If **company name** is missing, ask before starting. Do **not** ask for a deck layout when none was provided — generate it via User-Clone-GPT instead.

## One-time setup

Run once per machine. `SKILL_DIR` below is the absolute path to this skill directory.

```bash
bash "$SKILL_DIR/scripts/setup.sh"
notebooklm login   # only if `notebooklm status` is not authenticated yet
```

This installs a pinned `notebooklm-py` (CLI + Python lib) via uv/pipx/pip and checks out the watermark remover at a pinned commit into `~/.local/share/notebooklm-watermark-remover/` with its own venv (plus PyMuPDF for flattening). It runs third-party code; see the project `SECURITY.md`. Requires `jq` for the commands below.

Verify the toolchain works before running the workflow:

```bash
notebooklm status        # confirms auth
notebooklm list --json   # confirms API access
```

## Workflow

Copy this checklist and tick items off as you go:

```
- [ ] 0. Set SKILL_DIR, USER_CLONE_GPT_SKILL_DIR, COMPANY, NB_NAME variables; make ./output dir
- [ ] 1. Resolve notebook ID by name
- [ ] 2. Find and download the company logo (web search)
- [ ] 2.5. (If no deck layout) Research company + generate layout via User-Clone-GPT → PITCH_PATH
- [ ] 3. Write or confirm the pitch description file (PITCH_PATH)
- [ ] 4. Upload the logo + pitch description as NotebookLM sources
- [ ] 5. List sources and pick only the relevant subset for this pitch
- [ ] 6. Render the deck prompt (substitute <Company Name> and <Deck Layout>)
- [ ] 7. Generate the slide deck via NotebookLM
- [ ] 8. Download the deck as PDF
- [ ] 9. Remove the watermark
- [ ] 10. Raster-merge cleaned PDF (one flat image per page) for Canva
- [ ] 11. (Default) **Ask the user to confirm** a temporary public upload, then upload flattened PDF to a public HTTPS URL; import into Canva (`import-design-from-url`) — if **`Not connected`**, ask user to toggle **Canva** MCP off/on (Step 11 subsection), then retry
- [ ] 12. (Default) Resize imported design to Presentation preset in Canva (`resize-design`) for presenter mode
- [ ] 13. Report paths (`*_pitch_cleaned.pdf`, `*_pitch_canva_flat.pdf`), NotebookLM sources, and Canva design IDs / edit URLs (import vs presentation)
```

Skip steps **11–12** when `SKIP_CANVA=1`, the user declines Canva, or the Canva MCP is missing / errors—still complete step **13** reporting for PDF-only runs (omit Canva lines). Omit step **10** as well when skipping Canva unless the user explicitly wants a flattened file.

### Step 0: Variables

Always pass `-n "$NB_ID"` / `--notebook "$NB_ID"` explicitly (don't rely on `notebooklm use`) so this is safe to run while other agents touch other notebooks.

```bash
SKILL_DIR="<absolute path to .agents/skills/pitch-deck-generator>"
USER_CLONE_GPT_SKILL_DIR="<absolute path to .agents/skills/user-clone-gpt>"
COMPANY="Acme Corp"                # from user input
COMPANY_SLUG=$(printf '%s' "$COMPANY" | tr '[:upper:] ' '[:lower:]_' | LC_ALL=C tr -cd 'a-z0-9_-')
[ -n "$COMPANY_SLUG" ] || COMPANY_SLUG="company_$(printf '%s' "$COMPANY" | cksum | cut -d' ' -f1)"
NB_NAME="${NB_NAME:-Pitch Decks}"
# Private per-run working directory (not a shared, predictable /tmp path).
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pitch-deck-${COMPANY_SLUG}.XXXXXX")
PITCH_PATH="$WORK_DIR/${COMPANY_SLUG}_pitch.md"   # user file, or User-Clone-GPT output (Step 2.5)
mkdir -p ./output
```

### Step 1: Resolve notebook ID

```bash
NB_ID=$(notebooklm list --json \
  | jq -r --arg t "$NB_NAME" '.notebooks[] | select(.title == $t) | .id' \
  | head -n1)

if [ -z "$NB_ID" ]; then
  echo "Notebook '$NB_NAME' not found. Existing notebooks:"
  notebooklm list
  exit 1
fi
```

If not found, ask the user whether to create it (`notebooklm create "$NB_NAME"`) or pick a different one.

### Step 2: Find and download the company logo

Use your web tools (web search + fetch) to locate the logo:

1. Search for `"{COMPANY} official logo PNG transparent"` (and/or `site:{company-domain} logo`).
2. Prefer a direct **HTTPS** raster image URL (`.png`, `.jpg`) with a transparent background, ideally from the company's own brand/press page. Skip search result pages and CDN-blocked URLs.
3. Download with HTTPS-only, size- and time-limited settings, then verify it is a raster image (SVG can carry scripts; convert it to PNG first if it is the only option):

```bash
LOGO_URL="<resolved direct image url>"
LOGO_PATH="$WORK_DIR/${COMPANY_SLUG}_logo.png"

case "$LOGO_URL" in https://*) ;; *) echo "Refusing non-HTTPS logo URL: $LOGO_URL"; exit 1 ;; esac
curl -fsSL --proto '=https' --proto-redir '=https' --max-filesize 5242880 --max-time 30 \
  -A "Mozilla/5.0" "$LOGO_URL" -o "$LOGO_PATH"
file "$LOGO_PATH" | grep -Eiq 'PNG image|JPEG image' || { echo "Not a PNG/JPEG image: $LOGO_URL"; rm -f "$LOGO_PATH"; exit 1; }
```

If the first URL fails or returns HTML, try the next candidate. If nothing works, ask the user to supply a logo URL or a local file path.

### Step 2.5: Research company + generate deck layout (when not provided)

**Skip this step** when the user already supplied a deck layout (inline or file path). Otherwise, follow the **user-clone-gpt** skill to research the buyer and produce a slide layout before NotebookLM generation.

Requires `OPENAI_API_KEY` plus a voice configuration (`OPENAI_INSTRUCTIONS_FILE`, `OPENAI_VECTOR_STORE_IDS` and/or `OPENAI_PROMPT_ID`) in the project root `.env` (see the user-clone-gpt skill).

```bash
USER_CLONE_GPT_PROMPT="$WORK_DIR/${COMPANY_SLUG}_user_clone_gpt_prompt.md"
PITCH_PATH="$WORK_DIR/${COMPANY_SLUG}_pitch.md"
USER_CLONE_GPT_OUT="./output/${COMPANY_SLUG}_user_clone_gpt_deck_layout.md"

cat > "$USER_CLONE_GPT_PROMPT" <<EOF
Write in the voice and style configured for this assistant.

**Content type:** buyer research + pitch deck layout
**Audience:** ${COMPANY}

**Task — two parts:**

1. **Company research (brief):** What does ${COMPANY} do? Who are their customers? What challenges likely matter for their product and GTM? Note any public signals (product focus, compliance posture, platform strategy, enterprise sales motion). Keep this to 5–8 bullets — factual, no invented metrics or customer names.

2. **Deck layout:** Produce a **10–12 slide** deck layout for pitching to **${COMPANY}**. Format exactly as markdown:
   - One \`## Slide N: Title\` heading per slide
   - **3–5 bullets** per slide (concise, buyer-specific)
   - Lead with ${COMPANY}'s likely pain, map to your product value, include proof points slide, close with next steps / CTA
   - Weave in research from part 1 — do not paste it as a separate appendix slide unless one slide is "Why now for ${COMPANY}"

**Constraints:**
- Match tone from prior transcripts and approved copy in the assistant's knowledge base.
- Cite product documentation with links where relevant.
- Do not invent customer logos, metrics, case studies, or certifications.

Output **only** the deck layout section (part 2) as the main body. You may include a short \`## Buyer context\` block (≤8 bullets) at the top if it helps the slide narrative.
EOF

python3 "$USER_CLONE_GPT_SKILL_DIR/scripts/ask_user_clone_gpt.py" --info   # config check, no API call
python3 "$USER_CLONE_GPT_SKILL_DIR/scripts/ask_user_clone_gpt.py" \
  --prompt-file "$USER_CLONE_GPT_PROMPT" \
  -o "$USER_CLONE_GPT_OUT" \
  --timeout 600

# Normalize into NotebookLM source format
cat > "$PITCH_PATH" <<EOF
# ${COMPANY} — buyer pitch description

$(cat "$USER_CLONE_GPT_OUT")
EOF
```

Review User-Clone-GPT output (claims, no fabricated proof points). If a slide is weak or generic, refine with a follow-up using the `[response_id=...]` printed by the previous run:

```bash
python3 "$USER_CLONE_GPT_SKILL_DIR/scripts/ask_user_clone_gpt.py" \
  "Tighten slides 2–4 for ${COMPANY}'s stack; keep 3–5 bullets per slide." \
  --previous-response-id resp_... \
  -o "$USER_CLONE_GPT_OUT"
# Re-copy into PITCH_PATH if updated
```

Tell the user the layout was auto-generated and show `./output/${COMPANY_SLUG}_user_clone_gpt_deck_layout.md` before proceeding.

### Step 3: Write or confirm the pitch description file

**If Step 2.5 ran:** `PITCH_PATH` is already set — verify the file exists and skip manual authoring.

**If the user provided a layout:** point `PITCH_PATH` at their file, or write inline content:

```bash
PITCH_PATH="$WORK_DIR/${COMPANY_SLUG}_pitch.md"
cat > "$PITCH_PATH" <<'PITCH_EOF'
# <Company Name> — buyer pitch description

<paste the deck layout / pitch description here verbatim>
PITCH_EOF
```

The first line title helps the agent later identify this source.

### Step 4: Upload logo + pitch description as sources

```bash
LOGO_SRC=$(notebooklm source add "$LOGO_PATH" --title "${COMPANY} logo" -n "$NB_ID" --json | jq -r .source.id)
PITCH_SRC=$(notebooklm source add "$PITCH_PATH" --title "${COMPANY} pitch description" -n "$NB_ID" --json | jq -r .source.id)

notebooklm source wait "$LOGO_SRC"  -n "$NB_ID" --timeout 180
notebooklm source wait "$PITCH_SRC" -n "$NB_ID" --timeout 180
```

If `--title` is rejected by your installed version, drop the flag and rely on the filename-derived title.

### Step 5: Pick only the relevant sources

List all sources and choose the subset to use for this pitch:

```bash
notebooklm source list -n "$NB_ID" --json | jq '.sources[] | {id, title}'
```

**Include** (`SRC_IDS+=(...)` for each):

- `$LOGO_SRC` and `$PITCH_SRC` (just-uploaded for this company)
- Shared / core brand assets — anything whose title clearly describes your product or company (product overview, features, brand kit, mascot, **company logo**, pricing, public docs) **and** is not tied to a specific other company

The deck template tells NotebookLM to use **both** the buyer's and your **logos from sources** where branding fits—**not** inline beside bullets or body text, which often breaks and becomes placeholder text.

**Exclude:**

- Any source mentioning a *different* company's name (their logo, their pitch description, their case study)
- Outdated drafts or scratch notes

When a title is ambiguous, prefer asking the user over guessing.

```bash
SRC_IDS=( "$LOGO_SRC" "$PITCH_SRC" )
# Append any shared brand/product sources you identified:
# SRC_IDS+=( "$PRODUCT_OVERVIEW_SRC" "$COMPANY_LOGO_SRC" ... )
```

### Step 6: Render the deck prompt

```bash
DECK_PROMPT=$(python3 "$SKILL_DIR/scripts/render_prompt.py" \
  --template "$SKILL_DIR/deck-prompt-template.md" \
  --company "$COMPANY" \
  --deck-layout "$PITCH_PATH")
```

The template is the source of truth for deck style (the top-level `deck-prompt-template.md` is a mirror kept for compatibility; edit the skill copy) — edit `deck-prompt-template.md` to evolve it across all future pitches. Unsubstituted `<...>` placeholders (anywhere in the rendered text, including the layout) cause the renderer to exit 2 so the agent can't silently ship a half-rendered prompt. An empty company name or layout is also rejected.

### Step 7: Generate the slide deck

Build the `-s` args from the chosen source IDs and call generate. Slide-deck generation can take several minutes and is rate-limited by Google.

```bash
SRC_ARGS=(); for id in "${SRC_IDS[@]}"; do SRC_ARGS+=( -s "$id" ); done

notebooklm generate slide-deck "$DECK_PROMPT" \
  -n "$NB_ID" \
  --format detailed \
  "${SRC_ARGS[@]}" \
  --wait --retry 2
```

On `GENERATION_FAILED` / rate-limit errors, wait 5–10 minutes and retry once. If it still fails, fall back to the NotebookLM web UI (sources are already prepared).

If `notebooklm generate ... --wait` **times out** (~300s) while the task is still **`in_progress`**, capture the **task ID** from the error/log, then poll until completion:

```bash
notebooklm artifact poll "<TASK_ID>" -n "$NB_ID"
```

When **`status`** becomes **`completed`**, download with **`notebooklm download slide-deck ... -a "<ARTIFACT_ID>"`** using the task/artifact ID from the generate output. **Never use `--latest`** in batch runs — it downloads the wrong deck when multiple pitches share a notebook.

```bash
# gen_out holds the combined output of the generate command, e.g. gen_out=$(notebooklm generate ... 2>&1)
# Make sure the ID you pick is not the notebook or a source ID.
task_id=$(echo "$gen_out" | grep -oE '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}' | head -1)
notebooklm artifact wait "$task_id" -n "$NB_ID" --timeout 900
notebooklm download slide-deck "$PDF_RAW" -n "$NB_ID" -a "$task_id" --force
```

### Step 8: Download the deck as PDF

```bash
PDF_RAW="./output/${COMPANY_SLUG}_pitch.pdf"
notebooklm download slide-deck "$PDF_RAW" -n "$NB_ID" -a "$task_id" --force
```

### Step 9: Remove the watermark

```bash
PDF_CLEAN="./output/${COMPANY_SLUG}_pitch_cleaned.pdf"
bash "$SKILL_DIR/scripts/remove_watermark.sh" "$PDF_RAW" "$PDF_CLEAN"
```

If the watermark isn't fully removed, pass tighter margins (see `python3 ~/.local/share/notebooklm-watermark-remover/remover.py --help`).

### Step 10: Raster-merge for Canva (one flat image per page)

The watermark remover pastes a bitmap **on top of** the slide PDF. Canva (especially after **Presentation** resize) can treat that bitmap as a **separate layer** and nudge it. Re-render each page to a **single full-page image** inside a new PDF so there is **no separate overlay**—inpainting is baked into the pixels.

```bash
PDF_CANVA_FLAT="./output/${COMPANY_SLUG}_pitch_canva_flat.pdf"
bash "$SKILL_DIR/scripts/flatten_pdf_for_canva.sh" "$PDF_CLEAN" "$PDF_CANVA_FLAT"
# Optional quality tweak (default scale is 2.0):
# bash "$SKILL_DIR/scripts/flatten_pdf_for_canva.sh" "$PDF_CLEAN" "$PDF_CANVA_FLAT" -- --scale 2.5
```

Keep **`PDF_CLEAN`** as the editable intermediate (still vector-ish except for the patch). Use **`PDF_CANVA_FLAT`** only for **Canva import**; text is no longer selectable and links are dropped. The flat PDF is **much larger** than `PDF_CLEAN`; lower **`--scale`** (e.g. `1.5`) if upload size limits bite.

### Step 11: (Default) Public URL + Canva import

The Canva MCP's `import-design-from-url` tool accepts **only** a **public `https://` URL**, not local paths.

**Privacy gate (required):** the deck contains buyer-specific sales strategy. Uploading it to a public temporary host means a third party stores it and **anyone with the link can download it until it expires**. Before uploading, tell the user this and **ask for explicit confirmation**. Offer the alternatives:

- a private, short-lived **signed URL** from storage the user controls (e.g. an S3/GCS presigned URL), or
- skipping the upload and importing manually in Canva (**Create a design → Import file**), i.e. `SKIP_CANVA=1`.

Only if the user agrees to a public host: upload **`PDF_CANVA_FLAT`** (not `PDF_CLEAN`), verify the link returns **`application/pdf`** (not an HTML landing page), then call the MCP tool.

Example pattern (hosts vary; pick one that returns a direct PDF over HTTPS):

```bash
PDF_CANVA_FLAT="./output/${COMPANY_SLUG}_pitch_canva_flat.pdf"
# Example: tmpfiles.org API returns a browser URL; use the /dl/... URL for a direct PDF response.
RESP=$(curl -fsS -F "file=@${PDF_CANVA_FLAT}" https://tmpfiles.org/api/v1/upload)
PUBLIC_URL=$(echo "$RESP" | jq -r '.data.url' | sed 's|tmpfiles.org/|tmpfiles.org/dl/|')
# Verify: curl -sI "$PUBLIC_URL" | grep -i content-type   # expect application/pdf
```

Then invoke **Canva MCP** → **`import-design-from-url`** with:

- **`url`**: the direct HTTPS PDF URL (must satisfy the tool's schema, e.g. not a `canva.com/design/` link).
- **`name`**: a readable title, e.g. `"${COMPANY} — buyer pitch"`.

Record from the response:

- **`IMPORT_DESIGN_ID`** — design ID starting with `D` (11 chars), e.g. for follow-up tools.

Temporary file hosts expire; treat Canva as the durable copy once imported.

#### Canva MCP — connect / reconnect (toggle)

If Canva import fails with **`Not connected`**, **`error`**, auth errors, or the **`user-Canva`** server is missing from available tools, **do not skip Canva silently** — ask the user to toggle the server, then retry steps 11–12 once.

**User: toggle Canva MCP in Cursor**

1. Open **Cursor Settings** (`Cmd+Shift+J` on macOS, `Ctrl+Shift+J` on Windows/Linux).
2. Go to **Features → Model Context Protocol** (or search **MCP**).
3. Find **Canva** (server id **`user-Canva`**).
4. **Disconnect:** turn the toggle **off** and wait ~5 seconds.
5. **Connect:** turn the toggle **back on**.
6. If prompted, complete **OAuth / Sign in to Canva** again.
7. Confirm **Canva** shows as connected and tools like `import-design-from-url` appear under MCP tools in chat.

**Debug connection (optional):** **Output** panel (`Cmd+Shift+U`) → dropdown **MCP Logs** → look for Canva init/auth errors after toggling.

**Agent after user toggles**

1. If the failure looked like **auth** (401, unauthorized, token expired), call **`mcp_auth`** for **`user-Canva`** once, then retry.
2. Re-upload **`PDF_CANVA_FLAT`** to a fresh HTTPS URL (temp hosts expire), within the consent the user already gave.
3. Retry **`import-design-from-url`** → **`resize-design`** → **`get-design`**.
4. If it still fails after one toggle + retry, set **`SKIP_CANVA=1`**, deliver the PDF paths, and tell the user they can import manually in Canva (**Create a design → Import file**) or toggle again later.

**Opt out without fixing MCP:** user says "skip Canva" → set **`SKIP_CANVA=1`** and omit steps 10–12 unless they still want a flat PDF for another tool.

### Step 12: (Default) Convert to native Presentation (presenter mode)

Imported PDFs are not always stored as a first-class **Presentation** product. Resize to the **`presentation`** preset so standard **Present / presenter mode** applies.

Invoke **Canva MCP** → **`resize-design`** with:

- **`design_id`**: **`IMPORT_DESIGN_ID`** from step 11.
- **`design_type`**: `{ "type": "preset", "name": "presentation" }`.

Record from the response:

- **`PRESENTATION_DESIGN_ID`** — **new** design ID (keep this for editing and presenting). The original import may remain in your Canva account; you can delete it if redundant.

Call **`get-design`** on **`PRESENTATION_DESIGN_ID`** if you need fresh **`edit_url`** / **`view_url`** for the final report.

Publishing to a **custom domain** uses Canva's **Publish Website** UI and DNS; the MCP does not expose that—point users to [Publish Canva websites](https://www.canva.com/help/publishing-canva-websites/) when they ask.

### Step 13: Report

Tell the user:

- **Deck layout:** `./output/{COMPANY_SLUG}_user_clone_gpt_deck_layout.md` when Step 2.5 auto-generated it; otherwise note the user-supplied source.
- **PDFs:** `./output/{COMPANY_SLUG}_pitch_cleaned.pdf` (post–watermark-removal) and `./output/{COMPANY_SLUG}_pitch_canva_flat.pdf` (raster-merged; what Canva imported **should** be this file).
- **NotebookLM:** which sources were included (sanity-check).
- **Canva (when steps 11–12 ran):** **`IMPORT_DESIGN_ID`**, **`PRESENTATION_DESIGN_ID`**, and edit/view links for the **presentation** design—plus a note that only the presentation file should be used for presenter mode.

## Source filtering — practical rule of thumb

| Title pattern                                                            | Action  |
|--------------------------------------------------------------------------|---------|
| Contains `$COMPANY` (this pitch's target)                                | Include |
| Product overview, features, brand kit, mascot, company logo, public docs | Include |
| Pricing, case study (generic)                                            | Include |
| Contains a *different* company name (Stripe pitch, Datadog logo, …)      | Exclude |
| "Old draft", "scratch", "test", "WIP"                                    | Exclude |

When in doubt, ask the user to confirm the source list before generating.

## Files in this skill

- `deck-prompt-template.md` — Pitch deck template. Edit to evolve the deck style across all future pitches.
- `scripts/setup.sh` — One-time installer for a pinned `notebooklm-py` and the watermark remover at a pinned commit (`NOTEBOOKLM_PY_SPEC`, `NOTEBOOKLM_WM_REF`, `NOTEBOOKLM_WM_DIR` overrides).
- `scripts/render_prompt.py` — Substitutes `<Company Name>` and `<Deck Layout>` in the template. Fails loudly on any leftover `<...>` placeholders.
- `scripts/remove_watermark.sh` — Wrapper around `Albonire/notebooklm-watermark-remover` (installed by `setup.sh` into `~/.local/share/notebooklm-watermark-remover/`; runs in its venv). Usage: `remove_watermark.sh <input> [output] [-- <remover args>]`.
- `scripts/flatten_pdf_pages.py` — Raster-merge every PDF page into one full-page bitmap in a new PDF (`insert_image` + `keep_proportion=False`).
- `scripts/flatten_pdf_for_canva.sh` — Runs `flatten_pdf_pages.py` using the watermark-remover venv (PyMuPDF already installed there).

## Troubleshooting

- **Auth required** — `notebooklm login`, or `notebooklm auth refresh --quiet` to extend cookies.
- **`notebooklm login` fails with `Executable doesn't exist at .../Google Chrome for Testing.app`** — Playwright Chromium isn't installed in the same venv as `notebooklm`. Install it from inside that venv:
  ```bash
  # uv tool install (default in setup.sh)
  "$(dirname "$(readlink -f "$(command -v notebooklm)")")/playwright" install chromium
  # or (uv shorthand)
  uv tool run --from notebooklm-py playwright install chromium
  ```
  Then retry `notebooklm login`. As a no-Playwright alternative, import cookies from an already-logged-in browser: `notebooklm login --browser-cookies chrome` (requires `notebooklm-py[cookies]`).
- **Notebook not found** — `notebooklm list` to confirm exact title (case-sensitive).
- **Slide-deck generation fails with rate limit** — wait 5–10 min, retry with `--retry 2`. Fall back to web UI if it keeps failing.
- **Logo URL returns HTML instead of an image** — pick a direct HTTPS `.png`/`.jpg` URL from the page source, or fall back to a different search result.
- **Logos show as placeholder text in slides** — avoid logos inline with copy (see `deck-prompt-template.md`); re-generate, or tighten logo placement wording for that buyer.
- **Watermark not fully removed** — try `--margin-x 400 --margin-y 100` (see remover `--help`); or run the remover on the PPTX export instead (`download slide-deck --format pptx`).
- **Watermark patch / overlay shifted in Canva (or after Presentation resize)** — import **`${COMPANY_SLUG}_pitch_canva_flat.pdf`** (Step 10) instead of `*_cleaned.pdf`: each slide is one raster, so there is no separate inpaint layer to move.
- **Watermark patch leaves a smudge over real content** — the remover inpaints a fixed bottom-right ROI and struggles when there's real **text/logos/detail** under it. Tighten the bottom-right **watermark zone** guidance in `deck-prompt-template.md` for that buyer and regenerate, rather than tuning the remover.
- **Canva MCP missing / import fails / `Not connected`** — Ask the user to **toggle Canva off → on** in **Settings → Features → Model Context Protocol** (see **Canva MCP — connect / reconnect** under Step 11). Check **Output → MCP Logs** if it keeps failing. Retry import once after toggle; use **`mcp_auth`** for **`user-Canva`** on auth errors. Fallback: **`SKIP_CANVA=1`**, deliver `*_canva_flat.pdf`, or manual import in Canva UI.
- **Public PDF URL returns HTML** — use the host's **direct download** URL (e.g. tmpfiles **`/dl/`** path); verify with `curl -sI` → `content-type: application/pdf`.
- **`resize-design` fails** — report **`IMPORT_DESIGN_ID`** only; user can duplicate/convert inside Canva's UI.
- **User-Clone-GPT fails / no layout generated** — run `ask_user_clone_gpt.py --info` to check `.env` (`OPENAI_API_KEY` plus a voice configuration); see **user-clone-gpt** troubleshooting. Fall back to asking the user for a deck layout only if the API is unavailable.
- **Auto-generated layout too generic** — re-prompt with `--previous-response-id` with buyer-specific context from web research (Step 2 logo/domain hunt often surfaces useful product angles).

## References

- **user-clone-gpt** skill — `.agents/skills/user-clone-gpt/SKILL.md` (User-Clone-GPT / `ask_user_clone_gpt.py`)
- NotebookLM CLI/Python — https://github.com/teng-lin/notebooklm-py
- Watermark remover — https://github.com/Albonire/notebooklm-watermark-remover (branch `bibi`, pinned by commit in `setup.sh`)
- Canva MCP tools used here: `import-design-from-url`, `resize-design`, `get-design` (schemas under your Cursor MCP descriptors for **`user-Canva`**).
- Canva Help — publish / domains: https://www.canva.com/help/publishing-canva-websites/
