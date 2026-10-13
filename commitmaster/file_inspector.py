"""
CommitMaster — Pre-Commit File Inspector.

Performs sanity checks, syntax validation, secret-leak detection, insecure-code
pattern detection and conflict-marker scanning on files before they are committed.

Every issue is returned as a dict with enough information for the UI to show the
user *what* is wrong, *where* it is (with the offending code), *why* it matters
and *how* to fix it:

    {
        "file":        "path/in/repo.py",
        "severity":    "error" | "security" | "warning",
        "type":        "secret_leak" | "insecure_code" | ...,
        "title":       "Hardcoded API key",
        "line":        12,
        "col":         8,
        "message":     one line description (kept for backwards compatibility),
        "snippet":     the offending line (secrets masked),
        "context":     [{"line": 10, "text": "...", "hit": False}, ...],
        "explanation": why this is a problem,
        "fix":         how to resolve it,
        "reference":   e.g. "CWE-798",
    }
"""
import ast
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from commitmaster.logger import get

log = get("file_inspector")

CONTEXT_RADIUS = 2          # lines of code shown above / below an issue
MAX_ISSUES_PER_FILE = 25

# Threat and Issue Categories
CATEGORY_VIRUS = "VIRUS / MALWARE THREAT"
CATEGORY_EXPLOIT = "HACKER EXPLOIT VECTOR"
CATEGORY_BREACH = "SECURITY BREACH"
CATEGORY_QUALITY = "CODE QUALITY & SYNTAX"

DEFAULT_HARDENING_BREACH = (
    "• Immediately revoke and rotate any leaked credential across all production and development environments.\n"
    "• Use centralized secrets management (e.g. AWS Secrets Manager, Azure Key Vault, HashiCorp Vault) or .env files excluded via .gitignore.\n"
    "• Enforce pre-commit automated secret scanning git hooks and branch protection rules."
)

DEFAULT_HARDENING_VIRUS = (
    "• Enforce application execution whitelisting (AppLocker/WDAC) and anti-malware runtime inspection.\n"
    "• Pin all dependency digests in lockfiles and audit supply chain packages for malicious or obfuscated scripts.\n"
    "• Restrict CI/CD runner egress access and disallow unsigned script execution."
)

DEFAULT_HARDENING_EXPLOIT = (
    "• Apply defensive programming: validate all inputs against strict schemas and allow-lists.\n"
    "• Follow the Principle of Least Privilege for database users, OS processes, and API tokens.\n"
    "• Integrate static application security testing (SAST) and dynamic testing (DAST) into CI pipelines."
)

DEFAULT_HARDENING_QUALITY = (
    "• Configure automated linting and code formatting (e.g. black, flake8, ruff, prettier) in pre-commit git hooks.\n"
    "• Implement automated unit test gates on all pull requests before merging into main branches."
)

# ── Secret detection ──────────────────────────────────────────────────────────
# (type, regex, label, fix hint).  A named group "secret" (or group 1) marks the
# part of the line that will be masked in the snippet.
SECRET_PATTERNS = [
    ("github_pat", r"\b(?P<secret>ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})\b",
     "GitHub Personal Access Token"),
    ("private_key", r"(?P<secret>-----BEGIN (?:RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----)",
     "Private cryptographic key"),
    ("aws_access_key", r"\b(?P<secret>AKIA[0-9A-Z]{16})\b", "AWS Access Key ID"),
    ("openai_key", r"\b(?P<secret>sk-[a-zA-Z0-9]{20,})\b", "OpenAI API Key"),
    ("stripe_key", r"\b(?P<secret>sk_live_[0-9a-zA-Z]{16,})\b", "Stripe live secret key"),
    ("google_api_key", r"\b(?P<secret>AIza[0-9A-Za-z_\-]{35})\b", "Google API key"),
    ("slack_token", r"\b(?P<secret>xox[baprs]-[0-9A-Za-z\-]{10,})\b", "Slack token"),
    ("db_uri_creds",
     r"""(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|mssql|oracle)://[^/\s:@'"]+:(?P<secret>[^/\s:@'"]{4,})@[^/\s'"]+""",
     "Database Connection URI with Embedded Plaintext Password"),
    ("url_credentials", r"[a-zA-Z][a-zA-Z0-9+.\-]*://[^/\s:@'\"]+:(?P<secret>[^/\s:@'\"]{4,})@",
     "Password embedded in a URL"),
    ("cloud_master_secret",
     r"""(?i)\b(?:aws_secret_access_key|aws_session_token|azure[_-]?client[_-]?secret)\s*[:=]\s*['"](?P<secret>[A-Za-z0-9/+=~_\-.]{30,})['"]""",
     "Cloud Master Secret / Service Principal Key"),
    ("jwt_secret_key",
     r"""(?i)\b(?:JWT_SECRET|SECRET_KEY)\s*[:=]\s*['"](?P<secret>[^'"\s]{10,})['"]""",
     "Hardcoded JWT / Session Secret Key"),
    ("generic_secret",
     r"""(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret)\s*[:=]\s*['"](?P<secret>[a-zA-Z0-9_\-\.]{20,})['"]""",
     "Hardcoded API key / secret"),
]

_SECRET_EXPLANATION = (
    "A credential written into source code is stored forever in Git history and is visible to "
    "everyone with access to the repository (and to the public if the repo is or becomes public). "
    "Bots scan GitHub continuously and abuse leaked keys within minutes."
)
_SECRET_FIX = (
    "1. Revoke / rotate this credential now - treat it as compromised.\n"
    "2. Load it from an environment variable or a git-ignored config file instead, e.g.\n"
    "       value = os.environ[\"MY_API_KEY\"]\n"
    "3. Commit a placeholder in an example file (e.g. config.example.json) and add the real file to .gitignore."
)

# ── Insecure code patterns ────────────────────────────────────────────────────
# Each rule: id, regex, exts (None = any text file), title, explanation, fix,
# reference, severity
_PY = (".py", ".pyw")
_JS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".html", ".htm")

