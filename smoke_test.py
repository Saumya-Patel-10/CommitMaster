import os, subprocess, sys, tempfile, json
sys.path.insert(0, r"C:\Data\Saumya\Projects\CommitMaster")

from commitmaster import commit_engine

repo = os.path.join(tempfile.gettempdir(), "commitmaster_test_repo")
subprocess.run(["rmdir", "/s", "/q", repo], shell=True, capture_output=True)
os.makedirs(os.path.join(repo, "src"), exist_ok=True)
os.makedirs(os.path.join(repo, "docs"), exist_ok=True)

def g(*a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)

assert g("init", "-q").returncode == 0, g("init").stderr
g("config", "user.name", "Test"); g("config", "user.email", "t@t.com")
open(f"{repo}/src/app.py", "w").write("print('hello')\n")
open(f"{repo}/README.md", "w").write("# demo\n")
open(f"{repo}/.env", "w").write("SECRET=x\n")
open(f"{repo}/config.json", "w").write("{}\n")
g("add", "."); g("commit", "-qm", "init")
open(f"{repo}/.env", "a").write("SECRET2=y\n")
open(f"{repo}/src/app.py", "a").write("print('changed')\n")
open(f"{repo}/src/newfeature.py", "w").write("def feature(): pass\n")
open(f"{repo}/tests/test_app.py", "w").write("def test_x(): pass\n") if os.makedirs(f"{repo}/tests", exist_ok=True) is None else None
open(f"{repo}/docs/guide.md", "w").write("guide\n")

assert commit_engine.is_git_repo(repo)
assert repo in commit_engine.list_repos([tempfile.gettempdir()]), "repo discovery failed"

changes = commit_engine.uncommitted_changes(repo)
print("changes:", changes)
groups = commit_engine.build_groups(changes)
print("groups:", json.dumps(groups, indent=1))
assert "sensitive" in groups and any(".env" in f for f in groups["sensitive"]), "sensitive detection failed"
assert any("test_app" in f for f in groups.get("test", [])), "test grouping failed"
assert any("guide.md" in f for f in groups.get("docs", [])), "docs grouping failed"
assert any("newfeature" in f for f in groups.get("feat", [])), "feat grouping failed"

msg = commit_engine.stage_and_commit(repo, groups["code"], "fix: update app output")
print("commit:", msg)
log = commit_engine.git(repo, "log", "--oneline")
assert "fix: update app output" in log
# sensitive file must remain uncommitted
remaining = commit_engine.uncommitted_changes(repo)
assert any(".env" in f for _, f in remaining), ".env should not have been committed"
print("ALL ENGINE TESTS PASSED")
