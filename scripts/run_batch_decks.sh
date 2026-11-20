#!/usr/bin/env bash
# Batch pitch decks for multiple buyers via NotebookLM + User-Clone-GPT.
#
# Configure (edit below or use the environment):
#   COMPANIES            array of "Display Name|extra context for User-Clone-GPT"
#   COMPANIES_FILE       optional file with one "Display Name|context" per line
#                        (blank lines and lines starting with # are ignored);
#                        when set it replaces the COMPANIES array
#   SHARED_SRC_IDS       array of NotebookLM source IDs for shared brand/product assets
#   NB_NAME              NotebookLM notebook title (default: Pitch Decks)
#   OUTPUT_DIR           where PDFs and layouts go (default: <repo>/output)
#   WORK_ROOT            per-company working files, created private (mode 700)
#                        (default: <OUTPUT_DIR>/work)
#   BATCH_SLEEP_SEC      pause between companies (default: 60)
#   BATCH_FAIL_SLEEP_SEC extra pause after a failure (default: 300)
#   FORCE_DECK=1         regenerate decks even if a cleaned PDF exists
#   FORCE_USER_CLONE_GPT=1  regenerate layouts even if one exists
#
# Logos: put a file at "$WORK_ROOT/<slug>/<slug>_logo.png" to have it uploaded.
#
# Requires: notebooklm (see setup.sh), jq, python3.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$ROOT/.agents/skills/pitch-deck-generator"
USER_CLONE_GPT_SKILL_DIR="$ROOT/.agents/skills/user-clone-gpt"
NB_NAME="${NB_NAME:-Pitch Decks}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT/output}"
WORK_ROOT="${WORK_ROOT:-$OUTPUT_DIR/work}"
BATCH_SLEEP_SEC="${BATCH_SLEEP_SEC:-60}"
BATCH_FAIL_SLEEP_SEC="${BATCH_FAIL_SLEEP_SEC:-300}"

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

UUID_RE='[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'

# Lowercase, spaces -> underscores, keep only [a-z0-9_-]. Never empty.
slugify() {
  local slug
  slug=$(printf '%s' "$1" | tr '[:upper:] ' '[:lower:]_' | LC_ALL=C tr -cd 'a-z0-9_-')
  if [ -z "$slug" ]; then
    slug="company_$(printf '%s' "$1" | cksum | cut -d' ' -f1)"
  fi
  printf '%s\n' "$slug"
}

# Create (if needed) a private per-company working directory and print it.
work_dir_for() {
  local dir="$WORK_ROOT/$1"
  (umask 077 && mkdir -p "$dir")
  chmod 700 "$WORK_ROOT" "$dir"
  printf '%s\n' "$dir"
}

load_companies_file() {
  local file="$1" line
  [ -f "$file" ] || { echo "COMPANIES_FILE not found: $file" >&2; return 1; }
  COMPANIES=()
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    COMPANIES+=("$line")
  done < "$file"
}

require_tools() {
  local tool missing=0
  for tool in "$@"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "Required tool not found on PATH: $tool" >&2
      missing=1
    fi
  done
  return "$missing"
}

generate_user_clone_gpt_layout() {
  local company="$1"
  local extra_context="$2"
  local slug work_dir
  slug=$(slugify "$company")
  work_dir=$(work_dir_for "$slug")
  local pitch_path="$work_dir/${slug}_pitch.md"
  local prompt_path="$work_dir/${slug}_user_clone_gpt_prompt.md"
  local layout_out="$OUTPUT_DIR/${slug}_user_clone_gpt_deck_layout.md"

  if [ -f "$layout_out" ] && [ "${FORCE_USER_CLONE_GPT:-0}" != "1" ]; then
    echo "[$company] User-Clone-GPT layout exists: $layout_out" >&2
  else
    # Unquoted delimiter: ${company}/${extra_context} are expanded once; their
    # contents are inserted literally (command substitutions inside the values
    # are NOT executed).
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
    python3 "$USER_CLONE_GPT_SKILL_DIR/scripts/ask_user_clone_gpt.py" \
      --prompt-file "$prompt_path" \
      -o "$layout_out" \
      --timeout 600 >&2
  fi

  # Always (re)build the pitch file so a cached layout still yields a source.
  {
    printf '# %s — buyer pitch description\n\n' "$company"
    cat "$layout_out"
  } > "$pitch_path"

  echo "$pitch_path"
}

# Print the path of a pre-supplied logo for this company, or nothing.
find_logo() {
  local company="$1"
  local slug="$2"
  local work_dir ext
  work_dir=$(work_dir_for "$slug")
  for ext in png jpg jpeg; do
    if [ -f "$work_dir/${slug}_logo.$ext" ]; then
      echo "$work_dir/${slug}_logo.$ext"
      return 0
    fi
  done
  echo "WARN: No logo for $company — place one at $work_dir/${slug}_logo.png" >&2
  echo ""
}

