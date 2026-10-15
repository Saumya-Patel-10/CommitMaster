import json
import unittest
from unittest import mock

from commitmaster import ai_setup, ai_messages
from commitmaster.config import load_config, get_manager


class _FakeResp:
    def __init__(self, data=None, lines=None, status=200):
        self._data, self._lines, self.status_code = data, lines or [], status

    def json(self):
        return self._data

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestAiSetup(unittest.TestCase):
    def setUp(self):
        cfg = load_config()
        cfg["setup_completed"] = False
        cfg["ai"].update({"ai_mode": "", "fallback_provider": "", "provider": "bionic", "model": ""})
        get_manager().save(cfg)

    def test_first_run_flag_and_skip(self):
        self.assertTrue(ai_setup.needs_first_run_setup())
        ai_setup.mark_setup_skipped()
        self.assertFalse(ai_setup.needs_first_run_setup())

    def test_apply_local_ollama(self):
        cfg = ai_setup.apply_setup({"mode": "local", "runtime": "ollama", "model": "qwen2.5-coder:7b"})
        ai = cfg["ai"]
        self.assertEqual(ai["provider"], "ollama")
        self.assertEqual(ai["base_url"], "http://localhost:11434/v1")
        self.assertEqual(ai["model"], "qwen2.5-coder:7b")
        self.assertEqual(ai["local_port"], 11434)
        self.assertTrue(load_config()["setup_completed"])

    def test_apply_local_lmstudio_and_api(self):
        ai_setup.apply_setup({"mode": "both", "runtime": "lmstudio", "model": "m",
                              "api_provider": "gemini", "api_key": "KEY123"})
        ai = load_config()["ai"]
        self.assertEqual(ai["provider"], "bionic")
        self.assertEqual(ai["base_url"], "http://localhost:1234/v1")
        self.assertEqual(ai["fallback_provider"], "gemini")
        self.assertEqual(ai["gemini_api_key"], "KEY123")
        # API key must not be copied into the plain 'ai_setup' summary
        self.assertNotIn("KEY123", json.dumps(load_config()["ai_setup"]))

    def test_apply_api_only(self):
        ai_setup.apply_setup({"mode": "api", "api_provider": "openai", "api_key": "sk-x"})
        ai = load_config()["ai"]
        self.assertEqual(ai["provider"], "openai")
        self.assertEqual(ai["openai_api_key"], "sk-x")

    def test_both_mode_falls_back_to_cloud(self):
        ai_setup.apply_setup({"mode": "both", "runtime": "ollama", "model": "llama3.2:3b",
                              "api_provider": "openai", "api_key": "sk-x"})
        cfg = load_config()
        fb = ai_messages._fallback_cfg(cfg)
        self.assertEqual(fb["ai"]["provider"], "openai")
        self.assertEqual(fb["ai"]["model"], "")
        calls = []

        def fake_primary(c, model, system, user, max_tokens):
            calls.append(c["ai"]["provider"])
            if c["ai"]["provider"] == "ollama":
                raise ai_messages._AIUnavailable("down")
            return {"ok": 1}

        with mock.patch.object(ai_messages, "_chat_json_primary", fake_primary):
            self.assertEqual(ai_messages._chat_json(cfg, "", "s", "u", 10), {"ok": 1})
        self.assertEqual(calls, ["ollama", "openai"])

    def test_local_only_has_no_fallback(self):
        ai_setup.apply_setup({"mode": "local", "runtime": "ollama", "model": "x"})
        self.assertIsNone(ai_messages._fallback_cfg(load_config()))

    def test_auto_configure_fills_model_and_port(self):
        ai_setup.apply_setup({"mode": "local", "runtime": "ollama", "model": ""})
        with mock.patch.object(ai_setup, "server_up", return_value=True), \
             mock.patch.object(ai_setup, "list_local_models", return_value=["qwen2.5-coder:7b"]):
            ai_setup.auto_configure()
        self.assertEqual(load_config()["ai"]["model"], "qwen2.5-coder:7b")

    def test_auto_configure_noop_for_api_mode(self):
        ai_setup.apply_setup({"mode": "api", "api_provider": "openai", "api_key": "k"})
        self.assertIsNone(ai_setup.auto_configure())

    def test_pull_ollama_progress(self):
        lines = [json.dumps({"status": "pulling", "total": 100, "completed": 40}).encode(),
                 json.dumps({"status": "success"}).encode()]
        seen = []
        with mock.patch.object(ai_setup.requests, "post", return_value=_FakeResp(lines=lines)):
            ai_setup.pull_ollama_model("x:1", progress=lambda d, t, s: seen.append((d, t)))
        self.assertIn((40, 100), seen)

    def test_pull_ollama_error(self):
        lines = [json.dumps({"error": "nope"}).encode()]
        with mock.patch.object(ai_setup.requests, "post", return_value=_FakeResp(lines=lines)):
            with self.assertRaises(ai_setup.SetupError):
                ai_setup.pull_ollama_model("x:1")

    def test_resolve_hf_gguf_skips_split_files(self):
        data = {"siblings": [{"rfilename": "m-Q4_K_M-00001-of-00002.gguf", "size": 1},
                             {"rfilename": "m-Q8_0.gguf", "size": 2},
                             {"rfilename": "m-Q4_K_M.gguf", "size": 3}]}
        with mock.patch.object(ai_setup.requests, "get", return_value=_FakeResp(data=data)):
            self.assertEqual(ai_setup.resolve_hf_gguf("a/b"), ("m-Q4_K_M.gguf", 3))

    def test_match_model_and_recommendation(self):
        self.assertEqual(ai_setup.match_model("Qwen2.5-Coder-7B-Instruct-Q4_K_M",
                                              ["foo", "qwen2.5-coder-7b-instruct"]),
                         "qwen2.5-coder-7b-instruct")
        self.assertEqual(ai_setup.recommended_model_id(8), "qwen-coder-3b")
        self.assertEqual(ai_setup.recommended_model_id(32), "qwen-coder-7b")

    def test_install_skipped_when_present(self):
        with mock.patch.object(ai_setup, "find_ollama", return_value="C:/o.exe"):
            self.assertEqual(ai_setup.install_runtime("ollama"), "C:/o.exe")


class TestWizardPages(unittest.TestCase):
    def test_wizard_flow_pages_build(self):
        import tkinter as tk
        from commitmaster.setup_wizard import SetupWizard
        try:
            w = SetupWizard()
        except tk.TclError:
            self.skipTest("no display")
        try:
            w.mode.set("both")
            self.assertEqual(w._sequence(), ["mode", "runtime", "model", "api", "install", "done"])
            for page in ("mode", "runtime", "model", "api"):
                w._show(page)
            w.api_key.set("")
            w._page = "api"
            self.assertFalse(w._validate())
            w.api_key.set("k")
            self.assertTrue(w._validate())
            w.mode.set("api")
            self.assertEqual(w._sequence(), ["mode", "api", "install", "done"])
            w.mode.set("local")
            self.assertEqual(w._sequence(), ["mode", "runtime", "model", "install", "done"])
        finally:
            w.root.destroy()


if __name__ == "__main__":
    unittest.main()