CODE_RULES: List[Dict[str, Any]] = [
    # ── Virus & Malware Threat Vectors ───────────────────────────────────────────
    {
        "id": "powershell_encoded_payload", "exts": None,
        "category": CATEGORY_VIRUS, "threat_class": "virus_threat",
        "regex": r"""(?i)\bpowershell(?:\.exe)?\s+[^;\n|]*-(?:enc|encodedcommand)\s+[A-Za-z0-9+/=]{16,}""",
        "title": "Obfuscated / Encoded PowerShell Payload (Fileless Malware Vector)",
        "explanation": "Base64 encoded command arguments in PowerShell are heavily utilized by malware droppers, loaders, "
                       "and trojans to evade endpoint antivirus signatures and script logging. The hidden payload executes arbitrary "
                       "commands directly in memory.",
        "fix": "1. Decode and inspect the Base64 payload before executing.\n"
               "2. Convert encoded commands into clear, auditable scripts checked into version control.\n"
               "3. Never execute hidden or obfuscated scripts in development or automated build pipelines.",
        "hardening": "• Enable PowerShell Constrained Language Mode and Script Block Logging (Event ID 4104).\n"
                     "• Require cryptographic code signing (AllSigned execution policy) on all production PowerShell scripts.\n"
                     "• Configure Windows Defender Application Control (WDAC) or AppLocker to block unauthorized script execution.",
        "reference": "MITRE ATT&CK T1059.001",
        "severity": "security",
    },
    {
        "id": "download_cradle", "exts": None,
        "category": CATEGORY_VIRUS, "threat_class": "virus_threat",
        "regex": r"""(?i)(?:curl|wget)\s+[^\n|;&]+(?:\s*\|\s*(?:bash|sh|zsh|powershell|cmd))|(?:Invoke-Expression|IEX)\s*\(?(?:New-Object\s+Net\.WebClient\)\.DownloadString|Invoke-WebRequest|iwr)""",
        "title": "Remote Download-and-Execute Cradle (Trojan / Dropper Pattern)",
        "explanation": "Piping untrusted remote network downloads directly into an execution shell (e.g. curl ... | bash, "
                       "or IEX (DownloadString)) allows an attacker who compromises the remote server, CDN, or DNS to execute "
                       "arbitrary root/admin code immediately on this machine.",
        "fix": "1. Separate download and execution into distinct, inspected steps.\n"
               "2. Verify the SHA-256 hash or digital signature of downloaded binaries/scripts before execution.\n"
               "3. Use explicit package managers (pip, npm, cargo) with lockfiles rather than raw web cradles.",
        "hardening": "• Pin dependency checksums and maintain an internal, vetted mirror/registry.\n"
                     "• Apply strict egress firewall filtering from continuous integration runners and build environments.\n"
                     "• Employ integrity monitoring tools to alert on unexpected process execution spawned from shells.",
        "reference": "MITRE ATT&CK T1105 / T1059",
        "severity": "security",
    },
    {
        "id": "reverse_shell", "exts": None,
        "category": CATEGORY_VIRUS, "threat_class": "virus_threat",
        "regex": r"""(?i)(?:/bin/(?:ba)?sh\s+-i\s*>&?\s*/dev/tcp/|\bsocket\.socket\([^)]*\).*os\.dup2\s*\(|\bsubprocess\.Popen\(.*(?:/bin/sh|/bin/bash|cmd\.exe|powershell\.exe).*stdin\s*=\s*subprocess\.PIPE.*stdout\s*=\s*subprocess\.PIPE)""",
        "title": "Reverse Shell / Unauthorized Remote Access Backdoor",
        "explanation": "This pattern establishes an outbound socket connection and binds standard system input/output streams "
                       "to an interactive shell. This technique is used by malware and adversaries to bypass inbound NAT/firewalls "
                       "and provide remote root/command-line shell access to external command-and-control (C2) servers.",
        "fix": "1. Immediately remove reverse shell invocations from source files.\n"
               "2. If remote management is required, use audited protocols such as SSH keys, mutual TLS, or VPN tunnels.\n"
               "3. Verify repository commit logs to determine if this file was committed by an unauthorized user or compromised dependency.",
        "hardening": "• Implement egress firewall controls to block arbitrary outbound TCP/UDP connections from internal servers.\n"
                     "• Deploy network intrusion detection (Zeek, Suricata) and EDR systems to flag outbound socket shell redirection.\n"
                     "• Require multi-factor authentication (MFA) and hardware keys for repository commit signing.",
        "reference": "MITRE ATT&CK T1059 / T1071",
        "severity": "security",
    },
    {
        "id": "ransomware_shadow_wiper", "exts": None,
        "category": CATEGORY_VIRUS, "threat_class": "virus_threat",
        "regex": r"""(?i)\bvssadmin(?:\.exe)?\s+delete\s+shadows|\bwbadmin(?:\.exe)?\s+delete\s+(?:catalog|systemstatebackup)|\bbcdedit(?:\.exe)?\s+/set\s+.*(?:recoveryenabled\s+no|bootstatuspolicy\s+ignoreallfailures)""",
        "title": "Ransomware Recovery Suppression (Volume Shadow / Backup Deletion)",
        "explanation": "Commands that delete Volume Shadow Copies (vssadmin delete shadows) or wipe system backup states are "
                       "standard ransomware anti-recovery instructions (observed in LockBit, BlackCat, WannaCry). They prevent victims "
                       "from rolling back encrypted files without paying extortion.",
        "fix": "1. Delete this instruction immediately.\n"
               "2. Ensure no build tasks or installer scripts tamper with Windows recovery or backup volumes.\n"
               "3. Conduct a full malware scan of the development machine.",
        "hardening": "• Maintain immutable, air-gapped backups (e.g. AWS S3 with Object Lock Compliance mode or offline external drives).\n"
                     "• Restrict volume shadow copy management to dedicated, elevated accounts with audit logging enabled.\n"
                     "• Configure Windows Security Event 4688 process creation monitoring to immediately terminate unauthorized vssadmin calls.",
        "reference": "MITRE ATT&CK T1490",
        "severity": "security",
    },
    {
        "id": "cryptominer_artifact", "exts": None,
        "category": CATEGORY_VIRUS, "threat_class": "virus_threat",
        "regex": r"""(?i)\b(?:stratum\+(?:tcp|ssl)://|\bxmrig(?:\.exe)?\b|minergate|cryptonight|coinhive)""",
        "title": "Cryptocurrency Mining Signature / Resource Hijacking Threat",
        "explanation": "Detected stratum network protocols or miner binary references. Threat actors inject cryptominers "
                       "into dependencies and repositories to covertly hijack CPU/GPU compute power, driving up hardware wear and "
                       "generating massive cloud utility bills.",
        "fix": "1. Remove all references to cryptocurrency mining endpoints and binaries.\n"
               "2. Review third-party dependencies for typosquatted or malicious packages (e.g. rogue npm/pip packages).\n"
               "3. Check server process tables for rogue background CPU-heavy workers.",
        "hardening": "• Implement cloud billing anomaly alerts and container CPU throttling thresholds.\n"
                     "• Block known cryptocurrency mining pools at your corporate DNS resolver.\n"
                     "• Enforce dependency lockfiles with signed repository attestations.",
        "reference": "MITRE ATT&CK T1496",
        "severity": "security",
    },
    {
        "id": "memory_injection_vector", "exts": _PY,
        "category": CATEGORY_VIRUS, "threat_class": "virus_threat",
        "regex": r"""(?i)\bVirtualAlloc(?:Ex)?\s*\([^)]*(?:0x40|PAGE_EXECUTE_READWRITE)|\bWriteProcessMemory\s*\(|\bCreateRemoteThread\s*\(""",
        "title": "Process Memory Injection / Shellcode Execution Vector",
        "explanation": "Allocating RWX (Read-Write-Execute) memory and calling CreateRemoteThread or WriteProcessMemory is a process "
                       "hollowing and shellcode injection technique used by malware to inject unauthorized binaries into trusted processes.",
        "fix": "1. Avoid dynamic memory allocation with executable permissions.\n"
               "2. Use standard language IPC (named pipes, queues, RPC) instead of manipulating other process memory spaces.",
        "hardening": "• Ensure Data Execution Prevention (DEP) and Control Flow Guard (CFG) are enabled compiler flags.\n"
                     "• Strip SeDebugPrivilege from non-administrative processes and service accounts.",
        "reference": "MITRE ATT&CK T1055",
        "severity": "security",
    },

    # ── Hacker Exploit Vectors ───────────────────────────────────────────────────
    {
        "id": "ssrf_cloud_metadata", "exts": None,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"""(?i)(?:169\.254\.169\.254|metadata\.google\.internal|100\.100\.100\.200)""",
        "title": "Cloud Instance Metadata SSRF Target (IAM Credential Theft)",
        "explanation": "The IP 169.254.169.254 is the cloud link-local Instance Metadata Service (IMDS). If user-controlled input "
                       "can reach this endpoint via an HTTP fetch or proxy, attackers can dump the instance's IAM role keys, temporary "
                       "security tokens, and take over your cloud account.",
        "fix": "1. Never allow outbound HTTP requests to link-local IP addresses (169.254.0.0/16).\n"
               "2. Enforce IMDSv2 (session token requirement) on AWS EC2.\n"
               "3. Filter and resolve target hostnames through a strict domain allow-list.",
        "hardening": "• Enforce IMDSv2 token hop limit = 1 so containerized applications cannot reach host metadata.\n"
                     "• Restrict IAM roles attached to instances with the Principle of Least Privilege.\n"
                     "• Block 169.254.169.254 via host firewall (iptables/Windows Filtering Platform) for unprivileged service accounts.",
        "reference": "CWE-918 / OWASP A10",
        "severity": "security",
    },
    {
        "id": "path_traversal", "exts": _PY,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"""(?i)(?:open|send_file|FileResponse)\s*\(\s*(?:os\.path\.join\([^)]*(?:filename|file_name|path|user_path)[^)]*\)|f["'][^"']*(?:\{filename\}|\{path\}|\{file\}))""",
        "title": "Path Traversal / Arbitrary File Access Risk",
        "explanation": "Constructing file system paths directly from variable names like 'filename' or 'path' without validation "
                       "allows attackers to submit traversal sequences (such as '../../etc/passwd' or '..\\..\\Windows\\System32') to "
                       "read, overwrite, or delete sensitive files outside the application directory.",
        "fix": "Resolve the absolute canonical path and verify it remains strictly within the intended base directory:\n"
               "       safe_base = os.path.abspath(BASE_DIR)\n"
               "       target = os.path.abspath(os.path.join(safe_base, os.path.basename(filename)))\n"
               "       if not target.startswith(safe_base + os.sep):\n"
               "           raise ValueError(\"Unauthorized path traversal attempt\")",
        "hardening": "• Reference files by randomly generated database UUIDs instead of client-supplied names.\n"
                     "• Run applications under dedicated service accounts with restrictive filesystem permissions (read-only where possible).\n"
                     "• Use chroot, apparmor profiles, or unprivileged container isolation.",
        "reference": "CWE-22 / OWASP A01",
        "severity": "security",
    },
    {
        "id": "xxe_injection", "exts": _PY,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"""(?i)\b(?:etree\.fromstring|etree\.parse|xml\.sax\.make_parser)\s*\(.*(?:resolve_entities\s*=\s*True|load_dtd\s*=\s*True)""",
        "title": "XML External Entity (XXE) Injection Vulnerability",
        "explanation": "Parsing untrusted XML with external entities or DTD resolution enabled permits attackers to craft XML documents "
                       "containing external file references, resulting in disclosure of confidential server files or internal network port scanning.",
        "fix": "Disable DTD processing and external entity resolution:\n"
               "       parser = etree.XMLParser(resolve_entities=False, no_network=True, dtd_validation=False)\n"
               "       doc = etree.fromstring(xml_bytes, parser=parser)\n"
               "   Or use defusedxml: import defusedxml.ElementTree as ET",
        "hardening": "• Prefer JSON, YAML (with safe loaders), or Protocol Buffers for modern network payloads.\n"
                     "• Require the 'defusedxml' package for all Python XML parsing.",
        "reference": "CWE-611 / OWASP A05",
        "severity": "security",
    },
    {
        "id": "cors_wildcard_credential", "exts": None,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"""(?i)Access-Control-Allow-Origin['"]?\s*:\s*['"]?\*['"]?.*credentials|allow_origins\s*=\s*\[\s*["']\*["']\s*\].*allow_credentials\s*=\s*True""",
        "title": "CORS Wildcard with Credentials Vulnerability",
        "explanation": "Allowing wildcard origins (*) in conjunction with credentials allows malicious third-party websites to make "
                       "cross-origin authenticated requests and steal private user data from the logged-in session.",
        "fix": "Specify an explicit, hardcoded list of trusted domain origins. Never combine wildcard '*' with allow_credentials=True.",
        "hardening": "• Restrict CORS origins to precise production domain origins with HTTPS.\n"
                     "• Set SameSite=Lax or SameSite=Strict on all authentication and session cookies.",
        "reference": "CWE-942 / OWASP A05",
        "severity": "security",
    },
    {
        "id": "prototype_pollution", "exts": _JS,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"""(?i)\[["']__proto__["']\]|\.__proto__\b|Object\.assign\s*\(\s*\{\}\s*,\s*JSON\.parse""",
        "title": "JavaScript Prototype Pollution Vulnerability",
        "explanation": "Directly modifying __proto__ or merging untrusted JSON into existing objects allows attackers to overwrite "
                       "properties on Object.prototype, altering application behavior and frequently escalating to remote code execution in Node.js.",
        "fix": "Use Object.create(null) for dictionary lookups, or sanitize object keys before merging to strip '__proto__', 'constructor', and 'prototype'.",
        "hardening": "• Freeze Object.prototype at application startup: Object.freeze(Object.prototype).\n"
                     "• Validate incoming request payloads against strict Zod or JSON schemas.",
        "reference": "CWE-1321",
        "severity": "security",
    },
    {
        "id": "dynamic_code_exec", "exts": _PY,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"(?<![\w.])(?:eval|exec)\s*\(",
        "title": "Dynamic code execution (eval / exec)",
        "explanation": "eval/exec run arbitrary Python from a string. If any part of that string can be "
                       "influenced by a user, file or network response, an attacker can run their own code on this machine.",
        "fix": "Avoid executing strings. Use ast.literal_eval() for data, json.loads() for JSON, or a dispatch "
               "table (dict of allowed functions) instead of eval.",
        "hardening": "• Never evaluate dynamic strings from untrusted sources.\n"
                     "• Implement dispatch dictionaries mapping safe command tokens to handler functions.\n"
                     "• Enforce strict static analysis (flake8 / bandit / pylint) in pre-commit hooks.",
        "reference": "CWE-95",
        "severity": "security",
    },
    {
        "id": "shell_injection", "exts": _PY,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"\bsubprocess\.\w+\(.*shell\s*=\s*True",
        "title": "Command injection risk (shell=True)",
        "explanation": "With shell=True the command line is parsed by the shell. Unsanitised input such as "
                       "`; rm -rf /` or `& del` gets executed as an extra command.",
        "fix": "Pass the command as a list and drop shell=True:\n"
               "       subprocess.run([\"git\", \"status\", path], check=True)",
        "hardening": "• Always use subprocess argument lists (e.g. ['git', 'commit', '-m', msg]) without shell=True.\n"
                     "• Avoid shell wrappers; use native platform APIs or vetted libraries.\n"
                     "• Validate and sanitize input strings against strict alphanumeric whitelists.",
        "reference": "CWE-78",
        "severity": "security",
    },
    {
        "id": "os_system", "exts": _PY,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"\bos\.(?:system|popen)\s*\(",
        "title": "Command injection risk (os.system / os.popen)",
        "explanation": "os.system hands a string to the shell, so any untrusted text inside it can inject extra commands.",
        "fix": "Use subprocess.run([...list of args...], check=True) without a shell.",
        "hardening": "• Deprecate os.system in favor of subprocess.run() with argument lists.\n"
                     "• Isolate process execution environments with minimal permissions.",
        "reference": "CWE-78",
        "severity": "security",
    },
    {
        "id": "unsafe_deserialization", "exts": _PY,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"\b(?:pickle|cPickle|marshal|shelve)\.loads?\s*\(",
        "title": "Unsafe deserialization (pickle / marshal)",
        "explanation": "Loading a pickle can execute arbitrary code embedded in the data. Never unpickle data that "
                       "did not come from a fully trusted source.",
        "fix": "Use a data-only format such as JSON, or sign and verify the payload (hmac) before loading it.",
        "hardening": "• Standardize on secure serialization formats like JSON, MessagePack, or Protocol Buffers.\n"
                     "• Cryptographically sign objects with HMAC-SHA256 if serialization is mandatory and verify before unpacking.",
        "reference": "CWE-502",
        "severity": "security",
    },
    {
        "id": "unsafe_yaml", "exts": _PY,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"\byaml\.load\s*\((?!.*(?:Safe|safe))",
        "title": "Unsafe YAML loading",
        "explanation": "yaml.load with the default loader can construct arbitrary Python objects, which allows code execution.",
        "fix": "Use yaml.safe_load(...) or pass Loader=yaml.SafeLoader.",
        "hardening": "• Always use yaml.safe_load() across all configuration files.\n"
                     "• Audit dependencies that parse YAML documents.",
        "reference": "CWE-502",
        "severity": "security",
    },
    {
        "id": "sql_injection", "exts": _PY,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "skip_if": r"\?",
        "regex": r"""(?i)\.execute(?:many|script)?\s*\(\s*(?:f["']|["'][^"']*(?:select|insert|update|delete|drop|alter)[^"']*["']\s*(?:%|\+|\.format))""",
        "title": "SQL injection risk (query built from strings)",
        "explanation": "Building SQL with f-strings, % or + lets an attacker change the meaning of the query "
                       "(e.g. a name of `x'; DROP TABLE users;--`).",
        "fix": "Use parameter placeholders and pass values separately:\n"
               "       cur.execute(\"SELECT * FROM users WHERE name = ?\", (name,))\n"
               "   Table / column names cannot be parameters - validate them against a fixed allow-list.",
        "hardening": "• Use parameterized queries or Object Relational Mappers (ORM) like SQLAlchemy with automatic parameter binding.\n"
                     "• Never concatenate user input into SQL strings.\n"
                     "• Apply least-privilege database user permissions (e.g. read-only roles where updates aren't needed).",
        "reference": "CWE-89",
        "severity": "security",
    },
    {
        "id": "weak_hash", "exts": _PY,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"\bhashlib\.(?:md5|sha1)\s*\(",
        "title": "Weak hash algorithm (MD5 / SHA-1)",
        "explanation": "MD5 and SHA-1 are broken for security use - collisions can be forged and they are far too fast "
                       "for password hashing.",
        "fix": "Use hashlib.sha256 (or better) for integrity checks, and bcrypt / argon2 / scrypt for passwords. "
               "If this is only a non-security checksum, pass usedforsecurity=False to document it.",
        "hardening": "• Use Argon2id or bcrypt with appropriate work factors for user passwords.\n"
                     "• Use SHA-256 or SHA-512 for digital signatures and cryptographic hashing.",
        "reference": "CWE-327",
        "severity": "warning",
    },
    {
        "id": "tls_verify_off", "exts": _PY,
        "category": CATEGORY_BREACH, "threat_class": "security_breach",
        "regex": r"\bverify\s*=\s*False|_create_unverified_context",  # nosec
        "title": "TLS certificate verification disabled",
        "explanation": "Without certificate verification anyone on the network path can impersonate the server "
                       "(man-in-the-middle) and read or alter the traffic.",
        "fix": "Remove the verify override. If you use a private CA, point to it: requests.get(url, verify=\"/path/ca.pem\").",
        "hardening": "• Always enforce TLS certificate verification.\n"
                     "• Install private corporate root certificates into the system trust store rather than turning off TLS verification in code.\n"
                     "• Enable HTTP Strict Transport Security (HSTS) on servers.",
        "reference": "CWE-295",
        "severity": "security",
    },
    {
        "id": "debug_enabled", "exts": _PY,
        "category": CATEGORY_BREACH, "threat_class": "security_breach",
        "regex": r"\.run\s*\(.*debug\s*=\s*True|^\s*DEBUG\s*=\s*True\b",
        "title": "Debug mode enabled",
        "explanation": "Debug mode can expose an interactive console and stack traces with secrets to anyone who reaches the app.",
        "fix": "Read the flag from the environment (DEBUG = os.environ.get(\"DEBUG\") == \"1\") and keep it off in production.",
        "hardening": "• Ensure production configurations are loaded from immutable environment variables.\n"
                     "• Never expose interactive debug consoles (e.g. Werkzeug debugger) outside localhost.",
        "reference": "CWE-489",
        "severity": "warning",
    },
    {
        "id": "insecure_tempfile", "exts": _PY,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"\btempfile\.mktemp\s*\(",
        "title": "Insecure temporary file (mktemp)",
        "explanation": "mktemp only returns a name; another process can create that file first (race condition / symlink attack).",
        "fix": "Use tempfile.NamedTemporaryFile() or tempfile.mkstemp(), which create the file atomically.",
        "hardening": "• Use atomic temporary file creation APIs (tempfile.NamedTemporaryFile).\n"
                     "• Set permissions to 0600 on created temporary files.",
        "reference": "CWE-377",
        "severity": "warning",
    },
    {
        "id": "hardcoded_password", "exts": None,
        "category": CATEGORY_BREACH, "threat_class": "security_breach",
        "regex": r"""(?i)\b(?:password|passwd|pwd)\b\s*[:=]\s*['"](?P<secret>[^'"\s]{4,})['"]""",
        "title": "Hardcoded password",
        "explanation": "A password in the source is shared with everyone who can read the code and is kept in Git history.",
        "fix": "Read it from an environment variable / secret store, or prompt for it at runtime.",
        "hardening": "• Store passwords in environment variables or key vaults.\n"
                     "• Use secret-scanning tools (like CommitMaster Pre-Commit hooks and GitGuardian) in CI.",
        "reference": "CWE-798",
        "severity": "security",
        "mask": True,
    },
    {
        "id": "js_eval", "exts": _JS,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"(?<![\w.])eval\s*\(|new\s+Function\s*\(",
        "title": "Dynamic code execution in JavaScript",
        "explanation": "eval / new Function execute strings as code - a classic route for cross-site scripting.",
        "fix": "Parse data with JSON.parse and call functions directly instead of evaluating strings.",
        "hardening": "• Adopt a strict Content Security Policy (CSP) with 'unsafe-eval' forbidden.\n"
                     "• Use JSON.parse() and structured object lookups.",
        "reference": "CWE-95",
        "severity": "security",
    },
    {
        "id": "js_xss", "exts": _JS,
        "category": CATEGORY_EXPLOIT, "threat_class": "exploit_vector",
        "regex": r"\.innerHTML\s*=|document\.write\s*\(|dangerouslySetInnerHTML",
        "title": "Cross-site scripting (XSS) risk",
        "explanation": "Writing untrusted text as HTML lets an attacker inject <script> tags or event handlers into the page.",
        "fix": "Use textContent (or your framework's escaping) instead of innerHTML. If HTML is required, "
               "sanitise it first with a library such as DOMPurify.",
        "hardening": "• Use modern frameworks with built-in output escaping (React, Vue, Svelte).\n"
                     "• Always sanitize HTML with DOMPurify if user-generated rich text is allowed.\n"
                     "• Configure Content-Security-Policy headers in HTTP responses.",
        "reference": "CWE-79",
        "severity": "security",
    },
]

