"""Unit tests for AI multi-provider support, anti-repetition filtering, and quote/junk sanitization."""
import os
import unittest
from unittest.mock import MagicMock, patch

from commitmaster import ai_messages


class TestAIProvidersAndSanitization(unittest.TestCase):
    def test_clean_summary_removes_backticks_and_quotes(self):
        # Repetitive backtick patterns seen in the user screenshot
        raw = 'refactor(jobs-explorer-page): refine `JobsExplorerPage` logic'
        cleaned = ai_messages._clean_summary(raw)
        self.assertEqual(cleaned, 'refactor(jobs-explorer-page): refine JobsExplorerPage logic')
        self.assertNotIn('`', cleaned)

        # Junk quotes
        raw2 = '"feat(auth): add OAuth2 token support"'
        cleaned2 = ai_messages._clean_summary(raw2)
        self.assertEqual(cleaned2, 'feat(auth): add OAuth2 token support')

        raw3 = "'''fix(api): handle timeout exception'''"
        cleaned3 = ai_messages._clean_summary(raw3)
        self.assertEqual(cleaned3, 'fix(api): handle timeout exception')

    def test_clean_description_eliminates_headline_repetition(self):
        summary = 'refactor(jobs-explorer-page): refine JobsExplorerPage logic'
        # Description repeating exactly what the headline said
        desc = (
            "- Updates logic in `JobsExplorerPage`\n"
            "- Updates logic in JobsExplorerPage\n"
            "- Adjust table row layout and filter callbacks"
        )
        cleaned = ai_messages._clean_description(desc, summary=summary)
        # Repetitive lines should be removed, leaving only meaningful bullet
        self.assertNotIn("Updates logic in `JobsExplorerPage`", cleaned)
        self.assertNotIn("Updates logic in JobsExplorerPage", cleaned)
        self.assertIn("Adjust table row layout and filter callbacks", cleaned)

    def test_clean_description_filters_boilerplate_and_quotes(self):
        desc = (
            '"- Minor changes and updates"\n'
            "- Fix validation edge case when email is empty"
        )
        cleaned = ai_messages._clean_description(desc)
        self.assertNotIn("Minor changes", cleaned)
        self.assertIn("Fix validation edge case when email is empty", cleaned)
        self.assertFalse(cleaned.startswith('"'))

    def test_provider_helpers(self):
        cfg_openai = {"ai": {"provider": "openai", "openai_api_key": "sk-12345"}}
        self.assertEqual(ai_messages.get_active_provider(cfg_openai), "openai")
        self.assertEqual(ai_messages.get_provider_label("openai"), "OpenAI")
        self.assertEqual(ai_messages.get_provider_key(cfg_openai, "openai"), "sk-12345")
        self.assertEqual(ai_messages.get_provider_model(cfg_openai, "openai"), "gpt-4o-mini")

        cfg_claude = {"ai": {"provider": "claude", "claude_api_key": "sk-ant-abc"}}
        self.assertEqual(ai_messages.get_active_provider(cfg_claude), "claude")
        self.assertEqual(ai_messages.get_provider_label("claude"), "Anthropic Claude")
        self.assertEqual(ai_messages.get_provider_key(cfg_claude, "claude"), "sk-ant-abc")
        self.assertEqual(ai_messages.get_provider_model(cfg_claude, "claude"), "claude-3-5-haiku-20241022")

        cfg_gemini = {"ai": {"provider": "gemini", "gemini_api_key": "AIzaSyTest"}}
        self.assertEqual(ai_messages.get_active_provider(cfg_gemini), "gemini")
        self.assertEqual(ai_messages.get_provider_label("gemini"), "Google Gemini")
        self.assertEqual(ai_messages.get_provider_key(cfg_gemini, "gemini"), "AIzaSyTest")
        self.assertEqual(ai_messages.get_provider_model(cfg_gemini, "gemini"), "gemini-1.5-flash")

    def test_heuristic_message_tsx_no_backticks_and_no_repetition(self):
        # Testing frontend .tsx files as seen in the user's report
        diff = """--- a/frontend/src/features/jobs/jobs-explorer-page.tsx
+++ b/frontend/src/features/jobs/jobs-explorer-page.tsx
@@ -10,1 +10,1 @@
-  const [jobs, setJobs] = useState([]);
+  const [jobs, setJobs] = useState<Job[]>([]);
"""
        info = ai_messages._analyze_diff(diff, "frontend/src/features/jobs/jobs-explorer-page.tsx")
        res = ai_messages._heuristic_message("frontend/src/features/jobs/jobs-explorer-page.tsx", info)
        summary, desc = res["summary"], res["description"]

        self.assertNotIn("`", summary)
        self.assertNotIn("(+1/-1", summary)
        # Summary mentions the component only once without redundant scope duplication
        self.assertEqual(summary, "refactor: enhance jobs explorer page and its logic")
        # Description should not repeat the summary
        self.assertNotIn(summary, desc)
        # Should not have duplicate "Updates logic in JobsExplorerPage" or generic filler
        self.assertNotIn("- Updates logic in `JobsExplorerPage`", desc)
        self.assertNotIn("Refines implementation details in jobs-explorer-page.tsx", desc)

    def test_live_browser_page_headline_and_clean_summary(self):
        # Test cleaning redundant AI output: "refactor(live-browser-page): enhance live browser page logic (+4/-4…"
        raw_ai = "refactor(live-browser-page): enhance live browser page logic (+4/-4 lines)"
        cleaned = ai_messages._clean_summary(raw_ai)
        self.assertEqual(cleaned, "refactor: enhance live browser page and its logic")
        self.assertNotIn("(+4/-4", cleaned)
        self.assertNotIn("live-browser-page): enhance live browser page", cleaned)

        # Test heuristic generation for live-browser-page.tsx
        diff = """--- a/frontend/src/features/live-browser/live-browser-page.tsx
+++ b/frontend/src/features/live-browser/live-browser-page.tsx
@@ -40,4 +40,4 @@
-  const ws = useSocket(url);
+  const ws = useSocket(url, { reconnect: true });
"""
        info = ai_messages._analyze_diff(diff, "frontend/src/features/live-browser/live-browser-page.tsx")
        res = ai_messages._heuristic_message("frontend/src/features/live-browser/live-browser-page.tsx", info)
        self.assertEqual(res["summary"], "refactor: enhance live browser page and its logic")
        self.assertNotIn("(+4/-4", res["summary"])
        self.assertNotIn("Refines implementation details in live-browser-page.tsx", res["description"])

    @patch("commitmaster.ai_messages.requests.post")
    def test_call_openai_mock(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"summary": "feat: test summary", "description": "- test item"}'}}]
        }
        mock_post.return_value = mock_resp

        cfg = {"ai": {"provider": "openai", "openai_api_key": "sk-test", "openai_model": "gpt-4o-mini"}}
        res = ai_messages._call_openai(cfg, "system prompt", "user prompt")
        self.assertIn("summary", res)
        self.assertEqual(mock_post.call_count, 1)

    @patch("commitmaster.ai_messages.requests.post")
    def test_call_claude_mock(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "content": [{"type": "text", "text": '{"summary": "feat: claude summary", "description": "- test item"}'}]
        }
        mock_post.return_value = mock_resp

        cfg = {"ai": {"provider": "claude", "claude_api_key": "sk-ant-test", "claude_model": "claude-3-5-haiku-20241022"}}
        res = ai_messages._call_claude(cfg, "system prompt", "user prompt")
        self.assertIn("summary", res)
        self.assertEqual(mock_post.call_count, 1)

    @patch("commitmaster.ai_messages.requests.post")
    def test_call_gemini_mock(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{"text": '{"summary": "feat: gemini summary", "description": "- test item"}'}]
                }
            }]
        }
        mock_post.return_value = mock_resp

        cfg = {"ai": {"provider": "gemini", "gemini_api_key": "AIzaSyFake", "gemini_model": "gemini-1.5-flash"}}
        res = ai_messages._call_gemini(cfg, "system prompt", "user prompt")
        self.assertIn("summary", res)
        self.assertEqual(mock_post.call_count, 1)

    def test_connection_validation_missing_key(self):
        cfg_no_key = {"ai": {"provider": "openai", "openai_api_key": ""}}
        ok, msg = ai_messages.test_connection(cfg_no_key)
        self.assertFalse(ok)
        self.assertIn("key missing", msg.lower())

        cfg_gemini_no_key = {"ai": {"provider": "gemini", "gemini_api_key": ""}}
        ok, msg = ai_messages.test_connection(cfg_gemini_no_key)
        self.assertFalse(ok)
        self.assertIn("key missing", msg.lower())


if __name__ == "__main__":
    unittest.main()
