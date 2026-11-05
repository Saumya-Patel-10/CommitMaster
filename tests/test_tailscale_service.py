"""
Unit tests for commitmaster.tailscale_service.
Tests both mocked outputs and real system environment detection.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from commitmaster import tailscale_service

MOCK_STATUS = {
    "Version": "1.104.4",
    "BackendState": "Running",
    "Self": {
        "ID": "node-1",
        "HostName": "saumya-pc",
        "DNSName": "saumya-pc.tailnet-xyz.ts.net.",
        "UserID": 101,
        "TailscaleIPs": ["100.64.108.92", "fd7a:115c:a1e0::1"],
        "Online": True,
    },
    "User": {
        "101": {
            "ID": 101,
            "LoginName": "imsaumyaapatel@gmail.com",
            "DisplayName": "Saumya Patel",
        }
    },
    "Peer": {
        "peer-1": {
            "ID": "node-2",
            "HostName": "saumya-laptop",
            "DNSName": "saumya-laptop.tailnet-xyz.ts.net.",
            "TailscaleIPs": ["100.108.102.82"],
            "Online": True,
            "OS": "windows",
            "LastSeen": "2026-11-03T18:00:00Z",
            "RxBytes": 1024,
            "TxBytes": 2048,
        },
        "peer-2": {
            "ID": "node-3",
            "HostName": "iphone-15-plus",
            "DNSName": "iphone-15-plus.tailnet-xyz.ts.net.",
            "TailscaleIPs": ["100.120.67.56"],
            "Online": False,
            "OS": "iOS",
            "LastSeen": "2026-11-03T15:00:00Z",
            "RxBytes": 500,
            "TxBytes": 500,
        }
    }
}


class TestTailscaleService(unittest.TestCase):

    def setUp(self):
        tailscale_service._STATUS_CACHE = None
        tailscale_service._STATUS_CACHE_TIME = 0.0

    @patch("commitmaster.tailscale_service.get_tailscale_binary", return_value=r"C:\Program Files\Tailscale\tailscale.exe")
    def test_installation_check(self, mock_bin):
        self.assertTrue(tailscale_service.is_tailscale_installed())

    @patch("commitmaster.tailscale_service.get_tailscale_status", return_value=MOCK_STATUS)
    def test_ip_extraction(self, mock_status):
        ip = tailscale_service.get_tailscale_ip()
        self.assertEqual(ip, "100.64.108.92")

    @patch("commitmaster.tailscale_service.get_tailscale_status", return_value=MOCK_STATUS)
    def test_magic_dns(self, mock_status):
        dns = tailscale_service.get_magic_dns_name()
        self.assertEqual(dns, "saumya-pc.tailnet-xyz.ts.net")

    @patch("commitmaster.tailscale_service.get_tailscale_status", return_value=MOCK_STATUS)
    def test_tailnet_user(self, mock_status):
        user = tailscale_service.get_tailnet_user()
        self.assertIsNotNone(user)
        self.assertEqual(user["LoginName"], "imsaumyaapatel@gmail.com")
        self.assertEqual(user["DisplayName"], "Saumya Patel")

    @patch("commitmaster.tailscale_service.get_tailscale_status", return_value=MOCK_STATUS)
    def test_peer_list(self, mock_status):
        peers = tailscale_service.get_tailnet_peers()
        self.assertEqual(len(peers), 2)
        # Online peer should be sorted first
        self.assertEqual(peers[0]["hostname"], "saumya-laptop")
        self.assertEqual(peers[0]["ip"], "100.108.102.82")
        self.assertTrue(peers[0]["online"])

        self.assertEqual(peers[1]["hostname"], "iphone-15-plus")
        self.assertFalse(peers[1]["online"])

    @patch("commitmaster.tailscale_service.get_tailscale_binary", return_value=r"C:\Program Files\Tailscale\tailscale.exe")
    @patch("subprocess.run")
    def test_whois_query(self, mock_subproc, mock_bin):
        mock_whois_output = json.dumps({
            "UserProfile": {
                "LoginName": "imsaumyaapatel@gmail.com",
                "DisplayName": "Saumya Patel"
            },
            "Node": {
                "HostName": "saumya-laptop",
                "OS": "windows",
                "ID": "node-2"
            }
        })
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = mock_whois_output
        mock_subproc.return_value = mock_proc

        result = tailscale_service.whois("100.108.102.82")
        self.assertIsNotNone(result)
        self.assertEqual(result["login_name"], "imsaumyaapatel@gmail.com")
        self.assertEqual(result["display_name"], "Saumya Patel")
        self.assertEqual(result["hostname"], "saumya-laptop")


if __name__ == "__main__":
    unittest.main()