# Files that should basically never be committed
SENSITIVE_FILE_NAMES = (".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc")
SENSITIVE_FILE_EXTS = (".pem", ".key", ".pfx", ".p12", ".keystore", ".jks")
SENSITIVE_FILE_SAFE = (".example", ".sample", ".template", ".dist")

# Merge conflict markers
CONFLICT_PATTERNS = [
    ("conflict_head", r"^<{7}\s+", "Git merge conflict marker (HEAD)"),
    ("conflict_middle", r"^={7}$", "Git merge conflict marker (separator)"),
    ("conflict_tail", r"^>{7}\s+", "Git merge conflict marker (branch/remote)"),
]

# Precompiled regexes for maximum performance
_COMPILED_CONFLICTS = [(cid, re.compile(pat), desc) for cid, pat, desc in CONFLICT_PATTERNS]
_COMPILED_SECRETS = [(stype, re.compile(pat), desc) for stype, pat, desc in SECRET_PATTERNS]
_COMPILED_RULES = [
    {
        **rule,
        "_rx": re.compile(rule["regex"]),
        "_skip_rx": re.compile(rule["skip_if"]) if rule.get("skip_if") else None,
    }
    for rule in CODE_RULES
]

_FILE_INSPECT_CACHE: Dict[str, Tuple[float, int, List[Dict[str, Any]]]] = {}

