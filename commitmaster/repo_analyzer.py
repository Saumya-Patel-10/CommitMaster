"""
CommitMaster — Repository Status, Logs & AI Recommendations Engine.

Provides deep status analysis for watched repositories:
1. Scans logs, bugs, and failed runs (from git history, log files, database events, and code inspection).
2. Scrapes repository purpose, tech stack, and structure to generate AI-powered recommendations:
   - Specific unit & integration test cases to write
   - Impactful feature recommendations
   - Code quality, bug prevention, and architectural hardening
"""

import glob
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from commitmaster import ai_messages, commit_engine, database as db, file_inspector
from commitmaster.config import load_config
from commitmaster.logger import get

log = get("repo_analyzer")

# Cache directory for AI recommendations
RECOMMENDATIONS_CACHE: Dict[str, Dict[str, Any]] = {}


def scan_repo_status_and_logs(repo_path: str, user_id: int) -> Dict[str, Any]:
    """
    Collect comprehensive repository health, status, bugs, and log entries.
    """
    norm_path = os.path.normpath(repo_path)
    rname = commit_engine.repo_name(norm_path)
    is_git = os.path.isdir(norm_path) and commit_engine.is_git_repo(norm_path)

    branch = commit_engine.current_branch(norm_path) if is_git else "unknown"
    commits_count = commit_engine.get_repo_commit_count(norm_path) if is_git else 0
    bound_account = db.get_repo_account(user_id, norm_path)
    origin_url = commit_engine.get_remote_url(norm_path, "origin") if is_git else ""

    uncommitted = commit_engine.uncommitted_changes(norm_path) if is_git else []
    uncommitted_count = len(uncommitted)

    # 1. Failed commits from database
    db_failed_commits: List[Dict[str, Any]] = []
    try:
        conn = db.get_conn()
        cur = conn.execute("""
            SELECT * FROM commit_activity
            WHERE user_id = ? AND (repo_path = ? OR repo_name = ?) AND status != 'committed'
            ORDER BY committed_at DESC LIMIT 20
        """, (user_id, norm_path, rname))
        db_failed_commits = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        log.debug("Failed to query commit failures: %s", exc)

    # 2. Error and warning events from analytics
    error_events: List[Dict[str, Any]] = []
    try:
        conn = db.get_conn()
        cur = conn.execute("""
            SELECT * FROM app_events
            WHERE user_id = ? AND (repo_name = ? OR repo_name = '')
              AND (kind LIKE '%fail%' OR kind LIKE '%error%' OR kind LIKE '%warning%')
            ORDER BY created_at DESC LIMIT 20
        """, (user_id, rname))
        error_events = [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        log.debug("Failed to query error events: %s", exc)

    # 3. Log files inside repository (*.log)
    disk_logs: List[Dict[str, Any]] = []
    if os.path.isdir(norm_path):
        try:
            log_patterns = [
                os.path.join(norm_path, "*.log"),
                os.path.join(norm_path, "logs", "*.log"),
                os.path.join(norm_path, "log", "*.log"),
                os.path.join(norm_path, "npm-debug.log*"),
                os.path.join(norm_path, "yarn-error.log*"),
            ]
            found_files: List[str] = []
            for pat in log_patterns:
                for f in glob.glob(pat):
                    if os.path.isfile(f) and f not in found_files:
                        found_files.append(f)

            for f_path in found_files[:10]:
                rel_name = os.path.relpath(f_path, norm_path)
                try:
                    with open(f_path, "r", encoding="utf-8", errors="ignore") as f_obj:
                        lines = [l.strip() for l in f_obj.readlines() if l.strip()]
                    # Extract last 15 error or warning lines
                    error_lines = [l for l in lines if re.search(r"\b(error|fail|exception|fatal|traceback|warn)\b", l, re.IGNORECASE)]
                    tail_lines = error_lines[-10:] if error_lines else lines[-6:]
                    disk_logs.append({
                        "file": rel_name,
                        "total_lines": len(lines),
                        "snippet": "\n".join(tail_lines),
                        "has_errors": bool(error_lines),
                    })
                except Exception:
                    pass
        except Exception as exc:
            log.debug("Log scan error: %s", exc)

    # 4. Code issues and bugs detected in active workspace
    code_issues: List[Dict[str, Any]] = []
    if is_git and uncommitted:
        try:
            inspect_targets = [p for _, p in uncommitted[:30]]
            issues_map = file_inspector.inspect_files(norm_path, inspect_targets)
            for f_rel, iss_list in issues_map.items():
                for iss in iss_list:
                    code_issues.append({
                        "file": f_rel,
                        "line": iss.get("line", 1),
                        "severity": iss.get("severity", "warning"),
                        "title": iss.get("title", "Issue"),
                        "message": iss.get("message", ""),
                        "fix": iss.get("fix", ""),
                    })
        except Exception as exc:
            log.debug("Code inspection error: %s", exc)

    return {
        "repo_name": rname,
        "repo_path": norm_path,
        "is_git": is_git,
        "branch": branch,
        "commits_count": commits_count,
        "bound_account": bound_account,
        "origin_url": origin_url,
        "uncommitted_count": uncommitted_count,
        "failed_commits": db_failed_commits,
        "error_events": error_events,
        "disk_logs": disk_logs,
        "code_issues": code_issues,
        "total_bug_count": len(db_failed_commits) + len(error_events) + len(code_issues) + sum(1 for d in disk_logs if d.get("has_errors")),
    }


def generate_repo_recommendations(repo_path: str, cfg: Optional[dict] = None) -> Dict[str, Any]:
    """
    Scrape repository purpose, tech stack, and structure to generate AI-powered recommendations:
    - Test cases (unit & integration tests to write)
    - Feature enhancements
    - Code quality & bug prevention
    """
    norm_path = os.path.normpath(repo_path)
    if norm_path in RECOMMENDATIONS_CACHE:
        return RECOMMENDATIONS_CACHE[norm_path]

    if cfg is None:
        cfg = load_config()

    rname = commit_engine.repo_name(norm_path)
    stack_info = _scrape_repo_stack(norm_path)
    recent_commits = []
    if os.path.isdir(norm_path) and commit_engine.is_git_repo(norm_path):
        try:
            hist = commit_engine.get_repo_commit_history(norm_path, limit=6)
            recent_commits = [c.get("subject", "") for c in hist]
        except Exception:
            pass

    # Try AI provider call
    ai_result = _call_ai_for_recommendations(cfg, rname, stack_info, recent_commits)
    if not ai_result or not ai_result.get("test_cases"):
        ai_result = _heuristic_recommendations(rname, stack_info)

    RECOMMENDATIONS_CACHE[norm_path] = ai_result
    return ai_result


def invalidate_repo_recommendations(repo_path: str) -> None:
    """Clear cached recommendations to allow fresh generation."""
    norm_path = os.path.normpath(repo_path)
    RECOMMENDATIONS_CACHE.pop(norm_path, None)


def _scrape_repo_stack(repo_path: str) -> Dict[str, Any]:
    """Inspect repository files to deduce project type, frameworks, and architecture."""
    technologies: List[str] = []
    key_files: List[str] = []
    readme_excerpt: str = ""

    if not os.path.isdir(repo_path):
        return {"technologies": ["General Project"], "key_files": [], "readme": ""}

    # Check README
    for r_name in ["README.md", "readme.md", "README.txt", "README"]:
        r_file = os.path.join(repo_path, r_name)
        if os.path.isfile(r_file):
            try:
                with open(r_file, "r", encoding="utf-8", errors="ignore") as f:
                    readme_excerpt = f.read(1200).strip()
                break
            except Exception:
                pass

    # Check project indicator files
    indicators = {
        "Python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
        "Node.js / TypeScript": ["package.json", "tsconfig.json"],
        "Go": ["go.mod", "go.sum"],
        "Rust": ["Cargo.toml"],
        "Java / Kotlin": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "Docker": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml"],
        "C / C++": ["CMakeLists.txt", "Makefile"],
        "HTML / Web": ["index.html"],
    }

    for tech, files in indicators.items():
        if any(os.path.exists(os.path.join(repo_path, f)) for f in files):
            technologies.append(tech)

    # Walk top 30 code files
    try:
        count = 0
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".next", ".gemini"}]
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), repo_path)
                _, ext = os.path.splitext(f)
                if ext.lower() in {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java", ".cpp", ".c", ".h", ".cs", ".sql", ".sh"}:
                    key_files.append(rel)
                    count += 1
                    if count >= 25:
                        break
            if count >= 25:
                break
    except Exception:
        pass

    if not technologies:
        technologies.append("Software Project")

    return {
        "technologies": technologies,
        "key_files": key_files,
        "readme": readme_excerpt,
    }


def _call_ai_for_recommendations(
    cfg: dict,
    repo_name: str,
    stack_info: Dict[str, Any],
    recent_commits: List[str],
) -> Optional[Dict[str, Any]]:
    """Query connected AI provider (OpenAI, Claude, Gemini, Local) for repository recommendations."""
    provider = ai_messages.get_active_provider(cfg)
    api_key = ai_messages.get_provider_key(cfg, provider)
    model = ai_messages.resolve_active_model(cfg) or ""

    if provider in ("openai", "claude", "gemini") and not api_key:
        return None

    system_prompt = (
        "You are an expert Principal Software Engineer and QA Architect. "
        "Analyze the repository metadata and return pure, valid JSON with concrete, actionable recommendations: "
        "test cases to implement, high-impact features to build, and bug prevention strategies."
    )

    user_prompt = f"""Repository: {repo_name}
Technologies: {', '.join(stack_info.get('technologies', []))}
Sample Files: {', '.join(stack_info.get('key_files', [])[:15])}
Recent Commits: {', '.join(recent_commits[:5]) if recent_commits else 'Initial development'}
README Summary: {stack_info.get('readme', '')[:600]}

Generate recommendations in this exact JSON schema:
{{
  "project_summary": "Brief 1-2 sentence understanding of what this project does and its core architecture.",
  "test_cases": [
    {{
      "title": "Short descriptive test case name",
      "target": "Target file or component (e.g. auth/login.py)",
      "scenario": "Scenario to test (e.g. Expired session token rejection)",
      "priority": "High" | "Medium",
      "description": "What to assert and why this edge case matters."
    }}
  ],
  "features": [
    {{
      "title": "High-impact feature title",
      "category": "Architecture" | "User Experience" | "Reliability" | "Integration",
      "description": "Clear explanation of what to build and its business or technical value."
    }}
  ],
  "bug_prevention": [
    {{
      "title": "Proactive hardening guideline",
      "description": "Specific code pitfall or vulnerability to avoid in this tech stack."
    }}
  ]
}}
Ensure exactly 4 test cases, 4 features, and 3 bug prevention guidelines. Reply ONLY with valid JSON."""

    try:
        raw_text = ""
        if provider == "openai":
            raw_text = ai_messages._call_openai(cfg, model, system_prompt, user_prompt, max_tokens=1500, timeout=14)
        elif provider == "claude":
            raw_text = ai_messages._call_claude(cfg, model, system_prompt, user_prompt, max_tokens=1500, timeout=14)
        elif provider == "gemini":
            raw_text = ai_messages._call_gemini(cfg, model, system_prompt, user_prompt, max_tokens=1500, timeout=14)
        elif provider in ("bionic", "ollama"):
            raw_text = ai_messages._call_local(cfg, model, system_prompt, user_prompt, max_tokens=1500, timeout=14)

        if raw_text:
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "test_cases" in parsed:
                return parsed
    except Exception as exc:
        log.debug("AI recommendations generation failed: %s", exc)

    return None


def _heuristic_recommendations(repo_name: str, stack_info: Dict[str, Any]) -> Dict[str, Any]:
    """Smart heuristic fallback recommendations when AI is offline or keyless."""
    techs = stack_info.get("technologies", [])
    files = stack_info.get("key_files", [])
    t_str = " / ".join(techs)

    first_file = files[0] if files else "core logic"
    second_file = files[1] if len(files) > 1 else first_file

    test_cases = [
        {
            "title": f"Edge Case Input Validation for {os.path.basename(first_file)}",
            "target": first_file,
            "scenario": "Null, empty string, and boundary value inputs",
            "priority": "High",
            "description": f"Verify {os.path.basename(first_file)} gracefully rejects malformed or unexpected parameters without uncaught exceptions or resource leaks.",
        },
        {
            "title": "Concurrent Execution & Thread-Safety Verification",
            "target": second_file,
            "scenario": "Simultaneous read/write operations from multiple threads or workers",
            "priority": "High",
            "description": "Ensure shared state, database sessions, and cache caches are properly guarded with locks or idempotency tokens to prevent race conditions.",
        },
        {
            "title": "Network Timeout & Offline Recovery Test",
            "target": "external integrations / APIs",
            "scenario": "Remote server connection drop or timeout during API payload delivery",
            "priority": "Medium",
            "description": "Assert retry backoff and fallback behaviors when external network services or database connections drop unexpectedly.",
        },
        {
            "title": "End-to-End Regression Test Suite",
            "target": "full workflow",
            "scenario": "Complete user transaction from initialization through persistence and reporting",
            "priority": "Medium",
            "description": "Validate that recent code modifications have not broken backward compatibility with existing schemas or caller contracts.",
        },
    ]

    features = [
        {
            "title": "Automated Health & Telemetry Dashboard",
            "category": "Reliability",
            "description": f"Add background monitoring metrics, error counters, and automated self-healing triggers to keep {repo_name} performant.",
        },
        {
            "title": "Structured Async Background Job Queue",
            "category": "Architecture",
            "description": "Offload long-running operations and disk/network I/O to a dedicated worker pool so user-facing operations remain sub-millisecond.",
        },
        {
            "title": "Audit Logging & Rollback Checkpoint System",
            "category": "Integration",
            "description": "Maintain immutable event audit records with one-click snapshot reversion to safeguard state against accidental misconfigurations.",
        },
        {
            "title": "Intelligent Caching with Invalidation Hooks",
            "category": "User Experience",
            "description": "Implement TTL-based in-memory caching for frequently computed summaries and query results to slash CPU cycles and latency.",
        },
    ]

    bug_prevention = [
        {
            "title": "Strict Schema Validation on External Inputs",
            "description": f"Guard all JSON payloads and file inputs in {t_str} with explicit type and range checks before executing business logic.",
        },
        {
            "title": "Enforce Deterministic Error Boundaries",
            "description": "Wrap IO-intensive and network tasks in scoped try/catch blocks with logged error diagnostics instead of raw unhandled crashes.",
        },
        {
            "title": "Clean Resource Teardown & Connection Pooling",
            "description": "Always release file descriptors, database connections, and subprocess handles using context managers (`with` / `try-finally`).",
        },
    ]

    return {
        "project_summary": f"{repo_name} is a {t_str} project with {len(files)} discovered source components ready for automated testing and expansion.",
        "test_cases": test_cases,
        "features": features,
        "bug_prevention": bug_prevention,
    }
