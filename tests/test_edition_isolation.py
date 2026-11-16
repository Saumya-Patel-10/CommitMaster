"""Side-by-side data directories and shell identities.

These checks run in fresh interpreters so the admin lock in tests/__init__.py
does not decide the product. They do not create Windows shortcuts.
"""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _python(code: str, env: dict, timeout: int = 60) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    merged.update(env)
    merged["PYTHONPATH"] = ROOT
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=merged,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestEditionDataDirectories(unittest.TestCase):
    def test_same_root_keeps_three_directories(self):
        with tempfile.TemporaryDirectory() as root:
            script = textwrap.dedent("""
                import os
                os.environ["COMMITMASTER_DATA_DIR"] = os.environ["ROOT"]
                os.environ["LOCALAPPDATA"] = os.environ["LOCAL"]
                from commitmaster import product
                import commitmaster.paths as paths
                product.activate(os.environ["PRODUCT"])
                print(paths.get_data_dir())
                print(paths.get_db_path())
                print(paths.get_config_path())
            """)
            paths = {}
            for name in ("user", "admin", "demo"):
                result = _python(script, {
                    "ROOT": root,
                    "LOCAL": os.path.join(root, "local"),
                    "PRODUCT": name,
                })
                self.assertEqual(result.returncode, 0, result.stderr)
                data_dir, db_path, config_path = result.stdout.strip().splitlines()
                paths[name] = data_dir
                self.assertTrue(data_dir.startswith(os.path.abspath(root)))
                self.assertTrue(db_path.endswith(os.path.join(os.path.basename(data_dir), "commitmaster.db")))
                self.assertTrue(config_path.endswith("config.json"))
                self.assertEqual(os.path.dirname(db_path), data_dir)
                self.assertEqual(os.path.dirname(config_path), data_dir)
            self.assertEqual(len(set(paths.values())), 3)
            self.assertTrue(paths["user"].endswith("CommitMaster"))
            self.assertTrue(paths["admin"].endswith("CommitMaster-Admin"))
            self.assertTrue(paths["demo"].endswith("CommitMaster-Demo"))

    def test_workspace_database_does_not_merge_products(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = os.path.join(root, "workspace")
            local = os.path.join(root, "local")
            os.makedirs(workspace)
            with open(os.path.join(workspace, "commitmaster.db"), "wb") as handle:
                handle.write(b"user-db")
            with open(os.path.join(workspace, "config.json"), "w", encoding="utf-8") as handle:
                handle.write('{"edition":"workspace"}')
            for secret in (".admin_session", ".admin_initial_secret", ".session_token", "server_commitmaster.db"):
                with open(os.path.join(workspace, secret), "w", encoding="utf-8") as handle:
                    handle.write("secret")
            script = textwrap.dedent("""
                import os, sys
                os.environ.pop("COMMITMASTER_DATA_DIR", None)
                os.environ["LOCALAPPDATA"] = os.environ["LOCAL"]
                import commitmaster.paths as paths
                paths._WORKSPACE_DIR = os.environ["WS"]
                if os.environ.get("FROZEN") == "1":
                    sys.frozen = True
                from commitmaster import product
                product.activate(os.environ["PRODUCT"])
                data = paths.get_data_dir()
                print(data)
                print("db", os.path.exists(os.path.join(data, "commitmaster.db")))
                print("config", os.path.exists(os.path.join(data, "config.json")))
                print("admin_session", os.path.exists(os.path.join(data, ".admin_session")))
                print("admin_secret", os.path.exists(os.path.join(data, ".admin_initial_secret")))
                print("session", os.path.exists(os.path.join(data, ".session_token")))
                print("server_db", os.path.exists(os.path.join(data, "server_commitmaster.db")))
                print("is_workspace", os.path.abspath(data) == os.path.abspath(os.environ["WS"]))
            """)
            user = _python(script, {"LOCAL": local, "WS": workspace, "PRODUCT": "user"})
            self.assertEqual(user.returncode, 0, user.stderr)
            user_lines = dict(line.split(" ", 1) for line in user.stdout.splitlines() if " " in line)
            user_dir = user.stdout.splitlines()[0]
            self.assertTrue(user_dir.endswith(os.path.join("local", "CommitMaster")))
            self.assertEqual(user_lines["db"], "True")
            self.assertEqual(user_lines["config"], "True")
            self.assertEqual(user_lines["admin_session"], "False")
            self.assertEqual(user_lines["admin_secret"], "False")
            self.assertEqual(user_lines["session"], "False")
            self.assertEqual(user_lines["server_db"], "False")
            self.assertEqual(user_lines["is_workspace"], "False")
            # A second launch must not replace the user's copy.
            with open(os.path.join(user_dir, "commitmaster.db"), "wb") as handle:
                handle.write(b"kept")
            again = _python(script, {"LOCAL": local, "WS": workspace, "PRODUCT": "user"})
            self.assertEqual(again.returncode, 0, again.stderr)
            with open(os.path.join(user_dir, "commitmaster.db"), "rb") as handle:
                self.assertEqual(handle.read(), b"kept")

            for name, folder in (("admin", "CommitMaster-Admin"), ("demo", "CommitMaster-Demo")):
                result = _python(script, {"LOCAL": local, "WS": workspace, "PRODUCT": name})
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = result.stdout.splitlines()
                self.assertTrue(lines[0].endswith(os.path.join("local", folder)))
                copied = dict(line.split(" ", 1) for line in lines if " " in line)
                self.assertEqual(copied["db"], "False")
                self.assertEqual(copied["admin_session"], "False")
                self.assertEqual(copied["is_workspace"], "False")

            frozen = _python(script, {"LOCAL": local, "WS": workspace, "PRODUCT": "user", "FROZEN": "1"})
            self.assertEqual(frozen.returncode, 0, frozen.stderr)
            self.assertNotIn(os.path.abspath(workspace), frozen.stdout.splitlines()[0])

    def test_user_refuses_the_admin_directory(self):
        with tempfile.TemporaryDirectory() as root:
            admin_dir = os.path.join(root, "CommitMaster-Admin")
            os.makedirs(admin_dir)
            script = textwrap.dedent("""
                import os
                os.environ["COMMITMASTER_DATA_DIR"] = os.environ["ADMIN"]
                from commitmaster import product
                product.activate("user")
                import commitmaster.paths as paths
                try:
                    paths.get_data_dir()
                except paths.DataDirectoryError as exc:
                    print("refused")
                    print(str(exc))
                else:
                    raise SystemExit("user product opened the admin directory")
            """)
            result = _python(script, {"ADMIN": admin_dir})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("refused", result.stdout)
            self.assertFalse(os.path.exists(os.path.join(admin_dir, "commitmaster.db")))


class TestShellIdentities(unittest.TestCase):
    def test_each_edition_has_its_own_identity(self):
        from commitmaster import windows_integration
        user = windows_integration.shell_identity("user")
        admin = windows_integration.shell_identity("admin")
        demo = windows_integration.shell_identity("demo")
        unified = windows_integration.shell_identity("unified")
        self.assertEqual(user["aumid"], "CommitMaster.App.User")
        self.assertEqual(admin["aumid"], "CommitMaster.App.Admin")
        self.assertEqual(demo["aumid"], "CommitMaster.App.Demo")
        self.assertEqual(unified["aumid"], user["aumid"])
        self.assertEqual(len({user["aumid"], admin["aumid"], demo["aumid"]}), 3)
        self.assertEqual(len({user["shortcut_name"], admin["shortcut_name"], demo["shortcut_name"]}), 3)
        self.assertEqual(user["shortcut_name"], "CommitMaster User")
        self.assertEqual(admin["shortcut_name"], "CommitMaster Admin")
        self.assertEqual(demo["shortcut_name"], "CommitMaster Demo")
        self.assertNotEqual(user["icon_name"], demo["icon_name"])
        self.assertNotEqual(user["exe_name"], demo["exe_name"])
        self.assertNotEqual(admin["exe_name"], demo["exe_name"])

    def test_shortcut_target_is_honored(self):
        import inspect
        from commitmaster import windows_integration
        source = inspect.getsource(windows_integration.create_desktop_shortcut)
        self.assertNotIn('target = "user"', source)
        self.assertEqual(
            [item["name"] for item in windows_integration.shortcut_specs("admin")],
            ["CommitMaster Admin"],
        )
        self.assertEqual(
            [item["name"] for item in windows_integration.shortcut_specs("demo")],
            ["CommitMaster Demo"],
        )
        self.assertEqual(
            [item["name"] for item in windows_integration.shortcut_specs("both")],
            ["CommitMaster User", "CommitMaster Admin"],
        )
        self.assertNotIn(
            "CommitMaster Demo",
            [item["name"] for item in windows_integration.shortcut_specs("user")],
        )
        if os.name != "nt":
            ok, message = windows_integration.create_desktop_shortcut("demo")
            self.assertFalse(ok)
            self.assertIn("Windows", message)

    def test_demo_process_does_not_claim_the_user_id(self):
        script = textwrap.dedent("""
            from commitmaster import product, windows_integration
            product.activate("demo")
            print(windows_integration.process_app_user_model_id("user"))
            print(windows_integration.process_app_user_model_id("unified"))
            print(windows_integration._edition_key("user"))
        """)
        result = _python(script, {})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(lines, [
            "CommitMaster.App.Demo",
            "CommitMaster.App.Demo",
            "demo",
        ])

    def test_demo_icon_is_distinct(self):
        from commitmaster import windows_integration
        user_icon = windows_integration.get_icon_path("user")
        admin_icon = windows_integration.get_icon_path("admin")
        demo_icon = windows_integration.get_icon_path("demo")
        self.assertIsNotNone(demo_icon)
        self.assertTrue(os.path.isfile(demo_icon))
        self.assertNotEqual(os.path.abspath(demo_icon), os.path.abspath(user_icon))
        self.assertNotEqual(os.path.abspath(demo_icon), os.path.abspath(admin_icon))
        with open(demo_icon, "rb") as handle:
            demo_bytes = handle.read()
        with open(user_icon, "rb") as handle:
            user_bytes = handle.read()
        self.assertNotEqual(demo_bytes, user_bytes)
        self.assertTrue(demo_bytes.startswith(b"\x00\x00\x01\x00"))
        logo = os.path.join(ROOT, "assets", "logo_demo.png")
        self.assertTrue(os.path.isfile(logo))

    def test_store_identity_is_unchanged(self):
        import json
        with open(os.path.join(ROOT, "store_identity.json"), encoding="utf-8") as handle:
            identity = json.load(handle)
        self.assertEqual(identity["package_name"], "SaumyaPatel.CommitMaster")
        self.assertEqual(identity["publisher_name"], "CN=7522A476-A1F1-4D1A-80FA-BEFE0A4BF5F8")
        self.assertEqual(identity["version"], "1.1.0.0")
        self.assertEqual(identity["executable"], "CommitMaster-User.exe")


if __name__ == "__main__":
    unittest.main()