# Extensions safe to inspect as text
TEXT_EXTENSIONS = {
    ".py", ".pyw", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".html", ".htm", ".css", ".scss",
    ".md", ".txt", ".rst", ".sh", ".bat", ".ps1", ".sql", ".xml",
    ".csv", ".env", ".env.local", ".env.development", ".env.production",
}

# Large file limit (10MB)
LARGE_FILE_BYTES = 10 * 1024 * 1024

# Dangerous binary file extensions that are usually accidentally committed
ACCIDENTAL_BINARY_EXTENSIONS = {".exe", ".dll", ".so", ".dylib", ".zip", ".tar", ".gz", ".7z", ".iso", ".bin"}

_PLACEHOLDER_HINTS = ("example", "dummy", "placeholder", "your_", "your-", "xxxx", "test", "changeme",
                      "<", "{", "$", "%s", "password", "secret", "****", "....", "none", "null",
                      "redact", "redacted", "token_redacted", "[token")


def is_binary_file(filepath: str) -> bool:
    """Detect if a file is likely binary by checking for null bytes in initial chunk."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        return False
    return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mask(value: str) -> str:
    """Keep the first 4 characters so the user can recognise the secret, hide the rest."""
    if len(value) <= 6:
        return "*" * len(value)
    return value[:4] + "*" * min(len(value) - 4, 12)


def _masked_line(line: str, match: Optional["re.Match"]) -> str:
    """Return the line with the secret portion masked."""
    if not match:
        return line
    try:
        start, end = match.span("secret")
    except IndexError:
        return line
    if start < 0:
        return line
    return line[:start] + _mask(line[start:end]) + line[end:]


def _context(lines: List[str], lineno: int, replace_line: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return the surrounding code of `lineno` (1-based) as [{line, text, hit}, ...]."""
    start = max(1, lineno - CONTEXT_RADIUS)
    end = min(len(lines), lineno + CONTEXT_RADIUS)
    ctx = []
    for n in range(start, end + 1):
        text = lines[n - 1].rstrip("\r\n")
        if n == lineno and replace_line is not None:
            text = replace_line
        elif n != lineno:
            # never leak a secret through the neighbouring lines
            text = _mask_known_secrets(text)
        ctx.append({"line": n, "text": text[:160], "hit": n == lineno})
    return ctx


