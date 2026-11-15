# CommitMaster — Cloud Deployment & Multi-Device Architecture Guide

This guide explains how CommitMaster is architected for multi-device synchronization, how to deploy your central cloud backend so users can log in from any Windows computer, and how you manage users as the Administrator.

---

## 1. 🔍 Root Cause of the Issue on the Second Device

When you downloaded CommitMaster on your second device, two things happened:

1. **Local SQLite Storage vs Cloud Database**:
   - Previously, CommitMaster stored all accounts and session logs exclusively in a local SQLite file (`commitmaster.db`) on your first machine.
   - Because `*.db` is excluded by `.gitignore` (which is standard practice to avoid leaking local credentials into public git commits), the second device had a brand new, empty local database file. It had no access to the accounts created on your primary PC.
2. **Account Creation Bug (`check_user_exists`)**:
   - When you tried creating a new account on the second device, `login_window.py` called `db.check_user_exists(username, email)`, but `check_user_exists` had not been implemented in `commitmaster/database.py`.
   - This caused an unhandled `AttributeError`, causing account registration to fail on fresh installs.

---

## 2. 🛠️ What Was Fixed & Implemented

1. **Fixed Account Registration**:
   - Implemented `check_user_exists(username, email)` in `commitmaster/database.py`.
   - Added user validation and friendly in-app error feedback to `login_window.py`.
2. **Central Cloud Backend Server (`server.py`)**:
   - A complete REST API server built with Flask.
   - Endpoints for user registration, authentication, session tokens, activity logs, metrics timeseries, and administrative user management.
   - Includes a Web Status Dashboard at `http://your-server-url/`.
   - Supports both **SQLite** (default) and **PostgreSQL** (e.g. Supabase, Neon, Render Postgres via `DATABASE_URL`).
3. **Dual-Mode Data Access Layer (`commitmaster/database.py`)**:
   - **Cloud Mode**: When `server_url` is configured in `config.json` or in the app UI, all login, signup, session, and activity calls seamlessly communicate with your central server via HTTPS.
   - **Local Mode**: When `server_url` is left empty or when working offline, the app operates against local `commitmaster.db`.
4. **Interactive In-App Server Settings**:
   - The Sign In window (`LoginWindow`) features a connection status badge (`🌐 Cloud: ...` or `💻 Local Offline Database`) and a **"⚙ Server Settings"** button.
   - Users and admins can enter a Server URL, click **"🔌 Test Connection"**, and save changes on the fly.
   - Advanced tab in **Settings** (`settings_ui.py`) also includes a Cloud Backend configuration section.
5. **Database Migration Script (`migrate_to_server.py`)**:
   - Automatically migrates existing local accounts (such as `saumya.patel`) to your deployed cloud server.
6. **1-Click Cloud Deployment Configurations**:
   - `render.yaml` (Free Render Web Service blueprint)
   - `railway.json` (1-click Railway deployment)
   - `Procfile` & `Dockerfile`
   - `Launch_Server.bat` (1-click local/home network server launcher)

---

## 3. 🚀 Deploying Your Central Backend Server

You can deploy the CommitMaster server in any of the following ways:

### Option A: Free Cloud Deployment on Render.com (Recommended — 2 Minutes)

Render provides free cloud web service hosting:

1. **Push your updated CommitMaster repository to GitHub**.
2. Go to **[Render.com](https://render.com)** and sign in with GitHub.
3. Click **New +** → **Blueprint** (or **Web Service**).
4. Select your **CommitMaster** repository.
   - Render will automatically detect `render.yaml`.
   - **Environment**: Python
   - **Build Command**: `pip install -r requirements-server.txt`
   - **Start Command**: `gunicorn server:app`
5. Click **Apply / Deploy**.
6. Render will generate a public HTTPS URL for your server:
   ```
   https://commitmaster-server-xxxx.onrender.com
   ```
7. Visit this URL in your web browser: you will see the **CommitMaster Server Web Dashboard** showing that the server is online.

---

### Option B: Deploying on Railway.app

1. Go to **[Railway.app](https://railway.app)**.
2. Click **New Project** → **Deploy from GitHub repo** → select **CommitMaster**.
3. Railway automatically detects `railway.json` and runs `gunicorn server:app`.
4. In Railway project settings, generate a domain (e.g. `https://commitmaster-production.up.railway.app`).

---

### Option C: Self-Hosting Locally or on Your Home PC / VPS

If you want to run the server on your primary PC:
1. Double-click **`Launch_Server.bat`** (or run `python server.py`).
2. The server starts on `http://0.0.0.0:8000`.
3. To access from other devices on the same Wi-Fi / LAN, use your local IP address:
   ```
   http://192.168.1.xxx:8000
   ```
4. (Optional) Use a free Cloudflare Tunnel or ngrok to give it a public HTTPS URL:
   ```powershell
   ngrok http 8000
   ```

---

## 4. 📦 Migrating Existing Local Accounts to the Server

To push your existing admin account (`saumya.patel`) and user accounts from your local database to your deployed cloud server:

```powershell
# If using a cloud server:
python migrate_to_server.py --server https://your-commitmaster.onrender.com

# If running locally on port 8000:
python migrate_to_server.py
```

Output:
```
Target Server Online: CommitMaster Cloud Backend (v3.0)
Found user account(s) to migrate:
  • [ADMIN] saumya.patel (saumya.a.patel@gmail.com)
  • [USER] notrealbutfr_yt (samual100806@gmail.com)
SUCCESS: Successfully migrated user account(s)!
```

---

## 5. 💻 Connecting from Any Windows Device

### On Any Client Device:
1. Download or clone CommitMaster on the second Windows PC.
2. Run `pip install -r requirements.txt`.
3. Launch the public user app with `python app.py`. That process has no Admin Portal. The private admin console is `python admin_app.py`, and the demo is `python demo_app.py`.
4. On the **Sign In** screen of the user app, look at the footer:
   - Click **"⚙ Server Settings"**.
   - Enter your Cloud Server URL: `https://your-commitmaster.onrender.com`.
   - Click **"🔌 Test Connection"** → Verify it shows `✔ Connected`.
   - Click **"💾 Save & Connect"**.
5. **Sign in** with your account credentials (`saumya.patel`, etc.) OR click **"Create one"** to register a new account.
6. The account is validated and stored on the central cloud server!

> [!TIP]
> **Pre-configuring for distributed users:**
> You can also put `"server_url": "https://your-commitmaster.onrender.com"` directly inside `config.json` before building the user executable (`CommitMaster-User.exe`). Build the three executables separately, as described in `README.md`. The admin and demo packages are not the Store user package.

---

## 6. Administrator access is a separate program

The public user app does not open an admin portal and does not treat a username as an administrator. Administrative account controls run only in `admin_app.py` / `CommitMaster-Admin.exe`, which is a different process and a different package identity.

Server admin routes require an admin-scoped session from `POST /api/admin/login` plus a TOTP code. Set `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `ADMIN_TOTP_SECRET` on the server host. They are not shipped inside the user executable. An impersonation session is separate from that admin session. This guide does not deploy the server or publish a desktop package.

---

## 7. Tests

From the repository root:

```powershell
python -m unittest discover -s tests -t .
```

That command is the suite. This guide does not record a pass count. Clean-machine install, Start Menu launch, MSIX packaging, and Microsoft Store submission were not run for this revision.
