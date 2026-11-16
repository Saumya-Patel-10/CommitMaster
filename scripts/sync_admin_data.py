import sqlite3
import os
import shutil
import json

src_db = os.path.expandvars(r"%LOCALAPPDATA%\CommitMaster\commitmaster.db")
dst_db = os.path.expandvars(r"%LOCALAPPDATA%\CommitMaster-Admin\commitmaster.db")
src_cfg = os.path.expandvars(r"%LOCALAPPDATA%\CommitMaster\config.json")
dst_cfg = os.path.expandvars(r"%LOCALAPPDATA%\CommitMaster-Admin\config.json")

print("=== Starting Data Sync to Admin App ===")

# 1. Copy config.json
if os.path.exists(src_cfg):
    shutil.copy2(src_cfg, dst_cfg)
    print("Copied config.json to Admin App directory.")

conn_src = sqlite3.connect(src_db)
conn_dst = sqlite3.connect(dst_db)

conn_src.row_factory = sqlite3.Row
conn_dst.row_factory = sqlite3.Row

def fix_path(p):
    if not p:
        return p
    return p.replace("Saumya\\Projects", "Saumya\\AI-Projects").replace("Saumya/Projects", "Saumya/AI-Projects").replace("Projects/CommitMaster", "AI-Projects/CommitMaster")

# a) commit_activity
print("\n--- Syncing commit_activity ---")
rows = conn_src.execute("SELECT * FROM commit_activity").fetchall()
conn_dst.execute("DELETE FROM commit_activity")
for r in rows:
    d = dict(r)
    d["repo_path"] = fix_path(d["repo_path"])
    cols = list(d.keys())
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT OR REPLACE INTO commit_activity ({','.join(cols)}) VALUES ({placeholders})"
    conn_dst.execute(sql, list(d.values()))
print(f"Synced {len(rows)} rows into commit_activity.")

conn_src.execute("UPDATE commit_activity SET repo_path = REPLACE(REPLACE(repo_path, 'Saumya\\\\Projects', 'Saumya\\\\AI-Projects'), 'Saumya/Projects', 'Saumya/AI-Projects')")
conn_src.commit()

# b) watched_repositories
print("\n--- Syncing watched_repositories ---")
rows = conn_src.execute("SELECT * FROM watched_repositories").fetchall()
conn_dst.execute("DELETE FROM watched_repositories")

seen_names = set()
for r in rows:
    d = dict(r)
    d["local_path"] = fix_path(d["local_path"])
    # If duplicate repo_full_name for user_id, make sure unique
    rfn = d["repo_full_name"]
    if rfn in seen_names:
        continue
    seen_names.add(rfn)
    cols = list(d.keys())
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT OR REPLACE INTO watched_repositories ({','.join(cols)}) VALUES ({placeholders})"
    conn_dst.execute(sql, list(d.values()))

# Ensure other AI-Projects exist
all_local_repos = [
    ("CommitMaster", r"C:\Data\Saumya\AI-Projects\CommitMaster"),
    ("CommitMaster-Website", r"C:\Data\Saumya\AI-Projects\CommitMaster-Website"),
    ("JobSeeker", r"C:\Data\Saumya\AI-Projects\JobSeeker"),
    ("Portfolio-Website", r"C:\Data\Saumya\AI-Projects\Portfolio-Website"),
    ("SentinelZero", r"C:\Data\Saumya\AI-Projects\SentinelZero"),
    ("Vin-larpr", r"C:\Data\Saumya\AI-Projects\Vin-larpr"),
]

for name, lpath in all_local_repos:
    if name not in seen_names and os.path.exists(os.path.join(lpath, ".git")):
        conn_dst.execute("""
            INSERT OR REPLACE INTO watched_repositories (user_id, repo_name, repo_full_name, default_branch, local_path, is_active_watch, created_at)
            VALUES (?, ?, ?, 'main', ?, 1, datetime('now'))
        """, (1, name, name, lpath))
        seen_names.add(name)
        print(f"Added new watched repository: {name} ({lpath})")

conn_dst.commit()
print("Watched repositories synced.")

# Update src db
conn_src.execute("UPDATE watched_repositories SET local_path = REPLACE(REPLACE(local_path, 'Saumya\\\\Projects', 'Saumya\\\\AI-Projects'), 'Saumya/Projects', 'Saumya/AI-Projects')")
conn_src.commit()

# c) repo_github_accounts
print("\n--- Syncing repo_github_accounts ---")
rows = conn_src.execute("SELECT * FROM repo_github_accounts").fetchall()
conn_dst.execute("DELETE FROM repo_github_accounts")
for r in rows:
    d = dict(r)
    d["repo_path"] = fix_path(d["repo_path"])
    cols = list(d.keys())
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT OR REPLACE INTO repo_github_accounts ({','.join(cols)}) VALUES ({placeholders})"
    conn_dst.execute(sql, list(d.values()))
print(f"Synced {len(rows)} rows into repo_github_accounts.")

# d) app_usage
print("\n--- Syncing app_usage ---")
rows = conn_src.execute("SELECT * FROM app_usage").fetchall()
conn_dst.execute("DELETE FROM app_usage")
for r in rows:
    d = dict(r)
    cols = list(d.keys())
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT OR REPLACE INTO app_usage ({','.join(cols)}) VALUES ({placeholders})"
    conn_dst.execute(sql, list(d.values()))
print(f"Synced {len(rows)} rows into app_usage.")

# e) app_events
print("\n--- Syncing app_events ---")
rows = conn_src.execute("SELECT * FROM app_events").fetchall()
conn_dst.execute("DELETE FROM app_events")
for r in rows:
    d = dict(r)
    cols = list(d.keys())
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT OR REPLACE INTO app_events ({','.join(cols)}) VALUES ({placeholders})"
    conn_dst.execute(sql, list(d.values()))
print(f"Synced {len(rows)} rows into app_events.")

conn_dst.commit()
conn_src.close()
conn_dst.close()

print("\n=== Data Sync Completed Successfully! ===")
