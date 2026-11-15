"""Stage the three product trees. This does not sign an MSIX and does not publish the Store app."""
from __future__ import annotations

import hashlib
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXCLUDED_DIRS = {
    ".git", ".github", "dist", "build", "msix_layout", "tests", "__pycache__",
    ".agents", "packaging",
}
USER_EXCLUDED_FILES = {
    "admin_app.py", "demo_app.py", "server.py", "admin_portal.py", "admin_client.py",
    "Launch_Admin_App.bat", "Launch_Admin_App.vbs", "generate_pdf_guide.py",
    "migrate_to_server.py", "backup_server_db.py", "build_exe.py", "build_msix.py", "build_installer.py",
}
ADMIN_EXCLUDED_FILES = {
    "demo_app.py", "server.py", "Launch_Admin_App.bat", "Launch_Admin_App.vbs",
}
DEMO_EXCLUDED_FILES = {
    "admin_app.py", "server.py", "admin_portal.py", "admin_client.py",
    "Launch_Admin_App.bat", "Launch_Admin_App.vbs",
}
SECRET_SUFFIXES = (".pem", ".pfx", ".key")
SECRET_NAMES = {".admin_initial_secret", ".admin_totp_secret", "server_commitmaster.db", "commitmaster.db"}


def _copy_tree(destination: str, excluded_files: set) -> None:
    if os.path.exists(destination):
        shutil.rmtree(destination)
    os.makedirs(destination)

    def ignore(directory, names):
        ignored = []
        base = os.path.basename(directory)
        if base in EXCLUDED_DIRS or base == "__pycache__":
            return names
        for name in names:
            if name in EXCLUDED_DIRS or name.endswith(".pyc") or name in SECRET_NAMES or name.endswith(SECRET_SUFFIXES):
                ignored.append(name)
            elif name in excluded_files:
                ignored.append(name)
        return ignored

    for name in os.listdir(ROOT):
        if name in EXCLUDED_DIRS or name in excluded_files or name in SECRET_NAMES:
            continue
        source = os.path.join(ROOT, name)
        target = os.path.join(destination, name)
        if os.path.isdir(source):
            shutil.copytree(source, target, ignore=ignore)
        elif os.path.isfile(source):
            shutil.copy2(source, target)


def stage_all(output_root: str) -> dict:
    identities = json.load(open(os.path.join(ROOT, "packaging", "identities.json"), encoding="utf-8"))
    trees = {
        "user": (os.path.join(output_root, "CommitMaster-User"), USER_EXCLUDED_FILES),
        "admin": (os.path.join(output_root, "CommitMaster-Admin"), ADMIN_EXCLUDED_FILES),
        "demo": (os.path.join(output_root, "CommitMaster-Demo"), DEMO_EXCLUDED_FILES),
    }
    result = {}
    for product, (path, excluded) in trees.items():
        _copy_tree(path, excluded)
        manifest = os.path.join(path, "PACKAGE_IDENTITY.json")
        with open(manifest, "w", encoding="utf-8") as handle:
            json.dump(identities[product], handle, indent=2)
        digest = _hash_tree(path)
        result[product] = path
        result[product + "_sha256"] = digest
    return result


def _hash_tree(path: str) -> str:
    hasher = hashlib.sha256()
    for dirpath, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, path).replace("\\", "/")
            hasher.update(rel.encode("utf-8"))
            with open(full, "rb") as handle:
                hasher.update(handle.read())
    return hasher.hexdigest()


if __name__ == "__main__":
    destination = os.path.join(ROOT, "dist", "staged")
    built = stage_all(destination)
    for key, value in built.items():
        print(f"{key}: {value}")
