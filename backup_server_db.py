"""
Automated Hot-Backup Utility for CommitMaster Server.
Performs non-blocking online SQLite database backups while users are actively connected.
"""
import os
import sqlite3
import datetime
import glob

SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.getenv("SERVER_DB_PATH", os.path.join(SERVER_DIR, "server_commitmaster.db"))
BACKUP_DIR = os.path.join(SERVER_DIR, "backups")

def run_backup(retention_days: int = 30):
    if not os.path.exists(DB_FILE):
        print(f"Database file not found: {DB_FILE}")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"commitmaster_backup_{ts}.db")

    print(f"Creating hot backup of {DB_FILE}...")
    source_conn = sqlite3.connect(DB_FILE)
    dest_conn = sqlite3.connect(backup_file)

    try:
        # SQLite Online Backup API (Atomic, non-locking hot backup)
        source_conn.backup(dest_conn, pages=100)
        print(f"Backup completed successfully: {backup_file}")
    finally:
        dest_conn.close()
        source_conn.close()

    # Clean old backups exceeding retention_days
    cutoff = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    for old_file in glob.glob(os.path.join(BACKUP_DIR, "commitmaster_backup_*.db")):
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(old_file))
            if mtime < cutoff:
                os.remove(old_file)
                print(f"Pruned expired backup: {os.path.basename(old_file)}")
        except Exception:
            pass

if __name__ == "__main__":
    run_backup()
