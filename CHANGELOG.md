# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). The current version is in
[`VERSION`](VERSION).

## [2.0.0] - 2026-11-20

### License
- The project is now licensed under the Apache License 2.0 (`LICENSE`).

### Breaking changes

- **User-Clone-GPT now uses the OpenAI Responses API.** OpenAI shut down the
  Assistants API (`/assistants`, `/threads`, `/runs`) on 2026-08-26, so 1.x of
  `ask_user_clone_gpt.py` can no longer work. 2.0.0 sends requests to
  `POST /v1/responses` (background mode, polled until done).
  - `OPENAI_ASSISTANT_ID` is no longer used. Configure your voice with one or
    more of `OPENAI_INSTRUCTIONS_FILE`, `OPENAI_VECTOR_STORE_IDS` and
    `OPENAI_PROMPT_ID` (see [`.env.example`](.env.example)). The script exits
    with a migration message if only `OPENAI_ASSISTANT_ID` is set.
  - Follow-ups use response IDs (`resp_...`) with `--previous-response-id`.
    `--thread-id` is still accepted as an alias but `thread_...` IDs are
    rejected. The CLI now prints `[response_id=...]` to stderr instead of
    `[thread_id=...]`.
  - `--info` prints the resolved, non-secret local configuration instead of
    the remote assistant object.
  - `--ensure-model-only` no longer changes anything remotely: it validates the
    configuration and prints the model. `--skip-model-check` is a no-op. The
    automatic "update the assistant's model with fallbacks" behaviour is gone,
    since there is no assistant object to update.
  - Every mode, including `--info` and `--ensure-model-only`, now fails
    (exit 2) unless `OPENAI_API_KEY` **and** a voice configuration are set.
    `--ensure-model-only` therefore succeeds or fails on local configuration
    alone; `run_batch_decks.sh` uses it as its fail-fast check.
  - `.env` discovery changed: the script uses `<project root>/.env`, where the
    project root is the first directory above the script that contains
    `.agents` or `.git`. 1.x walked upward for *any* `.env`. If you installed
    the skill somewhere else (for example copied it to `~/.claude/skills/`),
    the old upward search no longer finds your `.env`: set
    `OPENAI_ENV_FILE=/path/to/.env` (or export the variables directly).
- **`render_prompt.py`** now rejects an empty `--company` or an empty deck
  layout (exit 2) instead of rendering a useless prompt.
- **`run_batch_decks.sh`** keeps working files (prompts, pitch files, logos)
  in a private `output/work/<slug>/` directory (mode 700) instead of the
  shared, predictable `/tmp/pitch-deck/<slug>/`. Move any pre-placed logos to
  `output/work/<slug>/<slug>_logo.png` (or set `WORK_ROOT`).

#### Migrating from 1.x

1. Copy your old assistant's instructions (from the OpenAI dashboard if it is
   still shown there, or from your own records) into a file in this repo (for example `voice/instructions.md`; keep it out of
   git if it is private). Set `OPENAI_INSTRUCTIONS_FILE` to that path.
2. Note the vector store ID(s) the assistant used for file search
   (`vs_...`) and set `OPENAI_VECTOR_STORE_IDS`. Vector stores still work with
   the Responses API.
3. Optionally, create a reusable prompt in the dashboard and set
   `OPENAI_PROMPT_ID`.
4. Remove `OPENAI_ASSISTANT_ID` and run
   `python3 .agents/skills/user-clone-gpt/scripts/ask_user_clone_gpt.py --info`
   to check the configuration.
5. Replace `--thread-id thread_...` in your notes or scripts with
   `--previous-response-id resp_...` (the ID printed after each run).
6. If the skill lives outside a project directory (no `.agents` or `.git`
   above it), set `OPENAI_ENV_FILE` to your `.env`.
7. Existing `setup.sh` installs: rerun `setup.sh`. If your watermark-remover
   checkout (`~/.local/share/notebooklm-watermark-remover` by default) has
   local edits, setup now stops instead of discarding them with
   `git reset --hard`; commit/stash them or delete the checkout first. The
   checkout is moved from the tip of branch `bibi` to the pinned commit.

### Security

