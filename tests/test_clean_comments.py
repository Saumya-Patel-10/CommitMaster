"""
Tests for AI Generated Comment Cleanness, Junk & Hashtag Stripping, and Pre-Commit Security.
"""

import unittest
from commitmaster import ai_messages
from commitmaster import commit_engine
from commitmaster import file_inspector


class TestCleanComments(unittest.TestCase):

    def test_clean_summary_no_hashtags_or_junk(self):
        """Verify _clean_summary strips hashtags, backticks, markdown, and diff noise."""
        raw = "### feat(#auth): Add new OAuth2 login flow #v2... (+12/-4 lines)"
        cleaned = ai_messages._clean_summary(raw)
        self.assertEqual(cleaned, "feat(auth): Add new OAuth2 login flow")
        self.assertNotIn("#", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertNotIn("+12/-4", cleaned)
        self.assertFalse(cleaned.endswith("."))

    def test_clean_summary_backticks_and_quotes(self):
        """Verify summary has no backticks, single/double quotes, or asterisks."""
        raw = 'fix: update `"database_service.py"` **connection** logic.'
        cleaned = ai_messages._clean_summary(raw)
        self.assertNotIn("`", cleaned)
        self.assertNotIn('"', cleaned)
        self.assertNotIn("'", cleaned)
        self.assertNotIn("*", cleaned)
        self.assertFalse(cleaned.endswith("."))

    def test_clean_description_no_hashtags(self):
        """Verify _clean_description transforms markdown ### headers to clean section headers and removes social hashtags."""
        raw = (
            "### New Features #release\n"
            "- Adds function `fetch_users` for #auth\n"
            "- **Updates** `\"UserManager\"` with \\\"clean\\\" logic (+4/-1 lines)\n"
            "- Refines <br> UI components #ui\n"
            "### Changes & Improvements\n"
            "- Updates logic in `server.py`\n"
        )
        cleaned = ai_messages._clean_description(raw)

        # Ensure NO line starts with '#' or contains '#'
        for line in cleaned.splitlines():
            self.assertFalse(line.strip().startswith("#"), f"Line should not start with #: {line}")
            self.assertNotIn("#", line, f"Line should not contain hashtag: {line}")

        # Ensure section headers are clean
        self.assertIn("New Features:", cleaned)
        self.assertIn("Changes & Improvements:", cleaned)

        # Ensure backticks are converted and asterisks removed
        self.assertNotIn("`", cleaned)
        self.assertNotIn("*", cleaned)
        self.assertNotIn("<br>", cleaned)
        self.assertNotIn("+4/-1", cleaned)

    def test_compose_commit_message(self):
        """Verify composed commit message is neat, clean, and contains zero hashtags."""
        summary = "### feat: implement tailscale network #mesh"
        description = (
            "### New Features\n"
            "- Adds `tailscale_setup.py` auto-installer\n"
            "### Changes & Improvements\n"
            "- Refines **fleet** management table #clean"
        )
        msg = ai_messages.compose_commit_message(summary, description)

        # Must not contain any hashtag '#' anywhere
        self.assertNotIn("#", msg)
        self.assertNotIn("`", msg)
        self.assertNotIn("*", msg)
        self.assertTrue(msg.startswith("feat: implement tailscale network"))
        self.assertIn("New Features:\n- Adds \"tailscale_setup.py\" auto-installer", msg)

    def test_sanitize_commit_message_engine(self):
        """Verify commit_engine.sanitize_commit_message sanitizes raw input."""
        dirty = "### fix: resolve token leak #security\n\n### Bug Fixes\n- Fixes `auth.py`"
        clean = commit_engine.sanitize_commit_message(dirty)
        self.assertNotIn("#", clean)
        self.assertNotIn("`", clean)
        self.assertTrue(clean.startswith("fix: resolve token"))

    def test_smoke_test_security_audit(self):
        """Verify tests/smoke_test.py has 0 vulnerability issues in file_inspector."""
        issues = file_inspector.inspect_file(".", "tests/smoke_test.py")
        self.assertEqual(len(issues), 0, f"Expected 0 issues, got: {issues}")


if __name__ == "__main__":
    unittest.main()

