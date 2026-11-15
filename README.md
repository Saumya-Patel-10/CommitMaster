# CommitMaster v1.0

[![Microsoft Store](https://img.shields.io/badge/Microsoft%20Store-Not%20published%20this%20revision-lightgrey.svg?logo=windows)](https://apps.microsoft.com/)
[![Platform Windows](https://img.shields.io/badge/platform-Windows%2011%20%7C%2010-0078d4.svg)](https://microsoft.com/windows)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Local AI Native](https://img.shields.io/badge/AI-100%25%20Offline%20(LM%20Studio%20%7C%20Ollama%20%7C%20Bionic)-brightgreen.svg)](https://lmstudio.ai/)
[![Fluent UI](https://img.shields.io/badge/UI-Fluent%20Procedural%20Textures-emerald.svg)]()
[![Security Audited](https://img.shields.io/badge/Security-20--Point%20Hardened-blue.svg)]()
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE.txt)

**CommitMaster** is a privacy-first **Windows Git companion and developer session monitor**. This repository builds three separate programs. The public user app tracks IDE sessions, inspects changes before you commit, and can draft Conventional Commits with a local model. The private admin app and the demo app are different entry points. They do not live inside the user app.

The user package keeps the existing Store identity: Name `SaumyaPatel.CommitMaster`, Publisher `CN=7522A476-A1F1-4D1A-80FA-BEFE0A4BF5F8`, version `1.1.0.0`, executable `CommitMaster-User.exe`. No MSIX for this revision has been built, and it has not been submitted to the Microsoft Store.

Whether you work with VS Code, Cursor, Antigravity IDE, PyCharm, or Visual Studio, CommitMaster runs silently in the background, protects you against secret leaks, and guarantees you never lose track of what you changed.

---

## 🔄 The Evolution Journey: From Prototype to Version 1.0

CommitMaster started as a tray daemon and grew into a Windows desktop application. The table below is that history. It is not a claim that this revision is certified or listed in the Microsoft Store:

| Area | Phase 1: Inception<br>*(CLI & Tray Daemon)* | Phase 2: Alpha<br>*(Local AI Desktop)* | Phase 3: Beta<br>*(Cloud & Security Hardening)* | Version 1.0 |
|:---|:---|:---|:---|:---|
| **User Interface** | Flat gray Tkinter frames & system tray icon only | Basic dark UI with simple buttons | Multi-page dark layout with account switcher | **Fluent UI with 7 Procedural Canvas Textures** (Tech Dots, Circuit Mesh, Carbon Weave, Blueprint, Hexagon), custom accents & 60fps LRU caching |
| **Notification Engine** | OS tray balloon tooltip | Windows notifications via Plyer | Single-IDE polling timer | **Independent Multi-IDE Process Tracker** (`Code.exe`, `Cursor.exe`, `Antigravity IDE.exe`, etc.) with 2s exit grace & Windows 11 crash shield |
| **AI Intelligence** | Hardcoded git change summaries | Single local endpoint (LM Studio) | Basic prompt templates | **100% Offline Local AI** (LM Studio, Ollama, Bionic) + Multi-Cloud (OpenAI, Claude, Gemini) with heuristic Conventional Commit fallback |
| **Pre-Commit Inspection**| None (blind `git commit`) | Basic `.env` exclusion | Simple credential regex | **Pre-Commit Health & Vulnerability Inspector** (AST syntax validator, CWE-798 secret scanner, merge conflict blocker & empty file detector) |
| **Authentication & Auth UI**| None (local shell only) | Stretched full-width dialog | Simple SQLite password storage | **Centered Studio Auth Card (450px fixed)**, PBKDF2 600,000 iterations, 15-minute brute-force lockout & token encryption |
| **Database Architecture** | Flat JSON file | Raw SQLite queries | SQLite with WAL mode | **Enterprise Indexed SQLite with Cursor Streaming** (`fetch_rows_iter`), zero UI lag on 10,000+ commit histories |
| **Multi-Device & Sync** | Single machine only | Local database only | Prototype REST endpoints | **Dual-Mode Data Architecture** (Zero-config local SQLite + Central Flask REST cloud backend `server.py` with multi-device login) |
| **Packaging & Distribution**| Raw Python source scripts | Single PyInstaller `.exe` | Portable ZIP and Win32 executable | Historical `CommitMaster.exe` release. This tree builds `CommitMaster-User.exe`, `CommitMaster-Admin.exe`, and `CommitMaster-Demo.exe`. An MSIX for this split has not been built or published. |

---

## 🌟 Key Features in Version 1.0

### 1. 🎨 Native Windows 11 Fluent UI & Procedural Canvas Textures
- **Dynamic Procedural Surfaces**: Headers, cards, and sidebar panels feature dynamically rendered tactile procedural textures:
  - **Tech Dot Matrix**: Developer coordinate grid with precision micro-dots.
  - **Circuit Mesh**: Microchip trace routes, 45° bus lines, and silicon pads.
  - **Carbon Weave**: Premium diagonal composite weave with tactile depth.
  - **Blueprint Grid**: Isometric engineering coordinate grid with crosshairs.
  - **Hexagon Mesh**: Cyber honeycomb wireframe geometry.
  - **Ambient Radial**: Luminous spotlight with soft noise falloff.
  - **Clean Solid**: Crisp minimalist dark slate.
- **High-Performance Image Caching**: In-memory PIL/PhotoImage LRU cache delivers fluid 60fps window resizing with zero stutter.
- **7 Theme Presets & Curated Accents**: GitHub Dark, Midnight Obsidian, Dracula Violet, Cyberpunk Neon, Nordic Frost, Monokai Pro Charcoal, Modern Clean Light, paired with 8 vibrant accent palettes.

### 2. 🔔 Multi-IDE Session Tracking & Contextual Reminders
- **Independent Per-Process Monitoring**: Concurrently tracks each running IDE executable (`Code.exe`, `Cursor.exe`, `Antigravity IDE.exe`, `pycharm64.exe`, `idea64.exe`, `devenv.exe`). Closing one IDE does not get masked by another running editor.
- **2-Second Session Exit Grace**: Detects IDE closure and prompts you within 2 seconds if uncommitted modifications remain.
- **Exact Actionable Toast Notifications**:
  > *"There are some files which haven't been commit in **[RepoName]** repo"*
- **Windows 11 Notification Shield**: Protects against system tray API crashes, ensuring floating bottom-right toasts render reliably.

### 3. 🤖 100% Offline Local AI Native + Cloud Providers
- **Zero Cloud Leakage**: Prompts and code diffs stay strictly on your local PC when using local providers.
- **Compatible with Modern Local Models**: LM Studio, Ollama, Bionic, and llama.cpp (Gemma 2, Qwen 2.5 Coder, Llama 3.2, DeepSeek, Mistral).
- **Multi-Cloud Provider Support**: Optional support for OpenAI (GPT-4o), Anthropic (Claude 3.5), and Google (Gemini 1.5).
- **Heuristic Fallback Engine**: If your AI server is paused or offline, CommitMaster automatically generates clean Conventional Commits (`feat(...)`, `fix(...)`, `refactor(...)`) based on AST symbols and change semantics.

### 4. 🛡️ Pre-Commit Health & Vulnerability Inspector
- **Syntax Validator**: Checks Python AST syntax, JSON formatting, and YAML structure before you commit.
- **Credential Leak Protection (CWE-798)**: Detects GitHub PATs (`ghp_*`), AWS access keys (`AKIA*`), OpenAI tokens (`sk-*`), private keys, and passwords.
- **Merge Conflict Blocker**: Blocks accidental staging of conflict markers (`<<<<<<< HEAD`, `=======`, `>>>>>>>`).
- **Empty File Warning**: Alerts you if a file was accidentally truncated to 0 bytes.

### 5. 📊 Capitalio-Style Analytics & Interactive Multi-Series Engine
- **5 Top KPI Metrics**: Real-time tracking for **Total Commits**, **Vulnerabilities**, **Code Errors**, **Failed Operations** (commits + pushes), and **Code Stability Score** with dynamic micro-sparklines and period comparative trends.
- **Interactive Multi-Series Performance Chart**: Watermelon Capitalio dot-grid canvas plotting Commits, Vulnerabilities, Errors, Failures, and Sessions concurrently.
- **Legend Pill Toggles**: Clickable header badges allow developers to toggle individual metrics on and off with instant canvas re-scaling.
- **Glassmorphic Hover Crosshair**: Dynamic guideline snapping across dates displaying a structured floating breakdown card of all active metrics.
- **Live System Audit Tables**: Prominent Security Findings and 7-day Daily Breakdown tables providing comprehensive repository visibility.

### 6. 🔔 Clean Single-Delivery In-App Notifications
- **Featured Toast Overlay**: Custom bottom-right floating notification toast with direct interactive action buttons (`Commit Now`, `Snooze`, `Dismiss`).
- **Zero OS Duplication**: Eliminates duplicate Windows Action Center balloon popups, keeping developer notifications clean and distraction-free.

### 7. Private admin app

Account administration is not part of the public user app. There is no Admin Portal button in `app.py`. Run `admin_app.py` (or `CommitMaster-Admin.exe`) as its own process. That process can select accounts and disable, enable, or delete them, with confirmation and an audit log. The user package excludes `admin_app`, `commitmaster.admin_portal`, and `commitmaster.admin_client`.

### 8. 🐙 Multi-Account GitHub Linking & Web Sign-In
- **Fast Web Sign-In**: Automatically launches GitHub with pre-filled scopes (`repo`, `user:email`, `read:org`, `workflow`) for instant authorization.
- **Multi-Account Profile Manager**: Easily switch between personal, open-source, and corporate GitHub accounts.
- **Repo-to-Account Push Bindings**: Bind specific repositories to specific accounts so commits and pushes always reflect the right identity.
- **Interactive Push Protection**: Modal confirmation summarizes repository, branch, author account, and commit list prior to remote push.

### 9. 🌐 Dual-Mode Architecture: Local & Central Cloud Sync
- **Local Mode (Default)**: Out-of-the-box zero-config operation powered by a high-performance local SQLite database.
- **Cloud Backend Mode (`server.py`)**: Deploy the included lightweight REST API to Render, Railway, or VPS so you can log in, sync tracked repositories, and manage sessions across multiple Windows computers.

### 10. 🔐 20-Point Enterprise Security Architecture
1. **Never Hardcode Secrets**: API keys and tokens stored strictly in local configuration or `.env`.
2. **Purge Git Secrets**: Account tokens and sessions excluded by default.
3. **Database Security**: SQLite WAL mode with remote TLS REST sync.
4. **Row-Level Security (RLS)**: Enforced `WHERE user_id = ?` query isolation across all data tables.
5. **Authenticated Token Encryption**: AES-256-GCM authenticated encryption for stored credentials.
6. **Server-Side Authentication**: Secure password verification at database layer.
7. **Record Access Locks**: Repository actions bound strictly to authenticated owners.
8. **Field Tampering Shield**: Parameter allowlisting on profile and settings updates.
9. **Secure Session Tokens**: Cryptographically random 64-character tokens (`secrets.token_hex(32)`).
10. **Password Hashing**: PBKDF2-HMAC-SHA256 with 600,000 iterations and 32-byte salts.
11. **Login Rate Limiting**: Progressive 15-minute lockout after 5 consecutive failed attempts.
12. **Anti-Bot Shield**: Locks against credential-stuffing and automated dictionary attacks.
13. **100% Parameterized SQL**: Zero string interpolation; SQL injection immune.
14. **Input Sanitization**: Regex validation on emails, usernames, and paths.
15. **Content Escaping**: File diffs and commit messages safely escaped before rendering.
16. **Upload Constraints**: Strict MIME and extension validation for profile avatars.
17. **Response Trimming**: `password_hash` omitted from all internal dictionary returns.
18. **Security Headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1`.
19. **Strict HTTPS**: Enforced TLS on all cloud endpoints and GitHub API calls.
20. **Audited Dependencies**: Clean dependency footprint with verified versions.

---

## Three programs

| Program | Run from source | Windows executable | Data directory name |
| --- | --- | --- | --- |
| User | `python app.py` | `CommitMaster-User.exe` | `CommitMaster` |
| Admin | `python admin_app.py` | `CommitMaster-Admin.exe` | `CommitMaster-Admin` |
| Demo | `python demo_app.py` | `CommitMaster-Demo.exe` | `CommitMaster-Demo` |

The user process locks itself as `user` and cannot open the admin console. The admin process is private and is not included in the user package. The demo process uses its own data directory, refuses a production server, and does not push to GitHub remotes.

Each program keeps its own local database. Do not point the admin or demo package at the user Store identity.

## Getting started from source

```powershell
git clone https://github.com/Saumya-Patel-10/CommitMaster.git
cd CommitMaster
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Use `python admin_app.py` or `python demo_app.py` instead of `python app.py` when you mean those programs. On Linux or macOS the same three commands start the source apps. The executables below are Windows builds.

The published GitHub release asset is still `CommitMaster.exe` from tag `v1.1`. That file is the older single executable and still contains the admin launch path. It is not `CommitMaster-User.exe`.

## Building

On Windows, with PyInstaller installed, `python build_exe.py` builds all three executables under `dist/` and attempts Authenticode signing only when `signtool` and `MSIX_TEST_CERT_PASSWORD` are present. The same command also writes `dist/CommitMaster-v1.0-Windows.zip` and `dist/CommitMaster.zip`. Those zips store the user executable under the filename `CommitMaster.exe`. The file produced by the user build, and by CI, is `dist/CommitMaster-User.exe`. The zips are not an MSIX. CI builds each executable separately and does not sign them:

```powershell
python -c "from build_exe import build_single; build_single('app.py', 'CommitMaster-User', 'user', product='user')"
python -c "from build_exe import build_single; build_single('admin_app.py', 'CommitMaster-Admin', 'admin', product='admin')"
python -c "from build_exe import build_single; build_single('demo_app.py', 'CommitMaster-Demo', 'demo', product='demo')"
```

A GitHub Actions run on commit `971a6ad` produced those three unsigned executables as workflow artifacts. They were not installed on a clean machine, not attached to a GitHub Release, and not submitted to the Store.

`python build_msix.py` is the user-package packager. It reads `store_identity.json` and expects `dist/CommitMaster-User.exe`. It needs `makeappx.exe`. Signing needs `signtool.exe`. Neither tool ran for this revision, so there is no `CommitMaster.msix` to install or upload. Do not treat a successful executable build as a Store publication.

### Store identity

Leave the user package identity unchanged:

| Field | Value |
| --- | --- |
| Name | `SaumyaPatel.CommitMaster` |
| Publisher | `CN=7522A476-A1F1-4D1A-80FA-BEFE0A4BF5F8` |
| Version | `1.1.0.0` |
| Executable | `CommitMaster-User.exe` |

Admin and demo identities are in `package_layout/identities.json`. They use different package names and publishers.

---

## ⚙️ Configuration Reference (`config.json`)

| Setting | Type | Default | Description |
|:---|:---|:---|:---|
| `watched_apps` | list | `["Code.exe", "Cursor.exe", "Antigravity.exe"]` | Monitored IDE executables for session end detection |
| `projects_dirs` | list | `[]` | Root directories containing your Git repositories |
| `session_end_grace_seconds` | int | `2` | Seconds to wait after IDE close before prompting |
| `auto_commit` | bool | `false` | Automatically stage and commit without manual prompt |
| `skip_sensitive_files` | bool | `true` | Prevent staging `.env`, `.pem`, `.key`, and secret files |
| `server_url` | string | `""` | Optional central backend URL for multi-device sync |
| `ai.provider` | string | `"bionic"` | Active AI provider (`"bionic"`, `"ollama"`, `"openai"`, `"claude"`, `"gemini"`) |
| `ai.base_url` | string | `"http://localhost:1234/v1"` | Local AI inference endpoint URL |
| `ai.model` | string | `""` | Model name (leave blank for automatic auto-detection) |
| `ai.timeout_seconds` | int | `90` | Maximum request timeout for AI responses |

---

## 🔒 Privacy & Safety Guarantee

CommitMaster is engineered with a strict **Privacy-First** philosophy:
- **Code Privacy**: Your source code, commits, and diffs are **never** transmitted to remote clouds unless you explicitly configure a commercial cloud AI provider key.
- **Local Database**: All accounts, repository bindings, and activity histories reside on your machine in encrypted SQLite storage.
- **Zero Telemetry Spyware**: No tracking pixels, external behavioral analytics, or invasive trackers.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE.txt](LICENSE.txt) file for details.
