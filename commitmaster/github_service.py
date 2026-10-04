"""
CommitMaster — GitHub Service.
Handles GitHub API interaction, Personal Access Token (PAT) verification,
user metadata retrieval, and token masking.
"""
from typing import Dict, Any, Tuple, Optional
import requests
from commitmaster.logger import get

log = get("github_service")


def mask_token(token: str) -> str:
    """Mask personal access token for safe UI display (e.g. ghp_••••••••1234)."""
    if not token:
        return ""
    token = token.strip()
    if len(token) <= 8:
        return "••••••••"
    prefix = token[:4] if token.startswith(("ghp_", "github_pat_")) else token[:2]
    suffix = token[-4:]
    return f"{prefix}••••••••{suffix}"


def verify_github_token(token: str) -> Tuple[bool, Dict[str, Any], str]:
    """
    Verify GitHub Personal Access Token (PAT) via GitHub REST API.
    Returns (success: bool, user_info: dict, message: str).
    """
    token = token.strip()
    if not token:
        return False, {}, "Token cannot be empty."

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CommitMaster-Desktop-App",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        resp = requests.get("https://api.github.com/user", headers=headers, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            username = data.get("login", "")
            name = data.get("name", "") or username
            email = data.get("email", "") or ""
            avatar_url = data.get("avatar_url", "") or ""
            scopes = resp.headers.get("X-OAuth-Scopes", "")

            # If public email is empty, try to fetch primary email from /user/emails
            if not email and "user" in scopes or "user:email" in scopes:
                try:
                    email_resp = requests.get("https://api.github.com/user/emails", headers=headers, timeout=6)
                    if email_resp.status_code == 200:
                        emails_data = email_resp.json()
                        if isinstance(emails_data, list):
                            for em in emails_data:
                                if em.get("primary"):
                                    email = em.get("email", "")
                                    break
                            if not email and emails_data:
                                email = emails_data[0].get("email", "")
                except Exception:
                    pass

            if not email:
                email = f"{username}@users.noreply.github.com"

            info = {
                "username": username,
                "name": name,
                "email": email,
                "avatar_url": avatar_url,
                "scopes": scopes,
            }
            log.info("GitHub PAT verified for @%s", username)
            return True, info, f"Verified successfully as @{username}!"

        elif resp.status_code == 401:
            return False, {}, "Invalid token: Authentication failed (401 Unauthorized)."
        elif resp.status_code == 403:
            return False, {}, "Access forbidden (403): Token may lack required 'repo' scopes or rate limit reached."
        else:
            return False, {}, f"GitHub API error (status {resp.status_code}): {resp.text[:100]}"

    except requests.exceptions.Timeout:
        return False, {}, "Connection timed out while reaching GitHub API."
    except requests.exceptions.ConnectionError:
        return False, {}, "Network error: Unable to connect to https://api.github.com."
    except Exception as exc:
        log.exception("Unexpected error verifying GitHub token: %s", exc)
        return False, {}, f"Verification error: {str(exc)}"


def get_github_web_auth_url(description: str = "CommitMaster Desktop") -> str:
    """
    Generate official GitHub web authorization URL for creating a personal access token
    with all required scopes for CommitMaster pre-selected.
    """
    import urllib.parse
    scopes = ["repo", "read:org", "user:email", "workflow"]
    scopes_str = ",".join(scopes)
    desc_encoded = urllib.parse.quote_plus(description)
    return f"https://github.com/settings/tokens/new?description={desc_encoded}&scopes={scopes_str}"


def open_github_web_auth(description: str = "CommitMaster Desktop") -> bool:
    """Open default browser to GitHub web sign-in / token creation page."""
    import webbrowser
    url = get_github_web_auth_url(description)
    try:
        log.info("Opening GitHub Web auth in browser: %s", url)
        webbrowser.open(url, new=2)
        return True
    except Exception as exc:
        log.error("Could not open browser for GitHub auth: %s", exc)
        return False


def fetch_user_repositories(token: str, max_repos: int = 200) -> Tuple[bool, list, str]:
    """
    Fetch all GitHub repositories the authenticated user has access to
    (owned, collaborated, org repos).
    Returns (success: bool, repos: List[dict], message: str).
    """
    token = token.strip()
    if not token:
        return False, [], "Token cannot be empty."

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CommitMaster-Desktop-App",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    all_repos = []
    page = 1
    per_page = 100

    try:
        while len(all_repos) < max_repos:
            url = f"https://api.github.com/user/repos?per_page={per_page}&page={page}&affiliation=owner,collaborator,organization_member&sort=updated"
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                if not data or not isinstance(data, list):
                    break
                for r in data:
                    all_repos.append({
                        "id": r.get("id"),
                        "name": r.get("name", ""),
                        "full_name": r.get("full_name", ""),
                        "private": bool(r.get("private")),
                        "html_url": r.get("html_url", ""),
                        "clone_url": r.get("clone_url", ""),
                        "ssh_url": r.get("ssh_url", ""),
                        "default_branch": r.get("default_branch", "main"),
                        "description": r.get("description") or "",
                        "language": r.get("language") or "Code",
                        "updated_at": r.get("updated_at", ""),
                        "stargazers_count": r.get("stargazers_count", 0),
                        "forks_count": r.get("forks_count", 0),
                        "owner_login": r.get("owner", {}).get("login", ""),
                        "owner_avatar": r.get("owner", {}).get("avatar_url", ""),
                    })
                if len(data) < per_page:
                    break
                page += 1
            elif resp.status_code == 401:
                return False, [], "Authentication failed (401). Token may be expired or invalid."
            elif resp.status_code == 403:
                return False, [], "Access forbidden (403). Check token scopes ('repo' required)."
            else:
                return False, [], f"GitHub API error ({resp.status_code}): {resp.text[:100]}"

        log.info("Fetched %d repositories from GitHub.", len(all_repos))
        return True, all_repos, f"Successfully fetched {len(all_repos)} repositories."

    except requests.exceptions.Timeout:
        return False, [], "Connection timed out while fetching repositories."
    except requests.exceptions.ConnectionError:
        return False, [], "Network error: Unable to reach GitHub API."
    except Exception as exc:
        log.exception("Error fetching repositories: %s", exc)
        return False, [], f"Error fetching repos: {str(exc)}"
