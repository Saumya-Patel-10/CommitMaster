# CommitMaster

A lightweight Windows tray app that watches your coding apps (VS Code, Cursor,
Antigravity, Bionic, ...). When you close them all, it asks **"Hey, you done
coding for that day?"** — and if you have uncommitted work, it groups your
changes, writes professional commit messages with your local LM Studio model,
shows you a preview, commits via `git`, and opens GitHub Desktop for review & push.

## How it works

```
┌─────────────┐   polls every 2s    ┌──────────────────┐
│ Coding apps │ ──────────────────▶ │ Session monitor  │──▶ all apps closed
└─────────────┘                     │  (tiny CPU/RAM)  │    for 2+ minutes
                                    └────────┬─────────┘
                     scans your project folders for dirty repos
                                             │
                                             ▼
                              "Done coding for that day?" (Yes/No)
                                             │ Yes + dirty repos
                                             ▼
                    LM Studio (local model) → conventional commit messages
                                             │
                                             ▼
                        Preview dialog (edit messages / cancel)
                                             │
                                             ▼
                     git add + git commit → GitHub Desktop opens → you push
```

## Setup

1. **Python 3.10+** and **Git for Windows** (`git` must be on PATH — Git Bash users already have it).
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. **LM Studio**: load a chat model and start the local server (Developer tab → *Start Server*, default `http://localhost:1234`). CommitMaster **auto-detects the loaded model**, so swapping Gemma → any other model needs no configuration.
4. Run it:
   ```
   python main.py
   ```
5. First launch opens `config.json` — set your project folder:
   ```json
   "projects_dirs": ["C:\\Data\\Saumya\\Projects"]
   ```

## Configuration (`config.json`)

| Setting | Purpose |
|---|---|
| `watched_apps` | Process names to monitor (Task Manager → Details to find exact names). Edit freely. |
| `projects_dirs` | Folders containing your cloned repos (scanned 3 levels deep). |
| `session_end_grace_seconds` | How long apps must stay closed before the reminder fires. |
| `auto_commit` | `false` (default) = preview before commit; `true` = commit automatically. |
| `skip_sensitive_files` | `.env`, keys, pem files are never auto-staged — they're listed with a warning for you to handle manually. |
| `lm_studio.model` | Leave empty to auto-detect, or pin a model name like `gemma3:12b`. |

## Tray menu

- **Check for uncommitted work now** — trigger the flow manually, no need to wait.
- **⚙ Settings…** (also opens on left-click / double-click of the tray icon) — full settings window:
  - **General** — auto-commit toggle, sensitive-file skipping, all timing values.
  - **Apps & Folders** — add/remove watched coding apps and project folders (with folder browser).
  - **AI / LM Studio** — server URL, model picker with live *⟳ Refresh* from LM Studio, connection test.
  - **Advanced** — GitHub Desktop path (auto-detect), sensitive-file patterns.
- **Open config.json** — raw settings file, for anything the UI doesn't cover.
- **Pause monitoring** — temporarily stop watching.
- **Exit**.

Settings changes apply immediately (no restart needed). Test the full flow anytime with `python main.py --check-now`.

## Notes & safety

- Nothing is ever committed without your confirm unless you turn on `auto_commit`.
- Sensitive files (`.env`, `*.pem`, `id_rsa`, ...) are excluded from auto-staging.
- Committing each *file* separately produces noisy history, so changes are grouped
  logically (new features / modified code / tests / docs / config) with one
  message per group — the way real teams commit.
- Start at login: press `Win+R` → `shell:startup` → put a shortcut to `main.py` there,
  or create an `.exe` with `pyinstaller --onefile --noconsole main.py`.
