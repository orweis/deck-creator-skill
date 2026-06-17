#!/usr/bin/env bash
# Batch pitch decks for multiple buyers via NotebookLM + User-Clone-GPT.
#
# Configure:
#   COMPANIES array — "Display Name|extra context for User-Clone-GPT"
#   SHARED_SRC_IDS array — NotebookLM source IDs for shared brand/product assets
#   NB_NAME — NotebookLM notebook title (default: Pitch Decks)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILL_DIR="$ROOT/.agents/skills/pitch-deck-generator"
USER_CLONE_GPT_SKILL_DIR="$ROOT/.agents/skills/user-clone-gpt"
NB_NAME="${NB_NAME:-Pitch Decks}"
OUTPUT_DIR="$ROOT/output"
mkdir -p "$OUTPUT_DIR"

# Companies: "Display Name|extra context for User-Clone-GPT"
COMPANIES=(
  "Acme Corp|Enterprise SaaS platform; likely needs fine-grained authorization and multi-tenant controls."
  "Example Inc|Developer tools company; API-first product with growing enterprise motion."
)

# Shared brand/product sources (set your NotebookLM source IDs here)
SHARED_SRC_IDS=(
  # "source-id-1"   # product overview
  # "source-id-2"   # company logo
)

NB_ID=$(notebooklm list --json \
  | jq -r --arg t "$NB_NAME" '.notebooks[] | select(.title == $t) | .id' \
  | head -n1)
if [ -z "$NB_ID" ]; then
  echo "Notebook '$NB_NAME' not found" >&2
  exit 1
fi