def _mask_known_secrets(text: str) -> str:
    for _, pattern, _ in SECRET_PATTERNS:
        m = re.search(pattern, text)
        if m:
            text = _masked_line(text, m)
    return text


def _issue(rel_path: str, severity: str, itype: str, title: str, lineno: int, col: int,
           message: str, lines: List[str], snippet: Optional[str] = None,
           explanation: str = "", fix: str = "", reference: str = "",
           shown_line: Optional[str] = None, with_context: bool = True,
           category: Optional[str] = None, hardening: Optional[str] = None,
           threat_class: Optional[str] = None) -> Dict[str, Any]:
    if snippet is None:
        raw = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
        snippet = (shown_line if shown_line is not None else raw).strip()[:120]

    # Resolve category, threat_class, and hardening if not explicitly provided
    if not category:
        if itype in ("secret_leak", "sensitive_file"):
            category = CATEGORY_BREACH
            threat_class = "security_breach"
            if not hardening:
                hardening = DEFAULT_HARDENING_BREACH
        elif itype in ("python_syntax_error", "python_parse_error", "json_syntax_error",
                       "yaml_tab_error", "merge_conflict", "large_file", "accidental_binary",
                       "empty_file", "read_error"):
            category = CATEGORY_QUALITY
            threat_class = "code_quality"
            if not hardening:
                hardening = DEFAULT_HARDENING_QUALITY
        elif itype == "insecure_code":
            category = CATEGORY_EXPLOIT
            threat_class = "exploit_vector"
            if not hardening:
                hardening = DEFAULT_HARDENING_EXPLOIT
        else:
            category = CATEGORY_EXPLOIT if severity == "security" else CATEGORY_QUALITY
            threat_class = "exploit_vector" if severity == "security" else "code_quality"
            if not hardening:
                hardening = DEFAULT_HARDENING_EXPLOIT if severity == "security" else DEFAULT_HARDENING_QUALITY

    if not hardening:
        if category == CATEGORY_VIRUS:
            hardening = DEFAULT_HARDENING_VIRUS
        elif category == CATEGORY_EXPLOIT:
            hardening = DEFAULT_HARDENING_EXPLOIT
        elif category == CATEGORY_BREACH:
            hardening = DEFAULT_HARDENING_BREACH
        else:
            hardening = DEFAULT_HARDENING_QUALITY

    if not threat_class:
        if category == CATEGORY_VIRUS:
            threat_class = "virus_threat"
        elif category == CATEGORY_EXPLOIT:
            threat_class = "exploit_vector"
        elif category == CATEGORY_BREACH:
            threat_class = "security_breach"
        else:
            threat_class = "code_quality"

    return {
        "file": rel_path,
        "severity": severity,
        "type": itype,
        "title": title,
        "category": category,
        "threat_class": threat_class,
        "line": lineno,
        "col": col,
        "message": message,
        "snippet": snippet,
        "context": _context(lines, lineno, shown_line) if (with_context and lines) else [],
        "explanation": explanation,
        "fix": fix,
        "hardening": hardening,
        "reference": reference,
    }