- `setup.sh` pins the third-party watermark remover to a reviewed commit SHA
  (override with `NOTEBOOKLM_WM_REF`, which must be a full SHA) instead of
  following the moving `bibi` branch, verifies `HEAD` after checkout, and no
  longer runs `git reset --hard` (it refuses to touch a checkout that has local
  changes). `notebooklm-py` is pinned (`NOTEBOOKLM_PY_SPEC` to override).
- `.env` lookup is bounded to the project root (or `OPENAI_ENV_FILE`); a
  `.env` in a parent directory such as `$HOME` is no longer loaded.
- IDs that go into URL paths are validated, API error bodies are summarised
  and truncated, and the HTTP client refuses non-`https://` base URLs.
- The CLI refuses to send `.env*`, `*.pem` and `*.key` files as prompts and
  caps prompt files at 1 MB. Added `--prompt-file` for explicit file input.
- The pitch-deck skill now requires explicit user consent before uploading a
  deck to a public temporary file host for the Canva import, and the logo
  download uses HTTPS-only, size- and time-limited `curl` settings.
- `.gitignore` also covers `.env.*`, keys and tool caches; added
  `.env.example` and `SECURITY.md`.

### Added

- Retry with exponential backoff (honouring `Retry-After`) for HTTP 429 on all
  requests and for 5xx / network errors on idempotent requests.
- `ask_user_clone_gpt.py --version`, `--prompt-file` (`-` for stdin), and
  clean error messages (no tracebacks) for configuration, network and timeout
  errors. `-o` creates missing parent directories.
- `run_batch_decks.sh`: `COMPANIES_FILE`, `OUTPUT_DIR`, `WORK_ROOT`,
  `BATCH_SLEEP_SEC` and `BATCH_FAIL_SLEEP_SEC` settings; checks for `notebooklm`,
  `jq` and `python3` up front; can be sourced for testing without side effects.
- `flatten_pdf_pages.py`: input checks, `--scale` upper bound (8), clean errors
  for unreadable PDFs; `setup.sh` installs PyMuPDF explicitly in the remover
  venv.
- Test suite (pytest, no network access), ruff and shellcheck configuration,
  and a GitHub Actions workflow (Python 3.10 to 3.14, pinned action SHAs,
  read-only token).
- `CHANGELOG.md`, `VERSION`, `SECURITY.md`, `.env.example`,
  `requirements-dev.txt`.

### Fixed

- `run_batch_decks.sh`: a failing step inside a company's run (source upload
  or wait, download, watermark removal, Canva flattening, User-Clone-GPT) no
  longer counts as success. Because `run_one_deck` runs inside
  `if pdf=$(...)`, bash ignored `set -e` there, so 1.x recorded such failures
  as a success with a missing PDF. Each step is now checked explicitly and
  every output PDF must exist and be non-empty. The artifact ID scraped from
  `notebooklm generate` output is logged.
- `ask_user_clone_gpt.py`: connection resets and truncated bodies while
  reading a response are reported as clean network errors (and retried for
  GET) instead of a traceback; a background response is cancelled when
  polling fails permanently, not only on timeout.
- `run_batch_decks.sh`: a cached layout no longer leaves the pitch file
  missing; stdout of the download/clean/flatten steps no longer leaks into the
  returned PDF path; empty `SHARED_SRC_IDS` no longer aborts on bash 3.2
  (macOS); notebook and source IDs are not mistaken for the artifact ID;
  company names that slugify to nothing get a stable fallback slug.
- `render_prompt.py`: placeholders are substituted in one pass, so text inside
  the company name or layout is never substituted again; missing files give a
  clean error.
- The top-level `deck-prompt-template.md` had drifted from the skill's copy; it
  is now an exact mirror (enforced by a test). The skill copy is canonical.

### Docs

- README rewritten: accurate prerequisites (including `jq`), configuration,
  batch usage, testing, security and privacy notes, and an up-to-date layout.
- Both `SKILL.md` files updated for the Responses API and the new safety steps.

## [1.0.0] - initial commit

- First published version: `pitch-deck-generator` and `user-clone-gpt` agent
  skills, batch script and helpers (OpenAI Assistants API based). Retroactively
  labelled 1.0.0 so that the 2.0.0 breaking changes are visible.