run_one_deck() {
  local company="$1"
  local extra_context="$2"
  local slug
  slug=$(slugify "$company")
  local pdf_raw="$OUTPUT_DIR/${slug}_pitch.pdf"
  local pdf_clean="$OUTPUT_DIR/${slug}_pitch_cleaned.pdf"
  local pdf_flat="$OUTPUT_DIR/${slug}_pitch_canva_flat.pdf"

  if [ -f "$pdf_clean" ] && [ "${FORCE_DECK:-0}" != "1" ]; then
    echo "[$company] Clean PDF exists: $pdf_clean — skipping generation" >&2
    echo "$pdf_clean"
    return 0
  fi

  rm -f "$pdf_raw" "$pdf_clean" "$pdf_flat"

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
  if [ -n "$logo_src" ]; then
    src_ids+=("$logo_src")
  fi
  # Safe expansion of a possibly empty array under `set -u` on bash < 4.4.
  src_ids+=(${SHARED_SRC_IDS[@]+"${SHARED_SRC_IDS[@]}"})

  echo "[$company] Rendering prompt (${#src_ids[@]} sources)..." >&2
  local deck_prompt
  deck_prompt=$(python3 "$SKILL_DIR/scripts/render_prompt.py" \
    --template "$SKILL_DIR/deck-prompt-template.md" \
    --company "$company" \
    --deck-layout "$pitch_path") || { echo "[$company] render_prompt failed" >&2; return 1; }

  local src_args=() id
  for id in "${src_ids[@]}"; do src_args+=( -s "$id" ); done

  echo "[$company] Generating slide deck (may take several minutes)..." >&2
  local gen_out gen_status=0 task_id
  # A --wait timeout exits non-zero but still prints the task ID, so capture
  # the status instead of aborting and decide below.
  gen_out=$(notebooklm generate slide-deck "$deck_prompt" \
    -n "$NB_ID" \
    --format detailed \
    "${src_args[@]}" \
    --wait --retry 2 2>&1) || gen_status=$?
  echo "$gen_out" >&2

  task_id=$(printf '%s\n' "$gen_out" | grep -oE "$UUID_RE" | grep -vxF -e "$NB_ID" "${src_ids[@]/#/-e}" | head -1 || true)
  if [ -z "$task_id" ]; then
    echo "[$company] ERROR: no task/artifact ID in generate output (exit $gen_status)" >&2
    return 1
  fi

  if [ "$gen_status" -ne 0 ] || printf '%s\n' "$gen_out" | grep -qE "timed out|in_progress"; then
    echo "[$company] Waiting for artifact $task_id to complete..." >&2
    notebooklm artifact wait "$task_id" -n "$NB_ID" --timeout 900 >&2 || {
      echo "[$company] ERROR: artifact $task_id did not complete" >&2
      return 1
    }
  fi

  echo "[$company] Downloading PDF (artifact $task_id)..." >&2
  notebooklm download slide-deck "$pdf_raw" -n "$NB_ID" -a "$task_id" --force >&2

  echo "[$company] Removing watermark..." >&2
  bash "$SKILL_DIR/scripts/remove_watermark.sh" "$pdf_raw" "$pdf_clean" >&2

  echo "[$company] Flattening for Canva..." >&2
  bash "$SKILL_DIR/scripts/flatten_pdf_for_canva.sh" "$pdf_clean" "$pdf_flat" >&2

  echo "[$company] Done: $pdf_clean" >&2
  echo "$pdf_clean"
}

main() {
  require_tools notebooklm jq python3
  mkdir -p "$OUTPUT_DIR"

  if [ -n "${COMPANIES_FILE:-}" ]; then
    load_companies_file "$COMPANIES_FILE"
  fi
  if [ "${#COMPANIES[@]}" -eq 0 ]; then
    echo "No companies configured." >&2
    exit 1
  fi

  NB_ID=$(notebooklm list --json \
    | jq -r --arg t "$NB_NAME" '.notebooks[] | select(.title == $t) | .id' \
    | head -n1)
  if [ -z "$NB_ID" ]; then
    echo "Notebook '$NB_NAME' not found" >&2
    exit 1
  fi

  # Fail fast on missing/invalid User-Clone-GPT configuration.
  python3 "$USER_CLONE_GPT_SKILL_DIR/scripts/ask_user_clone_gpt.py" --ensure-model-only

  echo "Shared brand sources: ${#SHARED_SRC_IDS[@]}"
  echo "Processing ${#COMPANIES[@]} companies..."

  local results_file="$OUTPUT_DIR/batch_decks_results.txt"
  : > "$results_file"

  local entry company context pdf
  for entry in "${COMPANIES[@]}"; do
    company="${entry%%|*}"
    if [[ "$entry" == *"|"* ]]; then
      context="${entry#*|}"
    else
      context=""
    fi
    echo "" >&2
    echo "========== $company ==========" >&2
    if pdf=$(run_one_deck "$company" "$context"); then
      echo "$company|$pdf" >> "$results_file"
    else
      echo "$company|FAILED" >> "$results_file"
      echo "[$company] FAILED — continuing with next company"
      sleep "$BATCH_FAIL_SLEEP_SEC"
    fi
    sleep "$BATCH_SLEEP_SEC"
  done

  echo ""
  echo "All done. Results: $results_file"
  cat "$results_file"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
