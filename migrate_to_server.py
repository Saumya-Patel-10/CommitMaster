"""
CommitMaster — profile migration helper.
========================================
Copies profile fields (username, email, display name, avatar color) to the
server. It does not send password hashes, GitHub tokens, or a migration
secret. The server requires an admin-scoped bearer token and forces every
imported row to a standard user.

Usage:
  python migrate_to_server.py --server https://example.invalid --token "$ADMIN_TOKEN"
"""

import os
import sys
import argparse
import sqlite3
import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB = os.path.join(APP_DIR, "commitmaster.db")
PROFILE_FIELDS = ("username", "email", "full_name", "avatar_color")


def migrate(server_url: str, token: str) -> bool:
    server_url = server_url.rstrip("/")
    if not token:
        print("Error: an admin-scoped bearer token is required (--token).")
        return False
    print(f"Source database: {LOCAL_DB}")
    print(f"Target server:   {server_url}")
    if not os.path.exists(LOCAL_DB):
        print(f"Error: local database '{LOCAL_DB}' does not exist.")
        return False

    try:
        health = requests.get(f"{server_url}/api/health", timeout=10)
    except Exception as exc:
        print(f"Error: cannot connect to {server_url}: {exc}")
        return False
    if health.status_code != 200:
        print(f"Error: server healthcheck failed with status {health.status_code}")
        return False

    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    payloads = []
    for row in conn.execute("SELECT username, email, full_name, avatar_color FROM users"):
        payloads.append({field: row[field] or "" for field in PROFILE_FIELDS})
    conn.close()

    print(f"Sending {len(payloads)} profile(s). Passwords and tokens stay local.")
    response = requests.post(
        f"{server_url}/api/admin/migrate-seed",
        json={"users": payloads},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if response.status_code != 200:
        print(f"Migration failed: HTTP {response.status_code}: {response.text}")
        return False
    print(f"Server accepted the profile import: {response.json()}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy local profile fields to the CommitMaster server")
    parser.add_argument("--server", default="http://localhost:8000", help="CommitMaster server URL")
    parser.add_argument("--token", default=os.getenv("COMMITMASTER_ADMIN_TOKEN", ""), help="Admin-scoped bearer token")
    args = parser.parse_args()
    sys.exit(0 if migrate(args.server, args.token) else 1)