def _is_placeholder(value: str) -> bool:
    low = value.lower().strip()
    if low in ("password", "secret", "mysecret", "mypassword", "changeme", "change_me", "none", "null", "dummy", "example"):
        return True
    if any(h in low for h in ("<", "{", "$", "%s", "xxxx", "your_", "your-", "token_redacted", "[token", "****", "....")):
        return True
    return False


def _is_sensitive_filename(rel_path: str) -> bool:
    base = os.path.basename(rel_path).lower()
    if any(base.endswith(s) for s in SENSITIVE_FILE_SAFE):
        return False
    if base in SENSITIVE_FILE_NAMES or base.startswith(".env."):
        return True
    return os.path.splitext(base)[1] in SENSITIVE_FILE_EXTS


def _is_suppressed(line: str) -> bool:
    """Lines carrying `# nosec` or `commitmaster:ignore` are deliberately accepted by the developer."""
    low = line.lower()
    return "nosec" in low or "commitmaster:ignore" in low


def _is_comment(line: str, ext: str) -> bool:
    s = line.lstrip()
    if ext in _PY or ext in (".sh", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".ps1"):
        return s.startswith("#")
    if ext in _JS:
        return s.startswith("//") or s.startswith("*") or s.startswith("/*")
    return False


# ── Main inspection ───────────────────────────────────────────────────────────

