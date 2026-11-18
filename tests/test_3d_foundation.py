"""
Tests for CommitMaster 3D Foundation Modules.
Verifies accessibility detection, scene data generators, webview bridge, and JSON serializability.
"""
import json
import os
import unittest

from commitmaster import accessibility, scene_data, webview_host


class Test3DFoundation(unittest.TestCase):

    def test_accessibility_detection(self):
        # 1. detect_reduced_motion
        reduced = accessibility.detect_reduced_motion()
        self.assertIsInstance(reduced, bool)

        # 2. detect_battery_saver
        battery = accessibility.detect_battery_saver()
        self.assertIsInstance(battery, bool)

        # 3. classify_performance_tier
        tier = accessibility.classify_performance_tier()
        self.assertIn(tier, ("high", "medium", "low"))

        # 4. get_accessibility_state with user overrides
        state = accessibility.get_accessibility_state({
            "reduced_motion": True,
            "performance_tier": "low",
            "enable_3d": False,
        })
        self.assertTrue(state["reduced_motion"])
        self.assertEqual(state["performance_tier"], "low")
        self.assertFalse(state["3d_enabled"])

    def test_scene_data_commit_galaxy(self):
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data = scene_data.build_commit_galaxy_data(repo_dir, max_commits=20)

        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertIn("branches", data)
        self.assertIn("summary", data)

        # Validate JSON serializability
        serialized = json.dumps(data)
        self.assertTrue(len(serialized) > 10)

    def test_scene_data_architecture(self):
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data = scene_data.build_architecture_data(repo_dir)

        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertIn("metrics", data)

        # Validate JSON serializability
        serialized = json.dumps(data)
        self.assertTrue(len(serialized) > 10)

    def test_scene_data_security(self):
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data = scene_data.build_security_data(repo_dir)

        self.assertIn("findings", data)
        self.assertIn("summary", data)
        self.assertIn("healthScore", data)

        # Validate JSON serializability
        serialized = json.dumps(data)
        self.assertTrue(len(serialized) > 10)

    def test_scene_data_analytics_and_agents(self):
        # Analytics data
        analytics = scene_data.build_analytics_data(days=7)
        self.assertIn("daily", analytics)
        self.assertIn("summary", analytics)
        json.dumps(analytics)

        # Agent workflow data
        agents = scene_data.build_agent_workflow_data()
        self.assertIn("agents", agents)
        self.assertIn("connections", agents)
        self.assertEqual(len(agents["agents"]), 5)
        json.dumps(agents)

        # Device topology data
        topology = scene_data.build_device_topology_data()
        self.assertIn("devices", topology)
        json.dumps(topology)

    def test_webview_host_paths(self):
        dist_path = webview_host.get_web_dist_path()
        self.assertTrue(isinstance(dist_path, str) and len(dist_path) > 0)
        self.assertTrue(os.path.exists(dist_path))

        avail = webview_host.is_webview2_available()
        self.assertIsInstance(avail, bool)


if __name__ == "__main__":
    unittest.main()
