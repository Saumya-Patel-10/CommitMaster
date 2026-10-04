# CommitMaster v2.0

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://microsoft.com/windows)
[![Local AI Native](https://img.shields.io/badge/AI-100%25%20Local%20(LM%20Studio%20%7C%20Ollama)-brightgreen.svg)](https://lmstudio.ai/)
[![Git Desktop Alternative](https://img.shields.io/badge/GUI-Git%20Desktop%20Alternative-orange.svg)]()
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A powerful, privacy-first **GitHub Desktop alternative** and **background coding session guardian** powered by **native local AI running on your PC** (LM Studio, Ollama, Bionic). 

CommitMaster inspects git changes, generates intelligent commit comments for **each modified file**, requires **interactive confirmation before git pushing**, lets you **sign into GitHub via the web**, and provides **active repository watching** across all your projects.

---

## 🔄 Upgrade Highlights: Evolution from v1.2 to v2.0

| Feature | v1.2 (Legacy Background Tray) | v2.0 (Modern Local AI Git Desktop) |
|---|---|---|
| **Primary Interface** | Minimal system tray icon & reminder popup | Full **GitHub Desktop GUI** with diff viewer, branch selector & commit dock |
| **AI Commit Generation** | Single lumped summary across staged files | **Per-file native local AI explanations** for every modified file |
| **AI Privacy & Runtime** | Basic LM Studio integration | 100% offline local PC inference (LM Studio / Ollama / Bionic) with resilient heuristic fallback |
| **Push Safety** | Automatic or external push in GitHub Desktop | **Interactive Push Protection Modal** (review branch, account, and commit list) |
| **GitHub Authentication** | Manual token entry only | **One-click Web Sign-In** with pre-filled scopes & clipboard auto-paste |
| **Repository Management**| Passive scanning of folders | **GitHub API repository discovery** with dynamic **Active Watch** selection |
| **Multi-Account Support** | Single account | **Multiple GitHub accounts** with per-repository push bindings |
| **Customization** | Hardcoded dark colors | **7 Curated themes**, custom accents, typography, and density scaling |

---

## 🌟 Highlights of v2.0

- ⚡ **Local Repo Scanner & AI Push Preview**: Real-time repository scanning directly on the Overview dashboard. View modified/added file badges, generate AI commit comments, edit the headline and per-file descriptions to your liking, and approve before pushing to GitHub.
- 🖥️ **Integrated Git Desktop View**: A full-featured desktop client with branch switching, visual file status indicators (`M`, `A`, `D`, `?`), side-by-side colorized diff viewing, and one-click commit & push.
- 🤖 **Native Local PC AI Per-File Comments**: Uses your local LLM (Gemma, Qwen, Llama, Mistral) via `localhost:1234` or `localhost:11434` with support for reasoning models, custom prompts, and heuristic fallbacks.
- 📜 **Smooth Scrolling & Precision Touchpad Engine**: Natural, high-performance scrolling across User and Admin apps for both traditional mouse wheels and modern laptop touchpads.
- 🛡️ **Interactive Push Protection**: Protects your remotes by prompting with an explicit confirmation dialog showing repo, branch, account, and commit list before pushing.
- 🌐 **Web-Based GitHub Sign-In**: Click to launch GitHub's web token generator with pre-filled scopes (`repo`, `user:email`, `read:org`, `workflow`) and paste directly from clipboard.
- 📁 **Selective Repository Authorization & Active Watch**: Full control over what is watched—only explicitly authorized local folders and selected GitHub repos are tracked.
- 🐙 **Multi-Account Linking**: Manage personal, work, and open-source GitHub accounts with per-repository push bindings.
- 🎨 **Interface Customization**: 7 color themes (Midnight, Slate Dark, Obsidian, Nord, Dracula, Cyberpunk, Light Mode), custom accent colors, font scaling, and density control.

---

## 📐 How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CommitMaster v2.0                                │
│                                                                             │
│  ┌───────────────────────┐  ┌────────────────────────────────────────────┐  │
│  │   Changed Files (3)   │  │              Colorized Diff                │  │
│  │  ☑ [M] database.py    │  │  @@ -1020,8 +1040,15 @@                   │  │
│  │  ☑ [A] github_srv.py  │  │  + def add_or_update_watched_repo(...):    │  │
│  │  ☑ [M] desktop_ui.py  │  │  +     # SQLite persistence logic          │  │
│  └───────────────────────┘  └────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ 🤖 AI Per-File Comment (Local PC Gemma / Qwen / Mistral via LM Studio):│  │
│  │ database.py: Added watched_repositories schema and sync helpers       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Commit: feat(db): implement watched repo tracking                     │  │
│  │ ☑ Ask me before git pushing [ Commit to main ]  [ Commit & Push 🚀 ]   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                         (If Push Protection is ON)
                                      ▼
             ┌─────────────────────────────────────────────────┐
             │       🛡️ Confirm Git Push to Remote             │
             │  Repo: CommitMaster | Branch: main              │
             │  Account: @Saumya-Patel-10                      │
             │  Commits to push (1):                           │
             │    • 3a89e1f feat(db): implement watched repos  │
             │  [ Cancel (Keep Local) ]    [ 🚀 Push to Remote ]│
             └─────────────────────────────────────────────────┘
```

---

## 🚀 Quick Setup

### 1. Requirements
- **Windows 10/11**
- **Python 3.10+**
- **Git for Windows** (accessible on PATH)
- *(Optional for AI)* **LM Studio** or **Ollama** running locally on port 1234 or 11434

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Launch
```powershell
python main.py
```
*(Or launch the dedicated Admin Portal via `python admin_app.py`)*

### 4. Link GitHub via Web Sign-In
1. Navigate to **🐙 GitHub Accounts** in the app.
2. Click **"+ Link GitHub Account"**.
3. Click **"🌐 Open GitHub Web Sign-In"** — your browser will open `https://github.com/settings/tokens/new` with the required scopes pre-selected (`repo`, `user:email`, `read:org`, `workflow`).
4. Generate the token, copy it, and click **"📋 Paste from Clipboard & Verify"**.

### 5. Sync Repositories & Set Active Watch
1. Open the **📁 Watched Repos** tab.
2. Click **"🔄 Sync All Repos from GitHub"** to pull down your repositories.
3. Bind your local folder paths using **"Link Local Folder"**.
4. Click **`[ ○ Keep eye on repo ]`** to toggle it to **`[ 👀 Actively Watching ]`**.

### 6. Scan Local Repos & Preview AI Push
1. On the **Overview** dashboard (or in **🖥️ Git Desktop**), locate the **⚡ Local Repository Scanner & AI Push Preview** card.
2. Select your repository from the dropdown, or click **"＋ Add Local Repo"** to select any local Git folder on your PC.
3. Click **"⚡ Scan for Changes Now"** to view detected modified, added, deleted, or untracked files with status badges.
4. Click **"✨ Write AI Comments for Each File"** — your local PC AI will analyze diffs and pre-populate the **Commit Headline** and **Per-File Commentary**.
5. **Freely edit** the headline or commentary text box to your liking.
6. Click **"🚀 Approve & Git Push to GitHub"** (or **"💾 Commit Locally Only"**). The push protection modal will display a summary for your approval before pushing.

---

## 🤖 Local PC AI Server Setup

CommitMaster communicates with your local PC AI using standard OpenAI-compatible API specifications.

### Using LM Studio (Recommended)
1. Download and install [LM Studio](https://lmstudio.ai/).
2. Download any coding or instruction model (e.g. `google/gemma-4-12b-qat`, `qwen2.5-coder-7b-instruct`, or `llama-3.2-3b-instruct`).
3. Click the **Developer / Local Model API** tab (`<->` on the sidebar).
4. Select your model to load it into memory.
5. Ensure **Server Status** is **Running** on port `1234` (`http://localhost:1234/v1`).
6. Turn **CORS** to **ON** in LM Studio settings.
7. In CommitMaster **Settings**, confirm Server URL is `http://localhost:1234/v1`. Model name can be left blank for automatic detection!

### Using Ollama
1. Run `ollama run qwen2.5-coder:7b` in your terminal.
2. In CommitMaster **Settings**, set Server URL to `http://localhost:11434/v1`.

### Global Cloud Deployment Transition
When transitioning from local testing to global deployment, simply update `ai.base_url` in `config.json` (or via Global Settings in the Admin Portal) to your cloud HTTPS endpoint. No application code changes are required.

---

## ⚙️ Configuration (`config.json`)

| Setting | Type | Purpose |
|---|---|---|
| `ai.base_url` | string | Local LLM endpoint (`http://localhost:1234/v1` or `http://localhost:11434/v1`) |
| `ai.model` | string | Model name (leave blank for automatic detection) |
| `projects_dirs` | list | Folders containing local repositories |
| `watched_apps` | list | Executables monitored for session close detection (e.g. `code.exe`, `cursor.exe`) |
| `session_end_grace_seconds` | int | Idle wait time after apps close before prompting (default 120s) |
| `ask_before_push` | int | `1` = always prompt confirmation modal before git pushing; `0` = push directly |
| `skip_sensitive_files` | bool | Automatically ignore `.env`, `*.pem`, `*.key` files from bulk staging |

---

## 🔒 Privacy & Safety Guarantee

- **Zero Cloud Exposure**: CommitMaster does not send your source code, file diffs, or prompts to any external cloud API. All inference runs locally on your machine.
- **Sensitive File Shield**: Credential files (`.env`, private keys, secrets) are excluded from automated commits.
- **Push Protection**: Accidental pushes to remotes (including `main` and `master`) are prevented by interactive review modals.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
