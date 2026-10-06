# CommitMaster v3.0

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform Windows](https://img.shields.io/badge/platform-Windows%2011%20%7C%2010-0078d4.svg)](https://microsoft.com/windows)
[![Windows Fluent UI](https://img.shields.io/badge/UI-Fluent%20Immersive%20Dark-emerald.svg)]()
[![Local AI Native](https://img.shields.io/badge/AI-100%25%20Local%20(LM%20Studio%20%7C%20Ollama)-brightgreen.svg)](https://lmstudio.ai/)
[![Git Desktop Alternative](https://img.shields.io/badge/GUI-Git%20Desktop%20Alternative-orange.svg)]()
[![Build Dual Executable](https://img.shields.io/badge/Distribution-Store%20MSIX%20%2B%20Admin%20EXE-purple.svg)]()
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A powerful, privacy-first **GitHub Desktop alternative**, **native Windows 11 desktop software**, and **background coding session guardian** powered by **100% offline local AI** running on your PC (LM Studio, Ollama). 

CommitMaster inspects active git changes across repositories, generates intelligent commit comments for **each modified file**, protects against **secret leaks and syntax breakages**, requires **interactive confirmation before git pushing**, lets you **sign into GitHub via the web**, and provides **active repository watching** across all your projects.

---

## 🔄 The Complete Evolution: v1.0 ➔ v2.0 ➔ v3.0

CommitMaster has evolved from a lightweight background script into a full-fledged, publication-ready Windows desktop suite with dedicated public user and private administrator software.

| Capability | v1.0 – v1.2 (Legacy Tray Daemon) | v2.0 (Modern Local AI Git Desktop) | v3.0 (Enterprise Windows Desktop Edition) |
|:---|:---|:---|:---|
| **Primary Interface** | Minimal system tray icon & reminder popup | Full GitHub Desktop GUI with diffs and branches | **Native Windows 11 Fluent App** with DWM Immersive Dark Titlebar & custom branding |
| **Windows Desktop Integration** | Plain console script / generic `python.exe` process | Tkinter dark mode with default white OS titlebars | **Explicit `AppUserModelID`**, custom taskbar grouping, native window icons, and DWM dark titlebar API |
| **Launch Experience** | Command-line `python main.py` | Command-line or batch file with black terminal popups | **1-Click Silent Launchers (`.vbs`)** with **0 console flashing** + 1-Click Desktop Shortcut creation |
| **Scrolling Engine** | Standard Tkinter stepped scroll | Basic canvas wheel binding | **High-Performance Smooth Wheel + Middle-Click Autoscroll** (Chrome-style velocity drag scrolling) |
| **AI Commit Generation** | Single lumped summary across staged files | Per-file native local AI explanations | **Multi-Model Local AI Engine** with reasoning support, auto-model detection & heuristic resilience |
| **Commit Strategy** | Single all-in-one commit only | Choice between All-in-One vs Individual Commits | **Dual Strategy Engine** with per-file commit preview, selective staging & customizable commentary |
| **Pre-Commit Safety** | Basic `.env` filename check | File inspector for merge markers & basic secrets | **Comprehensive Pre-Commit Health & Vulnerability Inspector** (AST syntax, CWE-798 token shield, empty file alerts) |
| **Admin & Architecture** | Single shared configuration | Basic admin tab in user dashboard | **Dual-App Separation**: Public Client (`CommitMaster.exe`) + Saumya's Private Unified Studio (`admin_app.py` / `CommitMaster-Admin.exe`) |
| **Distribution & Store Readiness** | Raw source code only | Single raw PyInstaller `.exe` | **Store Sandbox Compliant** (`%LOCALAPPDATA%` persistence) + automated dual-package build system (`Build_All_Packages.bat`) |
| **Documentation & Guides** | Plain markdown notes | Comprehensive README | **Full README + 300+ KB Publication PDF Deployment Guide** (`CommitMaster_Store_Deployment_and_Admin_Guide.pdf`) |

---

## 🌟 What's New in Version 3.0

### 1. 🪟 Native Windows 11/10 Desktop Treatment
- **DWM Immersive Dark Titlebar**: Deep Windows Desktop Window Manager (`DwmSetWindowAttribute`) integration eliminates default white titlebars. Window frames seamlessly match the charcoal/obsidian dark theme.
- **Explicit `AppUserModelID` (`CommitMaster.Desktop.3.0`)**: Windows identifies CommitMaster as an independent top-tier desktop application. Pinned icons, jump lists, and Alt+Tab switchers display the official logo instead of grouping under `python.exe`.
- **Multi-Resolution Asset Pack**: Custom Windows 11 Fluent squircle icon pack including multi-res `icon.ico` (16×16 to 256×256) and Microsoft Store tiles (`Square44x44Logo`, `Square150x150Logo`, `StoreLogo`).

### 2. ⚡ 1-Click Launchers & Desktop Shortcuts (Zero Terminal Needed)
- **Silent VBScript Launchers**: Run CommitMaster with zero black command prompts flashing on screen via `Launch_Admin_App.vbs` and `Launch_CommitMaster.vbs`.
- **Auto-Shortcut Provisioning**: Launchers automatically ensure official desktop shortcuts exist upon first run.
- **In-App Desktop Shortcut Creator**: Click **`📌 Create Desktop Shortcuts`** directly inside the Settings tab of both User and Admin apps anytime to instantly pin apps to your Desktop.

### 3. 🖱️ High-Performance Middle-Click Autoscroll Engine
- Experience fluid navigation across complex Git diffs and extensive user logs.
- Click and hold the mouse wheel (or middle button) and drag up or down: the view scrolls continuously with speed dynamically governed by how far you drag, matching Google Chrome and native Windows software.

### 4. 🛡️ Dual-Application Enterprise Architecture
- **Public User App (`CommitMaster.exe` / `app.py`)**: Designed for end-users and Microsoft Store distribution. Includes overview, Git desktop client, per-file AI commits, branch manager, and personal preferences.
- **Saumya's Private Admin App (`CommitMaster-Admin.exe` / `admin_app.py`)**: Your private command center combining personal workspace tools with global admin governance: user account provisioning, role management, audit trails, and aggregate usage charts.

### 5. 📦 Microsoft Store Sandbox & Packaging Suite
- **Store-Safe Persistence**: Configured to store databases, session tokens, and logs in `%LOCALAPPDATA%\CommitMaster`, complying with Windows Store read-only sandbox requirements.
- **1-Click Dual Compiler (`Build_All_Packages.bat`)**: Compiles both `CommitMaster.exe` and `CommitMaster-Admin.exe` into `dist/` with a single double-click.

---

## 🚀 Core Features Matrix

### 🖥️ Full-Featured Git Desktop Client
- **Visual File Badges**: Clear badges for Modified (`M`), Added (`A`), Deleted (`D`), and Untracked (`?`) files.
- **Side-by-Side Colorized Diffs**: Syntax-highlighted unified diffs with line additions (`green`), deletions (`red`), and hunk markers (`blue`).
- **Branch Management**: Fast branch switching, creation, and current branch tracking.
- **Interactive Push Protection**: An explicit modal window displays the repository, branch, active GitHub account, and commit list for confirmation before pushing.

### 🤖 100% Offline Local PC AI
- **No Cloud Required**: All prompts and code diffs stay strictly on your local PC.
- **Per-File Commentary**: Generates targeted commit messages and descriptions for each modified file.
- **Compatible with LM Studio, Ollama, and Bionic**: Supports Gemma, Qwen 2.5 Coder, Llama 3.2, Mistral, and DeepSeek.
- **Heuristic Fallback Engine**: If your local AI server is paused or offline, CommitMaster automatically generates clean Conventional Commits based on git change semantics.

### 🛡️ Pre-Commit Health & Vulnerability Inspector
- **Syntax Validator**: Catches Python AST syntax errors, JSON decode corruptions, and YAML indentation mistakes before you commit.
- **Credential Leak Protection (CWE-798)**: Detects GitHub PATs (`ghp_*`), AWS keys (`AKIA*`), OpenAI API tokens (`sk-*`), and private keys.
- **Merge Conflict Detector**: Prevents accidental commits containing `<<<<<<< HEAD`, `=======`, or `>>>>>>>`.
- **Empty File Alerts**: Flags accidentally emptied files before they corrupt repositories.

### 🐙 Multi-Account GitHub Linking & Web Sign-In
- **Web Sign-In**: Automatically launches GitHub with pre-filled scopes (`repo`, `user:email`, `read:org`, `workflow`) for instant copy-paste token authorization.
- **Multiple Accounts**: Link separate personal, open-source, and corporate accounts.
- **Repo-to-Account Push Bindings**: Assign specific repositories to specific GitHub accounts so commits are always pushed by the correct author.

### 🎨 Personal Interface Customization
- **7 Built-in Themes**: Midnight, Slate Dark, Obsidian, Nord, Dracula, Cyberpunk, and Light Mode.
- **Custom Accent Colors**: Emerald Green, Cyan, Electric Blue, Purple, Orange, or custom Hex.
- **Typography & Density Scaling**: Font family selection, UI density controls (Comfortable / Compact), and font scaling (90% to 115%).

---

## 📐 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CommitMaster v3.0                                │
│                     (Windows 11 Immersive Dark GUI)                         │
│                                                                             │
│  ┌───────────────────────┐  ┌────────────────────────────────────────────┐  │
│  │   Changed Files (3)   │  │              Colorized Diff                │  │
│  │  ☑ [M] database.py    │  │  @@ -1020,8 +1040,15 @@                   │  │
│  │  ☑ [A] github_srv.py  │  │  + def add_or_update_watched_repo(...):    │  │
│  │  ☑ [M] desktop_ui.py  │  │  +     # SQLite persistence logic          │  │
│  └───────────────────────┘  └────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ 🤖 AI Per-File Comment (Local PC Gemma / Qwen / Mistral via LM Studio):│  │
│  │ • database.py: Added watched_repositories schema and sync helpers     │  │
│  │ • github_srv.py: Implemented multi-account token validation           │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ Commit: feat(core): implement multi-account repository bindings       │  │
│  │ ☑ Push Protection Active  [ Commit All ]  [ Commit Individually ]     │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                         (Interactive Safety Check)
                                      ▼
             ┌─────────────────────────────────────────────────┐
             │       🛡️ Confirm Git Push to Remote             │
             │  Repo: CommitMaster | Branch: main              │
             │  Account: @Saumya-Patel-10                      │
             │  Commits to push (1):                           │
             │    • 3a89e1f feat(core): multi-account bindings │
             │  [ Cancel (Keep Local) ]    [ 🚀 Push to Remote ]│
             └─────────────────────────────────────────────────┘
```

---

## 🚀 Quick Setup & Native Development

### 1. Prerequisites
- **Windows 11 or Windows 10 (20H1+)**
- **Python 3.10+** (Tested on Python 3.12 and 3.14)
- **Git for Windows** (accessible on system PATH)
- *(Optional for AI)* **LM Studio** or **Ollama** running locally on port 1234 or 11434

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Launching (Clickable & Terminal)

| Application | Terminal Command | 1-Click Silent Launcher |
| :--- | :--- | :--- |
| **Personal Admin App** | `python admin_app.py` | [Launch_Admin_App.vbs](Launch_Admin_App.vbs) |
| **Public Client App** | `python app.py` | [Launch_CommitMaster.vbs](Launch_CommitMaster.vbs) |
| **Background Tray Daemon** | `python main.py` | — |

> [!TIP]
> Double-click [Create_Desktop_Shortcuts.vbs](Create_Desktop_Shortcuts.vbs) to instantly pin both applications to your Windows Desktop with custom icons.

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
7. In CommitMaster **Settings**, confirm Server URL is `http://localhost:1234/v1`. Model name can be left blank for automatic detection.

### Using Ollama
1. Run `ollama run qwen2.5-coder:7b` in your terminal.
2. In CommitMaster **Settings**, set Server URL to `http://localhost:11434/v1`.

---

## 📦 Building Standalone Executables & Microsoft Store MSIX

To build standalone Windows executables without requiring a Python runtime:

```powershell
# Double click Build_All_Packages.bat or run:
python build_exe.py
```

**Build Output:**
- `dist/CommitMaster.exe`: Public standalone executable for users and Microsoft Store packaging.
- `dist/CommitMaster-Admin.exe`: Saumya's private administrator standalone application.
- `dist/CommitMaster-v3.0-Windows.zip`: Public distribution zip archive.

For complete Microsoft Store MSIX packaging and deployment instructions, refer to the included guide:
📄 **[CommitMaster_Store_Deployment_and_Admin_Guide.pdf](CommitMaster_Store_Deployment_and_Admin_Guide.pdf)**

---

## ⚙️ Configuration Reference (`config.json`)

| Setting | Type | Purpose |
|:---|:---|:---|
| `ai.base_url` | string | Local LLM endpoint (`http://localhost:1234/v1` or `http://localhost:11434/v1`) |
| `ai.model` | string | Model name (leave blank for automatic auto-detection) |
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
