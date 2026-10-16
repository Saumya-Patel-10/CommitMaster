// CommitMaster AI Knowledge Base for automated support assistant
export const AI_KNOWLEDGE = [
  {
    keywords: ["lm studio", "local ai", "ollama", "offline", "model", "endpoint", "connect"],
    question: "How do I configure CommitMaster with local offline AI like LM Studio or Ollama?",
    answer: `CommitMaster supports 100% offline local AI with zero cloud leakage. Here is how to configure it:

**For LM Studio:**
1. Open LM Studio and start the Local Inference Server (default: \`http://127.0.0.1:1234/v1\`).
2. Load any coding model (e.g., Qwen 2.5 Coder 7B, DeepSeek-Coder, or Gemma 2).
3. In CommitMaster **Settings ➔ AI Configuration**:
   - Set Provider to **LM Studio**
   - API Endpoint: \`http://127.0.0.1:1234/v1\`
   - Model: leave default or specify your loaded model name.

**For Ollama:**
1. Run in terminal: \`ollama run qwen2.5-coder:7b\`
2. Set Provider to **Ollama**
3. Endpoint: \`http://localhost:11434/v1\` (Ollama's OpenAI-compatible endpoint).

*If your local AI server is stopped, CommitMaster's Heuristic Fallback Engine automatically generates clean Conventional Commits from AST symbols without failing!*`
  },
  {
    keywords: ["toast", "notification", "not showing", "alert", "reminder", "popup"],
    question: "Why am I not receiving notification toasts when closing my IDE?",
    answer: `CommitMaster features an independent multi-process monitor for \`Code.exe\`, \`Cursor.exe\`, \`Antigravity IDE.exe\`, and \`pycharm64.exe\`. If you aren't seeing toasts:

1. **Check Windows 11 Focus Assist / Do Not Disturb:** Ensure Windows isn't suppressing background app notifications.
2. **2-Second Grace Period:** CommitMaster polls process trees and gives a 2-second grace period before checking if unstaged files remain in your tracked Git repos.
3. **Repository Registration:** Verify that your active repository folder is added to CommitMaster's tracked list in the sidebar.
4. **Notification Shield:** CommitMaster v3.0 has a built-in Windows 11 Notification Shield that falls back to custom floating bottom-right toasts if system tray tooltips are blocked.`
  },
  {
    keywords: ["github", "token", "account", "login", "switch", "push", "scopes"],
    question: "How does GitHub account linking and push protection work?",
    answer: `CommitMaster lets you manage personal, work, and open-source GitHub accounts:

1. **Web Sign-in:** Click **Add Account** in the Accounts panel. CommitMaster opens GitHub with pre-filled OAuth scopes: \`repo\`, \`user:email\`, \`read:org\`, \`workflow\`.
2. **Repo-to-Account Binding:** In repository settings, bind individual repos to specific GitHub accounts so commits and pushes always reflect the right identity.
3. **Push Confirmation Modal:** Before pushing to remote, CommitMaster pops an interactive summary of branch, target origin, author name, and commit list to prevent accidental pushes to production or wrong forks.`
  },
  {
    keywords: ["security", "ast", "cwe-798", "secrets", "api key", "leak", "scanner"],
    question: "What does the Pre-Commit Health & Vulnerability Inspector check?",
    answer: `Before staging or committing, CommitMaster executes a pre-commit health audit:

- **CWE-798 Hardcoded Secrets Scanner:** Detects GitHub tokens (\`ghp_*\`), AWS access keys (\`AKIA*\`), OpenAI API keys (\`sk-*\`), private SSH keys, and passwords.
- **AST Syntax Validator:** Verifies Python Abstract Syntax Trees for valid Python code, JSON parsing validity, and YAML structure before staging.
- **Merge Conflict Blocker:** Prevents accidentally committing unresolved git conflicts (\`<<<<<<< HEAD\`, \`=======\`, \`>>>>>>>\`).
- **Empty File Warning:** Flags files unexpectedly truncated to 0 bytes.`
  },
  {
    keywords: ["microsoft store", "msix", "exe", "smartscreen", "install", "download"],
    question: "What is the difference between the Microsoft Store version and Direct Download?",
    answer: `Both versions share the exact same features and 100% offline security:

- **Microsoft Store (.MSIX):** One-click verified installation, sandboxed application container, automatic silent background updates, and zero Windows SmartScreen warnings.
- **Direct MSIX Package:** Sideloadable for enterprise or machines without Store access.
- **Direct Portable EXE:** Self-contained Win32 executable that runs without installation (ideal for portable thumb drives).

*Note on Windows SmartScreen:* If downloading the direct EXE, Windows may show 'Windows protected your PC' because digital publisher reputation is newly registered. Click 'More info' ➔ 'Run anyway'.`
  },
  {
    keywords: ["server.py", "sync", "cloud", "database", "multi-device"],
    question: "How do I deploy and connect the optional cloud sync server?",
    answer: `CommitMaster operates in **Dual-Mode**:
- **Local Mode (Default):** Runs with zero configuration using local SQLite with WAL mode.
- **Cloud Mode:** You can deploy the included \`server.py\` (Flask + SQLite/Postgres) to Render, Railway, or VPS.

To connect:
1. In CommitMaster settings, toggle **Storage Mode** to **Remote Cloud Server**.
2. Enter your server URL (e.g., \`https://your-commitmaster-server.onrender.com\`).
3. Log in with your email and password to sync your tracked repositories across all your Windows laptops.`
  }
];

export const QUICK_SUGGESTIONS = [
  "How to connect LM Studio or Ollama?",
  "Why am I not seeing notification toasts?",
  "How does the Pre-Commit Security Scanner work?",
  "Microsoft Store vs Direct MSIX download?",
  "Setup GitHub accounts and push protection",
  "Report an issue or open a support ticket"
];
