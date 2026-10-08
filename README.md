# CommitMaster v4.0

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform Windows](https://img.shields.io/badge/platform-Windows%2011%20%7C%2010-0078d4.svg)](https://microsoft.com/windows)
[![Windows Fluent UI](https://img.shields.io/badge/UI-Fluent%20Procedural%20Textures-emerald.svg)]()
[![Local AI Native](https://img.shields.io/badge/AI-100%25%20Local%20(LM%20Studio%20%7C%20Ollama)-brightgreen.svg)](https://lmstudio.ai/)
[![Microsoft Store Ready](https://img.shields.io/badge/Store-MSIX%20%2B%20Win32%20EXE-purple.svg)]()
[![Security Audited](https://img.shields.io/badge/Security-20--Point%20Architecture-blue.svg)]()
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

CommitMaster is a privacy-first **GitHub Desktop alternative**, **native Windows 11 developer suite**, and **coding session companion** powered by **100% offline local AI** (LM Studio, Ollama, Bionic) and multi-cloud AI providers (OpenAI, Claude, Gemini).

CommitMaster actively monitors Git repositories across your system, generates file-by-file commit comments, protects against credential leaks and syntax errors, enforces interactive confirmation before remote pushes, and alerts you via intelligent desktop notifications the moment an IDE session concludes with uncommitted changes.

---

## 🔄 The Complete Evolution: v1.0 ➔ v2.0 ➔ v3.0 ➔ v4.0

| Capability | v1.0 (Legacy Tray Daemon) | v2.0 (Local AI Desktop) | v3.0 (Windows Desktop Edition) | v4.0 (Production & Store Release) |
|:---|:---|:---|:---|:---|
| **Design & Surface Textures** | Flat gray Tkinter frames | Basic dark theme | Solid dark mode colors | **Procedural Pattern Textures & Tactile Grid Banners** covering sidebar panels, card medallions, and page headers |
| **Notification Engine** | Basic Windows tray balloon | OS notification alerts | Single-IDE polling timer | **Independent Multi-IDE Session Tracker** with exact repository alert phrasing & Windows 11 crash protection |
| **Session Lifecycle Grace** | Hardcoded 120s delay | 120s timer | Configurable grace | **Instant 2s Grace Period** with per-process IDE close detection (VS Code, Cursor, Antigravity, etc.) |
| **Login & Auth Window** | Stretched full-width dialog | Simple auth inputs | Account manager switcher | **Centered Compact Studio Card (450px fixed)**, prevent wide-screen stretch, PBKDF2 600k hashing |
| **Database Architecture** | Raw SQLite queries | Basic WAL mode | Single-user database | **Enterprise Indexed SQLite with Row-by-Row Cursor Streaming** (`fetch_rows_iter`) & 0 memory spikes |
| **Security Architecture** | None | `.env` file exclusion | Basic credential filters | **20-Point Security Architecture** (Login rate limiting, RLS, token encryption, field-tampering shield, response trimming) |
| **Packaging & Distribution**| Raw Python source | Single PyInstaller `.exe` | Dual-EXE (`build_exe.py`) | **Official Microsoft Store MSIX Package (`CommitMaster.msix`)** + Standalone Portable EXE + 1-Click Batch compilers |
| **Admin App Integration** | Command line only | Separate prototype script | Unified multi-nav admin | **Full Reminder & Monitored IDE Integration** inside `admin_app.py` for comprehensive dev testing |

---

## 🌟 What's New in Version 4.0

### 1. 🎨 Surface Patterns & Procedural Textures Across Panels & Headers
- **Procedural Canvas Banners**: Headers, panels, and cards are no longer flat, monotone blocks. CommitMaster now dynamically renders subtle tactile textures:
  - **Tech Dot Matrix**: Developer coordinate grid with precision alignment micro-dots.
  - **Circuit Mesh**: Futuristic microchip traces, 45° bus lines, and silicon junction pads.
  - **Carbon Weave**: Executive tactile diagonal composite weave with depth.
  - **Blueprint Grid**: Isometric engineering coordinate grid with crosshairs.
  - **Hexagon Mesh**: Wireframe cyber honeycomb geometry.
  - **Ambient Radial**: Luminous radial spotlight with soft noise.
  - **Clean Solid**: Crisp minimalist dark surfaces.
- **Full Sidebar Panel & Header Coverage**: The entire sidebar header (expanded to 240px width), user identity profile card, top navigation header bar, and internal page banners are seamlessly textured.
- **High-Performance Image Caching**: An in-memory PIL/PhotoImage LRU cache delivers fluid 60fps window resizing with zero stutter or lag.

### 2. 🔔 Intelligent Multi-IDE Session Tracking & Accurate Notifications
- **Independent Per-Process Tracking**: In previous versions, running multiple developer tools simultaneously (e.g. Antigravity IDE and VS Code) could mask close events. Version 4.0 independently monitors each running executable (`Code.exe`, `Cursor.exe`, `Antigravity IDE.exe`, `pycharm64.exe`, `idea64.exe`, etc.).
- **Instant IDE Exit Triggers**: Session end grace period reduced from 120s to **2 seconds**. Closing VS Code triggers immediate verification of uncommitted work.
- **Exact User-Specified Notification Phrasing**:
  > *"There are some files which haven't been commit in **[RepoName]** repo"*
- **Deep Linked Repo Scanning**: Discovers uncommitted files across all linked GitHub repositories, watched folders, user project directories, and local working directories.
- **Windows 11 Shell Notification Shield**: Safely guards against Windows 11 `Shell_NotifyIconW` tray handler crashes, guaranteeing floating bottom-right Tkinter reminder toasts render reliably.

### 3. 🔐 Compact Login Screen & Brute-Force Rate Limiting
- **Compact Modal Geometry**: Replaced full-width stretched login forms with a centered, modern card clamped to 450×600px (`minsize 420x520`, `maxsize 500x850`). Looks balanced and sharp on ultrawide and 4K displays.
- **Brute-Force & Bot Protection**: Failed login attempts are recorded in SQLite (`login_rate_limit`). Exceeding 5 consecutive failed attempts temporarily locks out the account for 15 minutes.
- **Response Trimming (`_clean_user_dict`)**: Sensitive password hashes are automatically stripped from database return objects across all API responses.

### 4. ⚡ Database Indexing & Row-by-Row Cursor Streaming
- **Explicit Foreign Key & Email Indexes**:
  - `idx_users_email`, `idx_verification_otps_email`
  - `idx_commit_activity_user_id`, `idx_app_usage_user_id`
  - `idx_sessions_user_id`, `idx_system_settings_updated_by`
  - `idx_github_accounts_user_id`, `idx_repo_github_accounts_user_id`
  - `idx_repo_github_accounts_account_id`, `idx_watched_repos_user_id`
  - `idx_watched_repos_github_account_id`, `idx_app_events_user_id`
- **Streaming Row-by-Row Fetching (`fetch_rows_iter`)**: Replaced memory-heavy `fetchall()` lists with lightweight SQLite cursor iteration (`for r in cur:`), eliminating UI lag during large repository scans.

### 5. 🛡️ 20-Point Enterprise Security Architecture
1. **Hide API Keys**: Never hardcoded; stored in user preferences or `.env` and excluded from repository files.
2. **Purge Git Secrets**: `.commitmaster_accounts.json` and session tokens untracked from Git and added to `.gitignore`.
3. **Public / Private DB Credentials**: Clean SQLite WAL architecture with secure remote REST API sync support.
4. **Row-Level Security (RLS)**: All queries enforce `WHERE user_id = ?` to strictly isolate multi-user records.
5. **Encrypt Sensitive Data**: AES-256-GCM authenticated encryption for personal access tokens (PATs) and credentials.
6. **Server-Side Auth**: Secure password verification via server and database layers.
7. **Lock Record Access**: Repository deletion, rebinding, and profile updates require user ownership validation.
8. **Block Field Tampering**: Strict parameter allowlisting on database updates.
9. **Secure Session Tokens**: Cryptographically random 64-character tokens generated via `secrets.token_hex(32)`.
10. **Hash Passwords**: PBKDF2-HMAC-SHA256 with 600,000 iterations + 32-byte salt and bcrypt fallback.
11. **Rate Limit Login**: Progressive lockout after 5 failed login attempts per username or email.
12. **Bot Protection**: Prevents credential stuffing through lockout thresholds.
13. **Parameterize Queries**: 100% of SQL queries use `?` parameterization; zero string concatenation.
14. **Validate All Input**: Strict regex checks for emails, usernames, and commit descriptions.
15. **Escape User Content**: File inspector diffs and commit messages sanitized prior to UI rendering.
16. **Restrict File Uploads**: Extension and MIME validation for avatar imports (`.png`, `.jpg`, `.webp`).
17. **Trim API Responses**: `password_hash` omitted from user retrieval outputs.
18. **Add Security Headers**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1`, `Referrer-Policy: strict-origin-when-cross-origin`.
19. **Force HTTPS**: All GitHub API and cloud communications strictly enforce TLS `https://`.
20. **Scan Dependencies**: Dependencies verified against modern security requirements.

### 6. 📦 Store-Ready Packaging Suite (MSIX & Standalone EXE)
- **`dist/CommitMaster.msix`**: Native Windows 10/11 app package built with Windows SDK `makeappx.exe` for Microsoft Partner Center Store submission.
- **`dist/CommitMaster.exe`**: Standalone user binary (no Python runtime required).
- **`dist/CommitMaster-Admin.exe`**: Saumya's private administrator workspace binary.
- **`build_msix.py` & `Build_MSIX_Package.bat`**: 1-click MSIX packaging automation including visual store asset generation (`Square44x44`, `Square150x150`, `StoreLogo`, `Wide310x150`, `SplashScreen`).

---

## 🚀 Core Features Matrix

### 🖥️ Full-Featured Git Desktop Client
- **Visual File Badges**: Badges for Modified (`M`), Added (`A`), Deleted (`D`), and Untracked (`?`) files.
- **Side-by-Side Colorized Diffs**: Syntax-highlighted unified diffs with line additions (`green`), deletions (`red`), and hunk markers (`blue`).
- **Branch Management**: Fast branch switching, creation, and current branch tracking.
- **Interactive Push Protection**: Modal confirmation displays repository, branch, active GitHub account, and commit list before pushing.

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
- **Theme Presets**: GitHub Dark, Midnight Obsidian, Dracula Violet, Cyberpunk Neon, Nordic Frost, Monokai Pro Charcoal, Modern Clean Light.
- **Accent Colors**: Emerald Green, Neon Cyan, Royal Violet, Sunset Amber, Crimson Red, Rose Pink, Mint Teal, or Custom Hex.
- **Typography & Density Scaling**: Font family selection, UI density controls (Comfortable / Compact), and font scaling (90% to 115%).

---

## 📦 Building Standalone Executables & Microsoft Store MSIX

### 1. Build Standalone EXEs
```powershell
# Double-click Build_All_Packages.bat or run:
python build_exe.py
```
**Outputs:**
- `dist/CommitMaster.exe`: Public standalone executable for users.
- `dist/CommitMaster-Admin.exe`: Saumya's private administrator standalone application.
- `dist/CommitMaster-v3.0-Windows.zip`: Portable distribution archive.

### 2. Build Microsoft Store MSIX Package
```powershell
# Double-click Build_MSIX_Package.bat or run:
python build_msix.py
```
**Output:**
- `dist/CommitMaster.msix`: Official MSIX package for Microsoft Partner Center Store submission.

---

## ⚙️ Configuration Reference (`config.json`)

| Setting | Type | Purpose |
|:---|:---|:---|
| `ai.provider` | string | Active AI provider (`"bionic"`, `"openai"`, `"claude"`, `"gemini"`, `"ollama"`) |
| `ai.base_url` | string | Local LLM endpoint (`http://localhost:1234/v1` or `http://localhost:11434/v1`) |
| `ai.model` | string | Model name (leave blank for automatic auto-detection) |
| `projects_dirs` | list | Folders containing local repositories |
| `watched_apps` | list | Monitored executables for session close detection (e.g. `Code.exe`, `Cursor.exe`) |
| `session_end_grace_seconds` | int | Idle wait time after apps close before prompting (default 2s in v4.0) |
| `reminder.interval_enabled` | bool | Enable interval timer reminders |
| `reminder.app_monitor_enabled` | bool | Enable IDE monitoring reminders |
| `reminder.only_if_dirty` | bool | Suppress reminders if all linked repositories are clean |
| `skip_sensitive_files` | bool | Automatically ignore `.env`, `*.pem`, `*.key` files from bulk staging |

---

## 🔒 Privacy & Safety Guarantee

- **Zero Cloud Leakage**: CommitMaster does not send source code or diffs to external clouds unless you explicitly configure a remote LLM API key.
- **Sensitive File Shield**: Credential files (`.env`, private keys, secrets) are excluded from automated commits.
- **Push Protection**: Accidental pushes to remotes are prevented by interactive review modals.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