def inspect_file(repo_path: str, rel_path: str) -> List[Dict[str, Any]]:
    """Inspect a single file for pre-commit issues (see module docstring for the issue format)."""
    full_path = os.path.normpath(os.path.join(repo_path, rel_path))

    # Deleted files need no syntax / leak check
    if not os.path.exists(full_path) or os.path.isdir(full_path):
        return []

    try:
        st = os.stat(full_path)
        mtime, file_size = st.st_mtime, st.st_size
    except OSError as e:
        log.warning("Could not stat %s: %s", rel_path, e)
        return []

    if full_path in _FILE_INSPECT_CACHE:
        c_mtime, c_size, c_issues = _FILE_INSPECT_CACHE[full_path]
        if c_mtime == mtime and c_size == file_size:
            return list(c_issues)

    issues: List[Dict[str, Any]] = []

    _, ext = os.path.splitext(rel_path.lower())
    base_name = os.path.basename(rel_path)

    # 1. Oversized files
    if file_size > LARGE_FILE_BYTES:
        issues.append(_issue(
            rel_path, "warning", "large_file", "Very large file", 1, 0,
            f"Large file detected ({file_size / (1024 * 1024):.1f} MB). "
            "Storing large files in Git can bloat repository history.",
            [], snippet=f"File size: {file_size:,} bytes",
            explanation="Git keeps every version of every file forever, so large files make clones slow and cannot be "
                        "removed from history easily. GitHub rejects files above 100 MB.",
            fix="Add the file to .gitignore, or track it with Git LFS (git lfs track \"*." + (ext.lstrip('.') or 'bin') + "\").",
            reference="",
        ))

    # 2. Accidental binary executables / archives
    if ext in ACCIDENTAL_BINARY_EXTENSIONS and file_size > 1024 * 1024:
        issues.append(_issue(
            rel_path, "warning", "accidental_binary", "Binary file in source control", 1, 0,
            f"Binary archive/executable file ({ext}) detected. Verify this file belongs in source control.",
            [], snippet=f"Extension: {ext}",
            explanation="Build outputs and archives are usually generated artefacts; committing them bloats the "
                        "repository and they cannot be diffed or reviewed.",
            fix="Add it to .gitignore, or publish it as a GitHub Release asset instead.",
        ))

    # 3. Secret-bearing files (.env, private keys, ...)
    if _is_sensitive_filename(rel_path):
        issues.append(_issue(
            rel_path, "security", "sensitive_file", "Credential file about to be committed", 1, 0,
            f"'{base_name}' normally contains credentials and should not be committed.",
            [], snippet=f"{base_name}  (contents hidden)",
            explanation="Files such as .env, private keys and certificates hold secrets. Once pushed they are in the "
                        "repository history permanently, even if you delete the file later.",
            fix="1. Run: git rm --cached \"" + rel_path + "\"\n"
                "2. Add \"" + base_name + "\" to .gitignore.\n"
                "3. If it was already pushed, rotate every secret inside it.\n"
                "4. Keep a " + base_name + ".example with dummy values for teammates.",
            reference="CWE-538",
        ))

    # 4. Empty files
    if file_size == 0:
        ignored_empty_exts = (".db", ".db-wal", ".db-shm", ".db-journal", ".sqlite", ".sqlite3", ".lock", ".log")
        if base_name not in ("__init__.py", ".gitkeep", ".keep", ".gitignore") and ext not in ignored_empty_exts:
            issues.append(_issue(
                rel_path, "warning", "empty_file", "Empty file", 1, 0,
                "File is empty (0 bytes). Check if content was accidentally cleared.",
                [], snippet="(empty file)",
                explanation="An empty file is often the result of a failed save or an accidental select-all + delete.",
                fix="Open the file and confirm it should be empty; restore it with `git checkout -- <file>` if not.",
            ))
        res = issues[:MAX_ISSUES_PER_FILE + 5]
        _FILE_INSPECT_CACHE[full_path] = (mtime, file_size, res)
        return list(res)

    # Binary → skip text based checks
    if ext not in TEXT_EXTENSIONS and is_binary_file(full_path):
        res = issues[:MAX_ISSUES_PER_FILE + 5]
        _FILE_INSPECT_CACHE[full_path] = (mtime, file_size, res)
        return list(res)

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as exc:
        issues.append(_issue(
            rel_path, "error", "read_error", "File cannot be read", 1, 0,
            f"Could not read file: {exc}", [], snippet="",
            explanation="The file could not be opened - it may be locked by another program or have wrong permissions.",
            fix="Close programs that may be using the file and check its permissions.",
        ))
        res = issues[:MAX_ISSUES_PER_FILE + 5]
        _FILE_INSPECT_CACHE[full_path] = (mtime, file_size, res)
        return list(res)

    lines = content.splitlines()

    # 5. Merge conflict markers
    for lineno, line in enumerate(lines, start=1):
        for _, rx, cdesc in _COMPILED_CONFLICTS:
            if rx.search(line):
                issues.append(_issue(
                    rel_path, "error", "merge_conflict", "Unresolved merge conflict", lineno, 1,
                    f"Unresolved merge conflict marker found: {cdesc}", lines,
                    explanation="Git inserted these markers because two changes touched the same lines. Committing them "
                                "puts invalid text into the file and usually breaks the code.",
                    fix="Open the file, keep the correct version of the lines between <<<<<<< and >>>>>>>, "
                        "delete the three marker lines, then save.",
                ))
                break

    # 6. Secret / credential leaks
    is_test_or_example = any(k in rel_path.lower() for k in ("test", "example", "mock", "fixture"))
    for lineno, line in enumerate(lines, start=1):
        if len(issues) >= MAX_ISSUES_PER_FILE:
            break
        for stype, rx, sdesc in _COMPILED_SECRETS:
            match = rx.search(line)
            if not match:
                continue
            val = match.group("secret") if "secret" in match.groupdict() else match.group(0)
            if _is_placeholder(val):
                continue
            if is_test_or_example and len(val) < 25:
                continue
            issues.append(_issue(
                rel_path, "security", "secret_leak", sdesc, lineno, match.start("secret") + 1,
                f"Potential credential leak: {sdesc}", lines,
                shown_line=_masked_line(line, match),
                explanation=_SECRET_EXPLANATION, fix=_SECRET_FIX,
                reference="CWE-798",
            ))
            break

    # 7. Insecure code patterns
    for rule in _COMPILED_RULES:
        if rule["exts"] is not None and ext not in rule["exts"]:
            continue
        if ext in (".md", ".txt", ".rst", ".json", ".csv"):
            continue
        rx = rule["_rx"]
        skip_rx = rule["_skip_rx"]
        for lineno, line in enumerate(lines, start=1):
            if len(issues) >= MAX_ISSUES_PER_FILE:
                break
            if _is_comment(line, ext) or _is_suppressed(line):
                continue
            if skip_rx and skip_rx.search(line):
                continue
            m = rx.search(line)
            if not m:
                continue
            shown = None
            if rule.get("mask"):
                val = m.groupdict().get("secret") or ""
                if _is_placeholder(val) or (is_test_or_example and len(val) < 12):
                    continue
                shown = _masked_line(line, m)
            issues.append(_issue(
                rel_path, rule.get("severity", "security"), "insecure_code", rule["title"], lineno, m.start() + 1,
                f"Security risk: {rule['title']}", lines, shown_line=shown,
                explanation=rule["explanation"], fix=rule["fix"], reference=rule.get("reference", ""),
                category=rule.get("category"), hardening=rule.get("hardening"),
                threat_class=rule.get("threat_class"),
            ))

    # 8. Syntax validation by file type
    if ext in (".py", ".pyw"):
        try:
            ast.parse(content, filename=rel_path)
        except SyntaxError as e:
            lineno = e.lineno or 1
            issues.insert(0, _issue(
                rel_path, "error", "python_syntax_error", "Python syntax error", lineno, e.offset or 0,
                f"Python Syntax Error: {e.msg} (line {lineno})", lines,
                snippet=(e.text or "").strip()[:120],
                explanation=f"Python cannot parse this file: {e.msg}. Importing or running it will crash immediately.",
                fix="Check the highlighted line and the lines just above it for a missing bracket, quote or colon, "
                    "then run `python -m py_compile " + rel_path + "` to confirm.",
            ))
        except Exception as exc:
            issues.insert(0, _issue(
                rel_path, "error", "python_parse_error", "Python parse failure", 1, 0,
                f"Python AST parse error: {exc}", lines, snippet="",
                explanation="The Python parser failed unexpectedly on this file.",
                fix="Try running `python -m py_compile " + rel_path + "` to see the exact error.",
            ))

    elif ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            issues.insert(0, _issue(
                rel_path, "error", "json_syntax_error", "Invalid JSON", e.lineno, e.colno,
                f"JSON Syntax Error: {e.msg} (line {e.lineno}, col {e.colno})", lines,
                explanation=f"The file is not valid JSON ({e.msg}). Programs reading it will fail.",
                fix="Look for a trailing comma, a missing quote or bracket near the highlighted line. "
                    "Pasting the file into a JSON validator will pinpoint the problem.",
            ))

    elif ext in (".yaml", ".yml"):
        for lineno, line in enumerate(lines, start=1):
            if line.startswith("\t") or (line.lstrip() != line and "\t" in line[:len(line) - len(line.lstrip())]):
                issues.insert(0, _issue(
                    rel_path, "error", "yaml_tab_error", "Tab used for YAML indentation", lineno, 1,
                    "YAML indentation error: tabs cannot be used for indentation in YAML files (use spaces)", lines,
                    explanation="The YAML specification forbids tab characters for indentation; parsers will reject the file.",
                    fix="Replace the leading tab(s) with spaces (2 spaces per level is the common convention).",
                ))
                break

    res = issues[:MAX_ISSUES_PER_FILE + 5]
    _FILE_INSPECT_CACHE[full_path] = (mtime, file_size, res)
    return list(res)


