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
                "context": [{"line": 15, "hit": True, "text": "AWS_KEY = AKIAEXAMPLE"}],
                "explanation": "Hardcoded credentials present in source file.",
                "fix": "Store key in environment variable.",
            }]
        }
        report = file_inspector.format_issue_report(issues, "CommitMaster")
        self.assertIn("COMMITMASTER PRE-COMMIT HEALTH & VULNERABILITY AUDIT REPORT", report)
        self.assertIn("[FILE: config.py]", report)
        self.assertIn("[SECURITY] Hardcoded AWS Access Key (Line 15) [CWE-798]", report)
        self.assertIn("Why it matters: Hardcoded credentials present in source file.", report)
        self.assertIn("Recommended Fix: Store key in environment variable.", report)


if __name__ == "__main__":
    unittest.main()