generate_user_clone_gpt_layout() {
  local company="$1"
  local extra_context="$2"
  local slug
  slug=$(echo "$company" | tr '[:upper:] ' '[:lower:]_' | tr -cd '[:alnum:]_-')
  local work_dir="/tmp/pitch-deck/${slug}"
  local pitch_path="$work_dir/${slug}_pitch.md"
  local prompt_path="$work_dir/${slug}_user_clone_gpt_prompt.md"
  local layout_out="$OUTPUT_DIR/${slug}_user_clone_gpt_deck_layout.md"
  mkdir -p "$work_dir"

  if [ -f "$layout_out" ] && [ "${FORCE_USER_CLONE_GPT:-0}" != "1" ]; then
    echo "[$company] User-Clone-GPT layout exists: $layout_out" >&2
    echo "$pitch_path"
    return 0
  fi

  cat > "$prompt_path" <<EOF
Write in the voice and style configured for this assistant.

**Content type:** buyer research + pitch deck layout
**Audience:** ${company}

**Task — two parts:**

1. **Company research (brief):** What does ${company} do? Who are their customers? What challenges likely matter for their product and GTM? Note public signals. Keep to 5–8 bullets — factual, no invented metrics or customer names.

2. **Deck layout:** Produce a **10–12 slide** deck layout for pitching to **${company}**. Format exactly as markdown:
   - One \`## Slide N: Title\` heading per slide
   - **3–5 bullets** per slide (concise, buyer-specific)
   - Lead with ${company}'s likely pain, map to your product value, include proof points, close with next steps / CTA
   - Weave research from part 1 — do not paste as a separate appendix unless one slide is "Why now for ${company}"

**Buyer-specific context:**
${extra_context}

**Constraints:**
- Match tone from prior transcripts and approved copy in the assistant's knowledge base.
- Cite product documentation with links where relevant.
- Do not invent customer logos, metrics, case studies, or certifications.

Output **only** the deck layout section (part 2) as the main body. You may include a short \`## Buyer context\` block (≤8 bullets) at the top if it helps the slide narrative.
EOF

  echo "[$company] Generating User-Clone-GPT layout..." >&2
  python3 "$USER_CLONE_GPT_SKILL_DIR/scripts/ask_user_clone_gpt.py" --ensure-model-only >&2
  python3 "$USER_CLONE_GPT_SKILL_DIR/scripts/ask_user_clone_gpt.py" "$prompt_path" \
    -o "$layout_out" \
    --timeout 600 >&2

  cat > "$pitch_path" <<PITCHEOF
# ${company} — buyer pitch description

$(cat "$layout_out")
PITCHEOF

  echo "$pitch_path"
}

find_logo() {
  local company="$1"
  local slug="$2"
  local work_dir="/tmp/pitch-deck/${slug}"
  local logo_path="$work_dir/${slug}_logo.png"
  mkdir -p "$work_dir"

  if [ -f "$logo_path" ] && [ "${FORCE_LOGO:-0}" != "1" ]; then
    echo "$logo_path"
    return 0
  fi

  echo "WARN: No logo for $company — add LOGO_URL lookup or supply manually" >&2
  echo ""
}

run_one_deck() {
  local company="$1"
  local extra_context="$2"
  local slug
  slug=$(echo "$company" | tr '[:upper:] ' '[:lower:]_' | tr -cd '[:alnum:]_-')
  local pdf_raw="$OUTPUT_DIR/${slug}_pitch.pdf"
  local pdf_clean="$OUTPUT_DIR/${slug}_pitch_cleaned.pdf"
  local pdf_flat="$OUTPUT_DIR/${slug}_pitch_canva_flat.pdf"

  if [ -f "$pdf_clean" ] && [ "${FORCE_DECK:-0}" != "1" ]; then
    echo "[$company] Clean PDF exists: $pdf_clean — skipping generation" >&2
    echo "$pdf_clean"
    return 0
  fi

  rm -f "$pdf_raw" "$pdf_clean" "$pdf_flat" 2>/dev/null || true

  local pitch_path
  pitch_path=$(generate_user_clone_gpt_layout "$company" "$extra_context")
  local logo_path
  logo_path=$(find_logo "$company" "$slug")

  echo "[$company] Uploading sources..." >&2
  local logo_src="" pitch_src=""
  if [ -n "$logo_path" ] && [ -f "$logo_path" ]; then
    logo_src=$(notebooklm source add "$logo_path" --title "${company} logo" -n "$NB_ID" --json | jq -r .source.id)
    notebooklm source wait "$logo_src" -n "$NB_ID" --timeout 180
  fi
  pitch_src=$(notebooklm source add "$pitch_path" --title "${company} pitch description" -n "$NB_ID" --json | jq -r .source.id)
  notebooklm source wait "$pitch_src" -n "$NB_ID" --timeout 180

  local src_ids=("$pitch_src")
  [ -n "$logo_src" ] && src_ids+=("$logo_src")
  src_ids+=("${SHARED_SRC_IDS[@]}")

  echo "[$company] Rendering prompt (${#src_ids[@]} sources)..." >&2
  local deck_prompt
  deck_prompt=$(python3 "$SKILL_DIR/scripts/render_prompt.py" \
    --template "$SKILL_DIR/deck-prompt-template.md" \
    --company "$company" \
    --deck-layout "$pitch_path") || { echo "[$company] render_prompt failed" >&2; return 1; }

  local src_args=()
  for id in "${src_ids[@]}"; do src_args+=( -s "$id" ); done

  echo "[$company] Generating slide deck (may take several minutes)..." >&2
  local gen_out task_id
  gen_out=$(notebooklm generate slide-deck "$deck_prompt" \
    -n "$NB_ID" \
    --format detailed \
    "${src_args[@]}" \
    --wait --retry 2 2>&1) || true
  echo "$gen_out" >&2

  task_id=$(echo "$gen_out" | grep -oE '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}' | head -1)
  if [ -z "$task_id" ]; then
    echo "[$company] ERROR: no task/artifact ID in generate output" >&2
    return 1
  fi

  if echo "$gen_out" | grep -qE "timed out|in_progress"; then
    echo "[$company] Waiting for artifact $task_id to complete..." >&2
    notebooklm artifact wait "$task_id" -n "$NB_ID" --timeout 900 >&2 || {
      echo "[$company] ERROR: artifact $task_id did not complete" >&2
      return 1
    }
  fi

  echo "[$company] Downloading PDF (artifact $task_id)..." >&2
  notebooklm download slide-deck "$pdf_raw" -n "$NB_ID" -a "$task_id" --force

  echo "[$company] Removing watermark..." >&2
  bash "$SKILL_DIR/scripts/remove_watermark.sh" "$pdf_raw" "$pdf_clean"

  echo "[$company] Flattening for Canva..." >&2
  bash "$SKILL_DIR/scripts/flatten_pdf_for_canva.sh" "$pdf_clean" "$pdf_flat"

  echo "[$company] Done: $pdf_clean" >&2
  echo "$pdf_clean"
}

python3 "$USER_CLONE_GPT_SKILL_DIR/scripts/ask_user_clone_gpt.py" --ensure-model-only

echo "Shared brand sources: ${#SHARED_SRC_IDS[@]}"
echo "Processing ${#COMPANIES[@]} companies..."

RESULTS_FILE="$OUTPUT_DIR/batch_decks_results.txt"
: > "$RESULTS_FILE"

for entry in "${COMPANIES[@]}"; do
  company="${entry%%|*}"
  context="${entry#*|}"
  echo "" >&2
  echo "========== $company ==========" >&2
  if pdf=$(run_one_deck "$company" "$context"); then
    echo "$company|$pdf" >> "$RESULTS_FILE"
  else
    echo "$company|FAILED" >> "$RESULTS_FILE"
    echo "[$company] FAILED — continuing with next company"
    sleep 300
  fi
  sleep 60
done

echo ""
echo "All done. Results: $RESULTS_FILE"
cat "$RESULTS_FILE"
