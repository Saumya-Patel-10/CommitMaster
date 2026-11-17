# Git commit/push hang: root cause, fix, evidence, and roadmap

Date: 2026-11-17. Machine: Windows 11 (10.0.26300), 24 logical cores, 31.4 GB RAM, Python 3.12.10, Git for Windows 2.56.
All measurements below were taken on that machine against disposable repositories and local test remotes.
No real GitHub repository, tailnet, or production service was touched.

## 1. Architecture summary (what is actually in the repo)

| Part | Technology | Entry |
|---|---|---|
| User app | Python 3.12, Tkinter/customtkinter, SQLite | `app.py` → `commitmaster/user_dashboard.py` |
| Admin app | same stack, separate process and data dir | `admin_app.py` (276 KB, contains a copy of the Git Desktop UI) |
| Demo app | same stack, product lock `demo` | `demo_app.py` → user session |
| Backend | Flask + SQLite | `server.py` (112 KB) |
| Git layer | `git` CLI via subprocess | `commit_engine.py`, `git_safety.py`, now `git_runner.py`, `git_ops.py` |
| Packaging | PyInstaller, Inno Setup, MSIX scripts | `build_exe.py`, `build_installer.py`, `build_msix.py` |

There is no web front end, no React and no WebGL anywhere. Graphs are matplotlib/Tk (`charts.py`). Phases 7 and 8 therefore
mean new Tk (or embedded web view) work, not an upgrade of an existing 3D stack.

## 2. Root cause of the stuck "Committing..."

Reproduced and fixed. Several independent defects each produce the same symptom.

| # | Defect | Evidence | Status |
|---|---|---|---|
| R1 | `git_safety._askpass_script()` called `os.fchmod`, which does not exist on Windows. Every push that used a GitHub account token raised `AttributeError` after 0.14 s (reproduced). Because the worker thread in `commit_composer.commit()` had no `try/except` around the push, the thread died, `_busy` stayed `True`, and the label stayed on "⏳ Committing..." forever. It also leaked one temp file per attempt. | repro run; regression test `test_token_push_over_http_works_on_this_platform_and_never_leaks`, `test_runner_crash_still_reaches_terminal_state` | Fixed |
| R2 | The label said "Committing..." for the whole run, including the push, so a slow push looked like a hung commit. | code read, `commit_composer.py` old L620 | Fixed (live stage panel) |
| R3 | `subprocess.run(timeout=)` kills only `git.exe`. Hooks and `git-remote-https` keep the pipes open, so the call can block past its timeout. Reproduced with a hook: the process tree survived, and a `close()` on a pipe held by a live reader deadlocked. | `test_timeout_kills_grandchildren_that_hold_the_pipe`, `test_cancel_during_commit_hook_kills_process_tree` | Fixed (Job Object + tree kill) |
| R4 | No stdin (`DEVNULL`) and no `GIT_TERMINAL_PROMPT=0` on several commands. `ls-remote` verification ran without credentials or prompt suppression, so it could wait on a credential prompt hidden by `CREATE_NO_WINDOW`. | `test_hook_waiting_for_stdin_cannot_hang_the_commit` | Fixed |
| R5 | No per-repository lock (audit FINDING-GIT-01). 5 simultaneous commits raced on `refs/heads`. | `test_concurrent_commits_are_serialised_not_corrupted` | Fixed (thread + OS file lock in `.git`) |
| R6 | After a push to a URL (token path) `refs/remotes/origin/<branch>` was never updated, so pushed commits kept showing as "unpushed". | `test_normal_commit_and_push_updates_tracking_and_verifies` | Fixed |
| R7 | Detached HEAD: `current_branch()` returns `"HEAD"` and the push ran against it. | `test_detached_head_commit_ok_push_refused` | Fixed (refused with advice) |
| R8 | Push/commit during an unfinished merge/rebase could create a wrong commit. | `test_unresolved_merge_conflict_blocks_commit` | Fixed (refused, repo untouched) |
| R9 | Blind second push after a failure (`"Personal Access Token" in msg` → push again). | code read | Removed; no automatic retry |
| R10 | Pre-commit file inspection ran on the UI thread. | code read | Moved to a worker thread |
| R11 | `messagebox` was called from a worker thread in two push handlers, and `do_push` had no exception handling. | code read | Fixed in `user_dashboard.py`, `admin_app.py`, `admin_portal.py` |

## 3. What was built

* `commitmaster/git_runner.py`: process runner (stdin closed, prompts disabled, wall-clock + idle timeout, cancellation,
  Job Object tree kill on Windows, byte-faithful output, live line callbacks) and `RepoLock` (thread + cross-process,
  released by the OS if the process dies).
* `commitmaster/git_safety.py`: portable `#!/bin/sh` askpass helper; remote check with the same credentials as the push;
  tri-state remote check (sha / ref absent / unknown); after a timeout or cancel the real remote state decides between
  *failed* and *uncertain*; failure classification (`auth`, `not_found`, `non_fast_forward`, `protected_branch`, `network`,
  `detached_head`, `stalled`, ...) with advice; tracking-ref and upstream sync after a verified push; atomic ledger write.
  Existing guarantees (no force push, no `--no-verify`, confirmation required, uncertain-push ledger, demo block) are unchanged.
* `commitmaster/git_ops.py`: one operation per repository, observable and cancellable; separate `commit_state` and
  `push_state`; terminal states `succeeded`, `committed_not_pushed`, `failed`, `cancelled`; always reaches a terminal state;
  crash journal and `recover_interrupted_operations()` (an interrupted push becomes "uncertain" and is not retried blindly).
