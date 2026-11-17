# Performance report (first pass)

Hardware / methodology: Windows 11 (10.0.26300), 24 logical CPUs, git 2.56.0.windows.4, Python 3.12.
Each figure is the median of 10-30 runs after one warm-up, on this repository (about 400 tracked files),
measured with `time.perf_counter()` in a standalone script. They are single-machine numbers; they are not a
guarantee for other machines, repository sizes, or antivirus configurations.

## What was measured before changing anything

| Item | Before |
|------|--------|
| `import commitmaster.database` | 93 ms |
| `import commitmaster.user_dashboard` | 43 ms (so import time is not the startup bottleneck) |
| Any `git` subprocess (`rev-parse`, `remote get-url`, `status` …) | 40-43 ms each |
| `get_unpushed_commits` (branch without upstream) | 122 ms (three git processes, one guaranteed to fail and log a warning) |
| `uncommitted_changes` | 43 ms uncached; 0 ms on a cache hit (an existing TTL cache already works) |

The dominant cost is process spawn: every UI refresh that asks a git question pays about 40 ms on the Tk
thread per question. `current_branch` alone has 21 call sites.

## Changes

| Change | Before | After |
|--------|--------|-------|
| `current_branch` reads `.git/HEAD` (new `commitmaster/git_fast.py`) | 40.7 ms (p90 43.4) | 0.07 ms (p90 0.10) |
| `get_unpushed_commits` skips the doomed `git log origin/x..x` when the remote ref is absent | about 122 ms | 42.3 ms (p90 46.5) |

`git_fast` returns "I don't know" (and the old git command runs) for reftable storage, `GIT_DIR` overrides,
bare repositories and unreadable or unusual files. `tests/test_git_fast.py` compares it with real git for plain,
slash-named, detached, unborn, packed-refs, subdirectory and linked-worktree layouts, and asserts no process
is spawned on the fast path.

## Not done yet (be skeptical of any claim that this is "optimized")

* Other UI-thread git calls (`get_branches`, `get_remote_url`, `get_repo_commit_count`, each about 40 ms) are
  unchanged, and none of them has been moved off the Tk thread. Page rebuilds have not been profiled.
* The monolithic `user_dashboard.py` / `admin_app.py` (several thousand lines each) and the duplicated Git
  Desktop UI in the admin app are unchanged.
* No end-to-end startup, memory or large-repository (100k+ file) measurement of the packaged executables.
* Nothing has been measured on a second machine.