def inspect_files(repo_path: str, files: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Inspect multiple files and return mapping of { file_path: [issues] }.
    Only files with detected issues are present in the output dictionary.
    """
    results: Dict[str, List[Dict[str, Any]]] = {}
    for f in files:
        file_issues = inspect_file(repo_path, f)
        if file_issues:
            results[f] = file_issues
    return results


def summarize_issues(issues_by_file: Dict[str, List[Dict[str, Any]]]) -> Dict[str, int]:
    """Return count breakdown of errors, security risks, warnings, and specialized threat categories."""
    summary = {
        "errors": 0, "security": 0, "warnings": 0, "total": 0,
        "virus_threats": 0, "exploit_vectors": 0, "security_breaches": 0, "code_quality": 0,
    }
    for file_issues in issues_by_file.values():
        for issue in file_issues:
            summary["total"] += 1
            sev = issue.get("severity")
            if sev == "error":
                summary["errors"] += 1
            elif sev == "security":
                summary["security"] += 1
            else:
                summary["warnings"] += 1

            tc = issue.get("threat_class")
            if tc == "virus_threat":
                summary["virus_threats"] += 1
            elif tc == "exploit_vector":
                summary["exploit_vectors"] += 1
            elif tc == "security_breach":
                summary["security_breaches"] += 1
            else:
                summary["code_quality"] += 1
    return summary


def format_issue_report(issues_by_file: Dict[str, List[Dict[str, Any]]], repo_name: str = "") -> str:
    """Format a clean, comprehensive, and professional vulnerability and security audit log."""
    from datetime import datetime, timezone
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    summary = summarize_issues(issues_by_file)
    total_files = len(issues_by_file)

    threat_parts = []
    if summary["virus_threats"]:
        threat_parts.append(f"{summary['virus_threats']} Virus/Malware")
    if summary["exploit_vectors"]:
        threat_parts.append(f"{summary['exploit_vectors']} Exploit Vectors")
    if summary["security_breaches"]:
        threat_parts.append(f"{summary['security_breaches']} Breaches/Leaks")
    threat_line = f"Threats:     {' | '.join(threat_parts)}" if threat_parts else "Threats:     0 Active Exploit / Virus Signatures"

    lines = [
        "=" * 80,
        "COMMITMASTER PRE-COMMIT HEALTH & VULNERABILITY AUDIT REPORT",
        f"Generated:   {now_str}",
        f"Repository:  {repo_name or 'Local Working Tree'}",
        f"Flagged:     {summary['total']} total issue(s) across {total_files} file(s)",
        f"Breakdown:   {summary['security']} Security / Secret Leaks | {summary['errors']} Critical / Syntax Errors | {summary['warnings']} Warnings",
        threat_line,
        "=" * 80,
        "",
    ]

    for path, issues in issues_by_file.items():
        lines.append(f"[FILE: {path}] ({len(issues)} issue{'s' if len(issues) != 1 else ''})")
        lines.append("-" * 80)
        for idx, i in enumerate(issues, start=1):
            sev = i.get('severity', 'warning').upper()
            title = i.get('title') or i.get('message', 'Issue')
            line_no = i.get('line', 1)
            ref = f" [{i['reference']}]" if i.get("reference") else ""
            lines.append(f"  {idx}. [{sev}] {title} (Line {line_no}){ref}")
            if i.get("category"):
                lines.append(f"     Threat Category: {i['category']}")

            ctx = i.get("context") or []
            if ctx:
                lines.append("     Code Context:")
                for c in ctx:
                    marker = ">" if c.get("hit") else " "
                    lines.append(f"       {marker} {c.get('line', ''):>4} | {c.get('text', '')}")
            elif i.get("snippet"):
                lines.append(f"     Snippet: {i['snippet']}")

            if i.get("explanation"):
                lines.append(f"     Why it matters: {i['explanation']}")
            if i.get("fix"):
                fix_lines = i["fix"].splitlines()
                lines.append(f"     Recommended Fix: {fix_lines[0]}")
                for fl in fix_lines[1:]:
                    lines.append(f"                      {fl}")
            if i.get("hardening"):
                h_lines = i["hardening"].splitlines()
                lines.append(f"     Project Hardening: {h_lines[0]}")
                for hl in h_lines[1:]:
                    lines.append(f"                        {hl}")
            lines.append("")
        lines.append("")

    lines.append("=" * 80)
    lines.append("End of CommitMaster Pre-Commit Vulnerability Log.")
    lines.append("=" * 80)
    return "\n".join(lines).strip()
