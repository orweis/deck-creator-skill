# Deck Creator

Automation for building buyer-specific pitch decks with **NotebookLM** (generation + PDF download), optional **watermark removal**, and optional **Canva** import for presenter-ready slides via MCP. Slide layouts can be drafted in your own voice by **User-Clone-GPT** (OpenAI Responses API).

The workflow is defined as agent skills under [`.agents/skills/`](.agents/skills/) (Cursor or any agent that can run shell commands and call MCP tools).

> **Upgrading from 1.x?** Version 2.0.0 moves User-Clone-GPT from the retired OpenAI Assistants API to the Responses API. `OPENAI_ASSISTANT_ID` is no longer used, `.env` is only read from the project root (set `OPENAI_ENV_FILE` for relocated installs), and `setup.sh` now pins the watermark remover and refuses to overwrite local edits. See [Migrating from 1.x](CHANGELOG.md#migrating-from-1x).

## Prerequisites

- **macOS or Linux** with `bash`, `python3` (3.10+), `git`, `curl` and **`jq`**
- **Google account** with access to [NotebookLM](https://notebooklm.google.com/)
- **Cursor** (or another agent environment that can run the skill and call MCP tools)
- **`uv`** (recommended), **`pipx`**, or **`pip`** for installing the NotebookLM CLI (see setup script)
- Optional: **Canva** account for the Canva import + presentation resize steps
- Optional: **OpenAI API key** plus your voice configuration, for auto-generated deck layouts

The Python scripts use only the standard library, except `flatten_pdf_pages.py`, which needs PyMuPDF (installed into the watermark-remover venv by `setup.sh`).

## Agent skills

Skills live under **[`.agents/skills/`](.agents/skills/)** and are available to all agents in this repo. See [`.agents/AGENTS.md`](.agents/AGENTS.md) for the index.

| Skill | Purpose |
|-------|---------|
| [`pitch-deck-generator`](.agents/skills/pitch-deck-generator/SKILL.md) | NotebookLM pitch deck generation, watermark removal, Canva import |
| [`user-clone-gpt`](.agents/skills/user-clone-gpt/SKILL.md) | Content in your voice (pitch copy, emails, deck layouts) via the OpenAI Responses API |

Optional: symlink a skill into **`~/.cursor/skills/`** if you want it available in other workspaces:

```bash
mkdir -p ~/.cursor/skills
ln -snf "$(pwd)/.agents/skills/pitch-deck-generator" ~/.cursor/skills/pitch-deck-generator
ln -snf "$(pwd)/.agents/skills/user-clone-gpt" ~/.cursor/skills/user-clone-gpt
```

Restart Cursor or reload the window if a skill does not appear after adding it.

## Configuration (User-Clone-GPT)

Copy the template and fill it in. `.env` is gitignored; never commit real keys.

```bash
cp .env.example .env
```

| Variable | Required | Meaning |
|----------|----------|---------|
| `OPENAI_API_KEY` | yes | OpenAI API key |
| `OPENAI_INSTRUCTIONS_FILE` | one of these three | File with your voice/system instructions (absolute, or relative to the repo root) |
| `OPENAI_VECTOR_STORE_IDS` | one of these three | Comma-separated `vs_...` IDs used for `file_search` (your knowledge base) |
| `OPENAI_PROMPT_ID` / `OPENAI_PROMPT_VERSION` | one of these three | Reusable prompt from the OpenAI dashboard |
| `OPENAI_MODEL` | no | Model to run (default `gpt-5.5`); model names change, check OpenAI's model list |
| `OPENAI_RUN_TIMEOUT` | no | Seconds to wait for a response (default 300) |
| `OPENAI_ENV_FILE` | no | Use this env file instead of `<repo>/.env` |

Check the configuration without calling the API:

```bash
python3 .agents/skills/user-clone-gpt/scripts/ask_user_clone_gpt.py --info
```

Main CLI usage (`--help` lists everything):

```bash
CLI=.agents/skills/user-clone-gpt/scripts/ask_user_clone_gpt.py
python3 "$CLI" --prompt-file prompt.md -o output/acme_layout.md   # prompt from a file
python3 "$CLI" "Three talking points for Acme's CISO"              # inline prompt
python3 "$CLI" "Shorten slide 3" --previous-response-id resp_...   # follow-up
```

The response ID for follow-ups is printed to stderr as `[response_id=...]`. `scripts/openai_assistant.py` is a compatibility alias for the same CLI.

## NotebookLM CLI: install and login

1. **Run the one-time setup script.** It installs a pinned `notebooklm-py`, Playwright Chromium for browser login, and the third-party watermark remover pinned to a reviewed commit:

   ```bash
   SKILL_DIR="$(pwd)/.agents/skills/pitch-deck-generator"
   bash "$SKILL_DIR/scripts/setup.sh"
   ```

   Overrides: `NOTEBOOKLM_PY_SPEC`, `NOTEBOOKLM_WM_DIR`, `NOTEBOOKLM_WM_REF` (a full commit SHA). The script is idempotent and refuses to overwrite a remover checkout that has local changes.

2. **Sign in to NotebookLM** (opens a browser flow on first use):

   ```bash
   notebooklm login
   ```

3. **Verify**:

   ```bash
   notebooklm status
   notebooklm list --json
   ```

If `notebooklm login` fails because Chromium is missing, see **Troubleshooting** in [`SKILL.md`](.agents/skills/pitch-deck-generator/SKILL.md) (Playwright must be installed in the same environment as the `notebooklm` binary).

## Canva MCP: setup and login

The skill **defaults** to importing the cleaned PDF into Canva using MCP tools such as `import-design-from-url` and `resize-design`. Canva can only import from a **public URL**, so the agent asks for your explicit consent before uploading the deck anywhere public (see [Security and privacy](#security-and-privacy)). Skip Canva by asking the agent to skip it or by setting `SKIP_CANVA=1` when following the skill manually.

1. **Enable the Canva MCP in Cursor.** Open **Cursor Settings → Tools & MCP → MCP servers**, and make sure the **Canva** server is added and enabled (it may appear as `user-Canva` or similar).
2. **Complete OAuth / connection.** On first use, Cursor prompts you to connect or sign in to Canva. If tools fail with auth errors, use **Reconnect** / **Login** on the MCP server entry.
3. **Sanity check.** Ask the agent to call a read-only Canva tool (for example listing or resolving a design) before a full run.

If the Canva MCP is missing or fails, the skill still delivers the **cleaned PDF** locally.

## Prompting an agent to use the skill

The skill activates when your request clearly asks for a **buyer pitch deck** for a **named company**. You must supply at least:

- **Company name**
- **Deck layout / pitch description** (bullet slide list, angles, proof points; inline or a file path), *or* let the agent auto-generate it via User-Clone-GPT

Optional extras: **NotebookLM notebook title** (default `Pitch Decks`), **logo URL**, **skip Canva**.

### Example prompts

```text
Create a pitch deck for Twilio using the pitch-deck-generator skill.
Company: Twilio.
Notebook: Pitch Decks.
Deck layout:
- Slide 1: Title — Twilio pitch
- Slide 2: The problem — API-first teams need fine-grained authorization at scale
- … (add your bullets)
```

```text
Build a buyer pitch for Acme Corp. Use the skill end-to-end including Canva presenter mode.
Here's the deck outline: <paste markdown or attach file>.
```

```text
Generate a buyer pitch for Stripe with NotebookLM only—skip Canva. Deck description is in ./notes/stripe-pitch.md
```

For the full operational checklist, see [`.agents/skills/pitch-deck-generator/SKILL.md`](.agents/skills/pitch-deck-generator/SKILL.md).

## Batch generation

[`scripts/run_batch_decks.sh`](scripts/run_batch_decks.sh) generates decks for several companies in one run (layout via User-Clone-GPT → NotebookLM → watermark removal → flattened PDF). Edit the `COMPANIES` / `SHARED_SRC_IDS` arrays at the top, or pass a file:

```bash
cat > companies.txt <<'EOF'
# Display Name|extra context for User-Clone-GPT
Acme Corp|Enterprise SaaS platform; multi-tenant controls matter.
Example Inc|Developer tools company with a growing enterprise motion.
EOF
COMPANIES_FILE=companies.txt bash scripts/run_batch_decks.sh
```

| Variable | Default | Meaning |
|----------|---------|---------|
| `NB_NAME` | `Pitch Decks` | NotebookLM notebook title |
| `COMPANIES_FILE` | unset | One `Name|context` per line; replaces the `COMPANIES` array |
| `OUTPUT_DIR` | `output/` | PDFs, layouts and `batch_decks_results.txt` |
| `WORK_ROOT` | `output/work/` | Private (mode 700) per-company working files; put a logo at `<WORK_ROOT>/<slug>/<slug>_logo.png` to upload it |
| `BATCH_SLEEP_SEC` / `BATCH_FAIL_SLEEP_SEC` | `60` / `300` | Pauses between companies / after a failure (NotebookLM rate limits) |
| `FORCE_DECK=1` / `FORCE_USER_CLONE_GPT=1` | off | Regenerate even if outputs exist |

## Security and privacy

- Keep secrets in `.env` only. The CLI reads the project's `.env` (never a parent directory's) and will not send `.env`/key files as prompts.
- `setup.sh` runs third-party code (the watermark remover and its Python dependencies). Both it and `notebooklm-py` are pinned; review upstream before changing the pins.
- Buyer research goes to OpenAI and decks go to NotebookLM. User-Clone-GPT runs in OpenAI's background mode, which requires `store: true`, so prompts and responses are stored server-side by OpenAI under your account's retention settings. The Canva import needs a **public** URL: anyone with the link can read the deck until it expires. The agent asks first; prefer a private signed URL you control, or import into Canva manually.

See [SECURITY.md](SECURITY.md) for details and how to report a vulnerability.

## Development and testing

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
ruff check . && ruff format --check .
shellcheck -x scripts/*.sh .agents/skills/pitch-deck-generator/scripts/*.sh
python -m pytest
```

The test suite never calls OpenAI, NotebookLM or Canva: HTTP is faked and external CLIs are stubbed. CI runs the same steps on Python 3.10 to 3.14 ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Repository layout

| Path | Purpose |
|------|---------|
| `.agents/AGENTS.md` | Index of project agent skills |
| `.agents/skills/pitch-deck-generator/SKILL.md` | Pitch deck workflow |
| `.agents/skills/pitch-deck-generator/deck-prompt-template.md` | Deck prompt template (canonical copy) |
| `.agents/skills/pitch-deck-generator/scripts/setup.sh` | One-time installer (pinned `notebooklm-py` + watermark remover) |
| `.agents/skills/pitch-deck-generator/scripts/render_prompt.py` | Fills `<Company Name>` / `<Deck Layout>` in the template |
| `.agents/skills/pitch-deck-generator/scripts/remove_watermark.sh` | Runs the watermark remover in its venv |
| `.agents/skills/pitch-deck-generator/scripts/flatten_pdf_for_canva.sh`, `flatten_pdf_pages.py` | Raster-merge each PDF page for stable Canva imports |
| `.agents/skills/user-clone-gpt/SKILL.md` | User-Clone-GPT content workflow |
| `.agents/skills/user-clone-gpt/scripts/ask_user_clone_gpt.py` | Responses API CLI |
| `scripts/run_batch_decks.sh` | Batch deck generation |
| `scripts/openai_assistant.py` | Compatibility alias for `ask_user_clone_gpt.py` |
| `deck-prompt-template.md` | Mirror of the skill template, kept for compatibility (a test keeps them identical) |
| `tests/` | pytest suite |
| `output/` | Generated PDFs and working files (gitignored) |
| `CHANGELOG.md`, `VERSION` | Release history and current version |

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
