"""
CommitMaster — Database Migration & Cloud Seeder.
=================================================
Transfers existing local accounts, passwords, and preferences from
local 'commitmaster.db' to the CommitMaster Cloud Backend Server.

Usage:
  # To migrate to a local running server:
  python migrate_to_server.py

  # To migrate to a deployed cloud server (e.g. on Render):
  python migrate_to_server.py --server https://your-commitmaster.onrender.com
"""

import os
import sys
import argparse
import sqlite3
import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB = os.path.join(APP_DIR, "commitmaster.db")

def migrate(server_url: str, secret_key: str = ""):
    server_url = server_url.rstrip("/")
    if not secret_key:
        secret_key = os.getenv("ADMIN_MIGRATION_SECRET", "").strip()
    if not secret_key:
        print("Error: Migration requires an admin migration secret via --secret or ADMIN_MIGRATION_SECRET.")
        return False
    print("=" * 60)
    print("CommitMaster — Database Cloud Migration")
    print("=" * 60)
    print(f"Source Database: {LOCAL_DB}")
    print(f"Target Server:   {server_url}")

    if not os.path.exists(LOCAL_DB):
        print(f"Error: Local database '{LOCAL_DB}' does not exist.")
        return False

    # Verify server connectivity
    try:
        resp = requests.get(f"{server_url}/api/health", timeout=10)
        if resp.status_code != 200:
            print(f"Error: Server healthcheck failed with status {resp.status_code}")
            return False
        health_data = resp.json()
        print(f"Target Server Online: {health_data.get('service')} (v{health_data.get('version')})")
    except Exception as exc:
        print(f"Error: Cannot connect to {server_url}: {exc}")
        return False

    # Read local users
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    users = conn.execute("SELECT * FROM users").fetchall()
    user_payloads = []
    for u in users:
        u_dict = dict(u)
        user_payloads.append({
            "username": u_dict["username"],
            "email": u_dict["email"],
            "full_name": u_dict.get("full_name", ""),
            "password_hash": u_dict["password_hash"],
            "role": u_dict.get("role", "user"),
            "avatar_color": u_dict.get("avatar_color", "#3fb950"),
            "is_active": u_dict.get("is_active", 1),
        })
    conn.close()

    print(f"Found {len(user_payloads)} user account(s) to migrate:")
    for u in user_payloads:
        role_label = "[ADMIN]" if u["role"] == "admin" else "[USER]"
        print(f"  • {role_label} {u['username']} ({u['email']})")

    # Post to migration endpoint
    print("\nUploading user accounts to target server...")
    try:
        resp = requests.post(
            f"{server_url}/api/admin/migrate-seed",
            json={"secret_key": secret_key, "users": user_payloads},
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            count = data.get("seeded_users", 0)
            print(f"SUCCESS: Successfully migrated {count} user account(s) to {server_url}!")
            print("\nYou can now sign in using these accounts from ANY Windows device!")
            return True
        else:
            print(f"Migration failed: HTTP {resp.status_code}: {resp.text}")
            return False
    except Exception as exc:
        print(f"Error sending migration payload: {exc}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate local CommitMaster data to Cloud Backend Server")
    parser.add_argument("--server", default="http://localhost:8000", help="CommitMaster Server URL")
    parser.add_argument("--secret", default=os.getenv("ADMIN_MIGRATION_SECRET", ""), help="Admin migration secret key")
    args = parser.parse_args()

    success = migrate(args.server, args.secret)
    sys.exit(0 if success else 1)