* `commitmaster/operation_panel.py`: stage checklist, elapsed time, real git percentage (only when git printed one),
  "no output for N s" warning, Cancel, expandable log, Copy log, separate commit and push result lines.
* `commit_composer.py` rewired to the above; a rebuilt page re-attaches to a running operation.

## 4. Test evidence (this machine, this session)

Baseline before any change: `149 passed, 2 failed` (`test_06_admin_portal_responsive...` and `test_09_impersonation_has_no_admin_power`).

After: `python -m pytest tests -q`: **185 passed, 1 failed**. The 1 failure is `test_09_impersonation_has_no_admin_power`,
the pre-existing timezone defect (audit SEC-04), not touched. `test_06` passed in the later runs; it is a Tk test and was flaky
in the baseline, so do not count it as fixed by this work.

New tests: `tests/test_git_ops.py` (32), `tests/test_operation_panel.py` (3). Scenarios from the requested list:

| Scenario | Test | Result |
|---|---|---|
| Normal commit / normal push / existing commits push | `test_normal_commit_only`, `..._and_push_...`, `test_existing_commit_push_only` | pass |
| Multiple changed files, per-file commits | `test_multiple_files_only_selected_are_committed`, `test_individual_commits_one_per_file` | pass |
| Large repository | `test_large_repository`: 4001 files, 2-file commit+push | 3.11 s total |
| Authentication failure / token push over HTTP (Basic auth, real `git http-backend`) | `test_authentication_failure_...`, `test_token_push_over_http_...` | pass, token absent from log |
| Network disconnection | `test_network_unreachable_fails_fast_...` | pass, `network` reason |
| Push rejection (non-fast-forward) | `test_non_fast_forward_rejection_...` | pass, remote untouched, local commit kept |
| Merge conflict | `test_unresolved_merge_conflict_blocks_commit` | pass |
| Detached HEAD, missing upstream | `test_detached_head_...`, `test_missing_upstream_is_set_...` | pass |
| Cancellation (push, hook) | `test_cancel_during_upload_...`, `test_cancel_during_commit_hook_...` | pass, no git child left running |
| Stalled push | `test_stalled_push_hits_idle_timeout_...` | pass, verified against the remote |
| Repeated clicks | `test_repeated_clicks_start_one_operation` | 5/5 refused, exactly 1 commit |
| Restart during an operation | `test_restart_during_operation_is_recovered_and_lock_released`, `test_restart_during_push_marks_push_uncertain` | pass (child killed with `taskkill /T /F`) |
| UI stays responsive | `test_commit_shows_stages_stays_responsive_...` | worst Tk event-loop gap **109 ms** during a 3 s hook commit |

Overhead check: `git rev-parse` through `run_process` median 40.4 ms vs 40.5 ms with `subprocess.run` (40 runs each).

## 5. Performance bottleneck report (partial, honest)

Only the Git path was profiled. The "laggy app" claim is **not yet** explained beyond the following measured/read facts:

* Every git call costs about 40 ms on this machine. `CommitComposer._update_commit_button()` calls `current_branch()` (a git
  process) on the UI thread on every selection change/re-render; `get_unpushed_commits()` and `ask_push_confirmation()` do too.
* `user_dashboard.py` (260 KB) and `admin_app.py` (276 KB) are single huge classes that rebuild whole pages with `_nav_to`.
* `commit_engine.uncommitted_changes` has a cache; `file_inspector` caches per file by mtime/size.
* Not measured yet: idle CPU, memory growth, startup time, page-rebuild cost, DB query plans.

## 6. Three-app separation assessment (from the code, not from the prior audit docs)

* `app.py` and `demo_app.py` do not import `admin_app` or `admin_portal`. `build_exe.py` excludes both modules from the
  user and demo builds (L60-66). That boundary looks correct. Not verified by inspecting a built executable.
* `admin_app.py` contains a full copy of the Git Desktop screens. It duplicates the code that had the bugs above; I patched the
  push handlers, but the duplication remains a maintenance risk (every fix must be made twice).
* **Open, confirmed in code, not fixed:** `server.py:336` and `server.py:380` still trust the client-supplied
  `Tailscale-User-Login` header and let `X-Tailscale-Auth: 1` trigger the Tailscale login path (audit SEC-01). I read the code;
  I did not exploit it. Changing it alters how remote users authenticate through `tailscale serve`, so it needs your approval.
* `server.py` uses naive `datetime.now()` in many places, matching the SEC-04 timezone failure in `test_09`.

## 7. Not done (so nothing here is claimed as complete)

Phase 3 profiling and optimisation; Phase 4 enforcement checks on built executables; Phase 5 multi-account rework (secure OS
credential storage, wrong-identity prevention beyond not guessing between several accounts); Phase 6 analysis engine and agents;
Phase 7 graph engine; Phase 8 UI redesign and 3D; Phase 9 Tailscale redesign; Phase 10 release verification. The startup
recovery result is logged only; there is no UI notice for it yet. The operation panel was exercised through Tk tests, not by
eye in the packaged app. SSH remotes were not tested.

## 8. Roadmap (priority order)

1. **Security (needs approval):** SEC-01/02/03 in `server.py`, SEC-04 UTC timestamps, then make `test_09` pass.
2. **Performance:** profile startup, page rebuilds and UI-thread git calls; cache branch/ahead-behind; move the remaining UI-thread git calls off the UI thread.
3. **Duplication:** extract the shared Git Desktop UI out of `admin_app.py`, or drop it from the admin app.
4. **Accounts:** OS credential store (Windows Credential Manager / `keyring`) instead of SQLite tokens; per-repo identity confirmation.
5. **Tailscale:** architecture proposal, test tailnet, rollback plan, before any live change.
6. Analysis/agents, graph engine, UI/3D.
