"""
Unit tests for Tailscale features in server.py.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import server


class TestServerTailscale(unittest.TestCase):

    def setUp(self):
        server.app.config["TESTING"] = True
        self.client = server.app.test_client()

    @patch("commitmaster.tailscale_service.is_tailscale_installed", return_value=True)
    @patch("commitmaster.tailscale_service.is_tailnet_connected", return_value=True)
    @patch("commitmaster.tailscale_service.get_tailscale_ip", return_value="100.64.108.92")
    @patch("commitmaster.tailscale_service.get_magic_dns_name", return_value="saumya-pc.tailnet.ts.net")
    @patch("commitmaster.tailscale_service.get_device_hostname", return_value="saumya-pc")
    def test_health_endpoint_has_tailscale(self, m_host, m_dns, m_ip, m_conn, m_inst):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("tailscale", data)
        self.assertTrue(data["tailscale"]["active"])
        self.assertEqual(data["tailscale"]["ip"], "100.64.108.92")
        self.assertEqual(data["tailscale"]["magic_dns"], "saumya-pc.tailnet.ts.net")

    @patch("commitmaster.tailscale_service.whois")
    def test_auth_tailscale_sso(self, mock_whois):
        mock_whois.return_value = {
            "login_name": "saumya.patel.dev@gmail.com",
            "display_name": "Saumya Patel",
            "hostname": "saumya-laptop",
            "os": "windows"
        }
        resp = self.client.post("/api/auth/tailscale", environ_base={"REMOTE_ADDR": "100.108.102.82"})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("ok"))
        self.assertIn("token", data)
        self.assertEqual(data["user"]["email"], "saumya.patel.dev@gmail.com")
        self.assertEqual(data["tailscale"]["node"], "saumya-laptop")


if __name__ == "__main__":
    unittest.main()

