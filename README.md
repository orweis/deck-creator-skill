# Deck Creator

Automation for building buyer-specific pitch decks with **NotebookLM** (generation + PDF download), optional **watermark removal**, and optional **Canva** import for presenter-ready slides via MCP.

The workflow is defined in the Cursor Agent skill under [`.agents/skills/pitch-deck-generator/`](.agents/skills/pitch-deck-generator/).

## Prerequisites

- **macOS or Linux** with `bash`, `python3`, `git`, and `curl`
- **Google account** with access to [NotebookLM](https://notebooklm.google.com/)
- **Cursor** (or another agent environment that can run the skill and call MCP tools)
- Optional: **`uv`**, **`pipx`**, or **`pip`** for installing the NotebookLM CLI (see setup script)
- Optional: **Canva** account if you want the default Canva import + presentation resize steps
- Optional: **OpenAI API key** and **User-Clone-GPT assistant** if you want auto-generated deck layouts

## Agent skills

Skills live under **[`.agents/skills/`](.agents/skills/)** and are available to all agents in this repo. See [`.agents/AGENTS.md`](.agents/AGENTS.md) for the index.

| Skill | Purpose |
|-------|---------|
| [`pitch-deck-generator`](.agents/skills/pitch-deck-generator/SKILL.md) | NotebookLM pitch deck generation, watermark removal, Canva import |
| [`user-clone-gpt`](.agents/skills/user-clone-gpt/SKILL.md) | User-Clone-GPT content generation (pitch copy, emails, deck layouts) |

Optional: symlink a skill into **`~/.cursor/skills/`** if you want it available in other workspaces:

```bash
mkdir -p ~/.cursor/skills
ln -snf "$(pwd)/.agents/skills/pitch-deck-generator" ~/.cursor/skills/pitch-deck-generator
ln -snf "$(pwd)/.agents/skills/user-clone-gpt" ~/.cursor/skills/user-clone-gpt
```

Restart Cursor or reload the window if a skill does not appear after adding it.

## Environment variables

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=sk-...
OPENAI_ASSISTANT_ID=asst_...    # your User-Clone-GPT assistant
OPENAI_MODEL=gpt-5.5            # optional; defaults to gpt-5.5
```

## NotebookLM CLI: install and login

1. **Run the one-time setup script** (installs `notebooklm-py`, Playwright Chromium for browser login, and the watermark-remover repo):

   ```bash
   SKILL_DIR="$(pwd)/.agents/skills/pitch-deck-generator"
   bash "$SKILL_DIR/scripts/setup.sh"
   ```

2. **Sign in to NotebookLM** (opens a browser flow on first use):

   ```bash
   notebooklm login
   ```

   If you are already authenticated, `notebooklm status` should succeed without prompting.

3. **Verify**:

   ```bash
   notebooklm status
   notebooklm list --json
   ```

If `notebooklm login` fails because Chromium is missing, see the **Troubleshooting** section in [`SKILL.md`](.agents/skills/pitch-deck-generator/SKILL.md) (Playwright must be installed in the same environment as the `notebooklm` binary).

## Canva MCP: setup and login

The skill **defaults** to importing the cleaned PDF into Canva using MCP tools such as `import-design-from-url` and `resize-design`. You can skip Canva by asking the agent to skip it or by setting `SKIP_CANVA=1` when following the skill manually.

1. **Enable the Canva MCP in Cursor**  
   Open **Cursor Settings → Tools & MCP → MCP servers**, and ensure the **Canva** server is added and enabled (the server name in your config may appear as `user-Canva` or similar).

2. **Complete OAuth / connection**  
   When you first use Canva tools, Cursor should prompt you to **connect** or **sign in** to Canva. Finish the browser authorization flow. If tools fail with auth errors, open the MCP server entry and use **Reconnect** / **Login** (wording depends on your Cursor version).

3. **Sanity check**  
   In chat, ask the agent to call a read-only Canva tool (for example listing or resolving a design) if you want to confirm the integration before running a full deck generation.

If the Canva MCP is missing or fails, the skill still delivers the **cleaned PDF** locally; only the Canva import and presentation resize steps are omitted.

## Prompting an agent to use the skill

The skill activates when your request clearly asks for a **buyer pitch deck** for a **named company**. You must supply at least:

- **Company name**
- **Deck layout / pitch description** (bullet slide list, angles, proof points—inline or path to a file), *or* let the agent auto-generate it via User-Clone-GPT

Optional extras you can mention up front:

- **NotebookLM notebook title** (default: `Pitch Decks`)
- **Logo URL** if you already have one (otherwise the agent will search)
- **Skip Canva** if you only want the PDF

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

For the full operational checklist (sources, generate, download, watermark, Canva), see [`.agents/skills/pitch-deck-generator/SKILL.md`](.agents/skills/pitch-deck-generator/SKILL.md).

## Repository layout

| Path | Purpose |
|------|---------|
| `.agents/AGENTS.md` | Index of project agent skills |
| `.agents/skills/pitch-deck-generator/SKILL.md` | Pitch deck workflow |
| `.agents/skills/pitch-deck-generator/deck-prompt-template.md` | Deck prompt template |
| `.agents/skills/pitch-deck-generator/scripts/` | `setup.sh`, `render_prompt.py`, `remove_watermark.sh` |
| `.agents/skills/user-clone-gpt/SKILL.md` | User-Clone-GPT content generation workflow |
| `.agents/skills/user-clone-gpt/scripts/` | `ask_user_clone_gpt.py` |
| `deck-prompt-template.md` | Top-level copy of the template (if present) |
| `output/` | Generated PDFs (gitignored by default) |

## License

MIT — customize and redistribute as needed.
