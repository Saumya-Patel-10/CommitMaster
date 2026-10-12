"""Smoke tests for CommitMaster core engine.

Run with:  python smoke_test.py
All tests operate on a temporary git repo and do NOT touch your real projects.
"""
import json
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")  # allow Unicode on Windows console
sys.path.insert(0, r"C:\Data\Saumya\Projects\CommitMaster")

from commitmaster import commit_engine
from commitmaster.config import load_config, DEFAULTS

REPO = os.path.join(tempfile.gettempdir(), "commitmaster_test_repo")


def g(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)


def setup_repo():
    subprocess.run(["rmdir", "/s", "/q", REPO], shell=True, capture_output=True)
    os.makedirs(os.path.join(REPO, "src"), exist_ok=True)
    os.makedirs(os.path.join(REPO, "docs"), exist_ok=True)
    os.makedirs(os.path.join(REPO, "tests"), exist_ok=True)

    assert g("init", "-q").returncode == 0, "git init failed"
    g("config", "user.name", "Test")
    g("config", "user.email", "test@example.com")

    # Initial commit
    open(f"{REPO}/src/app.py",    "w").write("print('hello')\n")
    open(f"{REPO}/README.md",     "w").write("# demo\n")
    open(f"{REPO}/.env",          "w").write("SECRET=x\n")
    open(f"{REPO}/config.json",   "w").write("{}\n")
    g("add", "."); g("commit", "-qm", "init")

    # Make dirty changes
    open(f"{REPO}/.env",                    "a").write("SECRET2=y\n")
    open(f"{REPO}/src/app.py",             "a").write("print('changed')\n")
    open(f"{REPO}/src/newfeature.py",      "w").write("def feature(): pass\n")
    open(f"{REPO}/tests/test_app.py",      "w").write("def test_x(): pass\n")
    open(f"{REPO}/docs/guide.md",          "w").write("guide\n")


def test_repo_discovery():
    assert commit_engine.is_git_repo(REPO), "is_git_repo failed"
    repos = commit_engine.list_repos([tempfile.gettempdir()])
    assert REPO in repos, f"repo not found in: {repos}"
    print("✔  repo discovery")


def test_uncommitted_changes():
    changes = commit_engine.uncommitted_changes(REPO)
    assert changes, "should have uncommitted changes"
    print(f"✔  uncommitted_changes ({len(changes)} files): {changes}")


def test_grouping():
    sensitive = DEFAULTS["sensitive_patterns"]
    changes = commit_engine.uncommitted_changes(REPO)
    groups = commit_engine.build_groups(changes, sensitive_patterns=sensitive)
    print("  groups:", json.dumps(groups, indent=2))

    assert "sensitive" in groups and any(".env" in f for f in groups["sensitive"]), \
        "sensitive detection failed"
    assert any("test_app" in f for f in groups.get("test", [])), "test grouping failed"
    assert any("guide.md" in f for f in groups.get("docs", [])), "docs grouping failed"
    assert any("newfeature" in f for f in groups.get("feat", [])), "feat grouping failed"
    print("✔  file grouping")


def test_commit():
    sensitive = DEFAULTS["sensitive_patterns"]
    changes = commit_engine.uncommitted_changes(REPO)
    groups = commit_engine.build_groups(changes, sensitive_patterns=sensitive)

    summary = commit_engine.stage_and_commit(REPO, groups["code"], "refactor: update app output")
    print(f"  commit summary: {summary}")
    assert "refactor: update app output" in commit_engine.git(REPO, "log", "--oneline")
    print("✔  stage_and_commit")


def test_sensitive_not_committed():
    remaining = commit_engine.uncommitted_changes(REPO)
    assert any(".env" in f for _, f in remaining), ".env should NOT have been committed"
    print("✔  sensitive file protection")


def test_diff_summary():
    diff = commit_engine.diff_summary(REPO)
    assert diff, "diff_summary returned empty"
    print(f"✔  diff_summary ({len(diff)} chars)")


def test_config_defaults():
    cfg = load_config()
    assert "ai" in cfg, "'ai' key missing from config"
    assert "base_url" in cfg["ai"], "'base_url' missing from ai config"
    assert "model" in cfg["ai"], "'model' key missing from ai config"
    print("✔  config defaults (ai section)")


def test_github_desktop_find():
    path = commit_engine.find_github_desktop()
    if path:
        print(f"✔  GitHub Desktop found at: {path}")
    else:
        print("ℹ  GitHub Desktop not installed (OK — auto-detect returned None)")


if __name__ == "__main__":
    print("=" * 50)
    print("CommitMaster smoke tests")
    print("=" * 50)
    setup_repo()
    test_repo_discovery()
    test_uncommitted_changes()
    test_grouping()
    test_commit()
    test_sensitive_not_committed()
    test_diff_summary()
    test_config_defaults()
    test_github_desktop_find()
    print("=" * 50)
    print("ALL TESTS PASSED ✔")
