# Security

## Reporting a vulnerability

Please report security issues privately through GitHub's
**Security → Report a vulnerability** form on this repository rather than in a
public issue. Include steps to reproduce and the affected file or script.

## What these tools touch

Be aware of the following when running the skills and scripts:

- **Secrets.** `OPENAI_API_KEY` lives in `.env` at the project root (gitignored).
  It is only sent as a bearer token to `https://api.openai.com`. Never commit
  `.env`; use `.env.example` as the template. `ask_user_clone_gpt.py` reads
  only the project's `.env` (or `OPENAI_ENV_FILE`) and refuses to send
  `.env*`, `*.pem` or `*.key` files as prompts.
- **Third-party code.** `setup.sh` installs `notebooklm-py` from PyPI and clones
  [`Albonire/notebooklm-watermark-remover`](https://github.com/Albonire/notebooklm-watermark-remover)
  and installs its requirements in a dedicated venv. Both are pinned (a
  package version and a commit SHA). Review the upstream code before changing
  the pins. Note that the remover's own `requirements.txt` uses lower-bound
  version ranges.
- **Browser credentials.** `notebooklm login` stores Google session cookies
  locally (managed by `notebooklm-py`).
- **Data sent to third parties.** Buyer research prompts go to OpenAI
  (background mode requires `store: true`, so OpenAI stores prompts and
  responses server-side under your account's retention settings); sources
  and decks go to Google NotebookLM; the optional Canva import requires a
  **public** URL for the PDF. The pitch-deck skill asks for explicit consent
  before uploading a deck to a public temporary host, because anyone with the
  link can download it until it expires. Prefer a private, short-lived signed
  URL from storage you control, or import into Canva manually.
- **Local files.** Batch working files are written to `output/work/<slug>/`
  with mode 700; outputs go to `output/` (gitignored).
