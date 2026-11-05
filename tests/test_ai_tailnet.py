"""
Unit tests for Tailnet AI compute routing in ai_messages.py.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import ai_messages


class TestTailnetAIRouting(unittest.TestCase):

    @patch("commitmaster.tailscale_service.is_tailscale_installed", return_value=True)
    @patch("commitmaster.tailscale_service.discover_tailnet_ai_nodes")
    def test_tailnet_ai_fallback(self, mock_discover, mock_installed):
        mock_discover.return_value = [
            {
                "host": "localhost (This PC)",
                "base_url": "http://127.0.0.1:11434/v1",
                "models": ["llama3"]
            },
            {
                "host": "saumya-pc (100.64.108.92)",
                "base_url": "http://100.64.108.92:11434/v1",
                "models": ["gemma-2-9b-it", "qwen2.5-coder"]
            }
        ]

        cfg = {"ai": {"provider": "ollama", "base_url": "http://127.0.0.1:11434/v1"}}
        rerouted = ai_messages._tailnet_ai_fallback_cfg(cfg)

        self.assertIsNotNone(rerouted)
        self.assertEqual(rerouted["ai"]["base_url"], "http://100.64.108.92:11434/v1")
        self.assertEqual(rerouted["ai"]["model"], "gemma-2-9b-it")


if __name__ == "__main__":
    unittest.main()

