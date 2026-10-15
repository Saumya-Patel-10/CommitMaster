"""
CommitMaster — AI environment setup (first-run wizard backend).
================================================================
Detects Ollama / LM Studio, installs them when missing, downloads the model the
user picked, starts the local server, and writes every AI setting (provider,
host, port, base URL, model, API keys) into config.json so nothing has to be
filled in manually.

All network/installer steps report progress through callbacks so a GUI can
show them, and honour a `cancel` threading.Event.
"""
import ctypes
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

import requests

from commitmaster.logger import get

log = get("ai_setup")

OLLAMA = "ollama"
LMSTUDIO = "lmstudio"
DEFAULT_HOST = "localhost"
DEFAULT_PORTS = {OLLAMA: 11434, LMSTUDIO: 1234}
RUNTIME_LABELS = {OLLAMA: "Ollama", LMSTUDIO: "LM Studio"}

_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# progress_cb(done_bytes, total_bytes, text) ; status_cb(text)
ProgressCb = Callable[[int, int, str], None]
StatusCb = Callable[[str], None]


class SetupCancelled(Exception):
    pass


class SetupError(Exception):
    pass


# ── Model catalog ─────────────────────────────────────────────────────────────
# ollama = tag for `ollama pull`; hf_repo = GGUF repo used for LM Studio downloads.

MODEL_CATALOG: List[Dict] = [
    dict(id="qwen-coder-3b", label="Qwen2.5-Coder 3B", size_gb=1.9, min_ram_gb=6,
         desc="Small & fast. Good for older / low-memory PCs.",
         ollama="qwen2.5-coder:3b", hf_repo="bartowski/Qwen2.5-Coder-3B-Instruct-GGUF"),
    dict(id="llama32-3b", label="Llama 3.2 3B", size_gb=2.0, min_ram_gb=6,
         desc="Small general-purpose model.",
         ollama="llama3.2:3b", hf_repo="bartowski/Llama-3.2-3B-Instruct-GGUF"),
    dict(id="phi35", label="Phi-3.5 Mini", size_gb=2.4, min_ram_gb=8,
         desc="Compact model with strong reasoning for its size.",
         ollama="phi3.5", hf_repo="bartowski/Phi-3.5-mini-instruct-GGUF"),
    dict(id="qwen-coder-7b", label="Qwen2.5-Coder 7B", size_gb=4.7, min_ram_gb=12,
         desc="Best balance of quality and speed for commit messages.",
         ollama="qwen2.5-coder:7b", hf_repo="bartowski/Qwen2.5-Coder-7B-Instruct-GGUF"),
    dict(id="gemma2-9b", label="Gemma 2 9B", size_gb=5.8, min_ram_gb=16,
         desc="Higher quality writing; needs more memory.",
         ollama="gemma2:9b", hf_repo="bartowski/gemma-2-9b-it-GGUF"),
    dict(id="qwen-coder-14b", label="Qwen2.5-Coder 14B", size_gb=9.0, min_ram_gb=24,
         desc="Highest quality; needs a powerful PC (24 GB+ RAM).",
         ollama="qwen2.5-coder:14b", hf_repo="bartowski/Qwen2.5-Coder-14B-Instruct-GGUF"),
]


def system_ram_gb() -> float:
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        pass
    try:
        class _MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        ms = _MS()
        ms.dwLength = ctypes.sizeof(_MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
        return ms.ullTotalPhys / (1024 ** 3)
    except Exception:
        return 8.0


def recommended_model_id(ram_gb: Optional[float] = None) -> str:
    """Largest 'sweet-spot' model the PC can comfortably run (never auto-picks 9B/14B)."""
    ram = system_ram_gb() if ram_gb is None else ram_gb
    if ram >= 12:
        return "qwen-coder-7b"
    return "qwen-coder-3b"


def get_model(model_id: str) -> Optional[Dict]:
    return next((m for m in MODEL_CATALOG if m["id"] == model_id), None)


# ── Detection ─────────────────────────────────────────────────────────────────

def _first_existing(paths: List[str]) -> Optional[str]:
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def find_ollama() -> Optional[str]:
    exe = shutil.which("ollama")
    if exe:
        return exe
    local = os.environ.get("LOCALAPPDATA", "")
    return _first_existing([
        os.path.join(local, "Programs", "Ollama", "ollama.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Ollama", "ollama.exe"),
    ])


def find_lmstudio_app() -> Optional[str]:
    local = os.environ.get("LOCALAPPDATA", "")
    return _first_existing([
        os.path.join(local, "Programs", "LM Studio", "LM Studio.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "LM Studio", "LM Studio.exe"),
    ])


def find_lms_cli() -> Optional[str]:
    exe = shutil.which("lms")
    if exe:
        return exe
    return _first_existing([os.path.join(os.path.expanduser("~"), ".lmstudio", "bin", "lms.exe"),
                            os.path.join(os.path.expanduser("~"), ".cache", "lm-studio", "bin", "lms.exe")])


def detect_installed() -> Dict[str, Optional[str]]:
    """{'ollama': path|None, 'lmstudio': path|None}"""
    return {OLLAMA: find_ollama(), LMSTUDIO: find_lmstudio_app() or find_lms_cli()}


def resolve_port(runtime: str, port: int = 0) -> int:
    return int(port) if port else DEFAULT_PORTS[runtime]


def api_root(runtime: str, host: str = DEFAULT_HOST, port: int = 0) -> str:
    return f"http://{host or DEFAULT_HOST}:{resolve_port(runtime, port)}"


def openai_base_url(runtime: str, host: str = DEFAULT_HOST, port: int = 0) -> str:
    return api_root(runtime, host, port) + "/v1"


def server_up(runtime: str, host: str = DEFAULT_HOST, port: int = 0, timeout: float = 1.5) -> bool:
    path = "/api/tags" if runtime == OLLAMA else "/v1/models"
    try:
        return requests.get(api_root(runtime, host, port) + path, timeout=timeout).status_code == 200
    except Exception:
        return False


def list_local_models(runtime: str, host: str = DEFAULT_HOST, port: int = 0) -> List[str]:
    """Model names already available on a running server ([] if it is not reachable)."""
    try:
        if runtime == OLLAMA:
            r = requests.get(api_root(runtime, host, port) + "/api/tags", timeout=2)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        r = requests.get(api_root(runtime, host, port) + "/v1/models", timeout=2)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])
                if "embed" not in m["id"].lower()]
    except Exception:
        return []


# ── Helpers: download / subprocess ────────────────────────────────────────────

def _check(cancel: Optional[threading.Event]) -> None:
    if cancel is not None and cancel.is_set():
        raise SetupCancelled()


def download_file(url: str, dest: str, progress: Optional[ProgressCb] = None,
                  cancel: Optional[threading.Event] = None, label: str = "") -> str:
    """Stream `url` to `dest` (via .part file). Resumes if a partial file exists."""
    part = dest + ".part"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    have = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, stream=True, headers=headers, timeout=(15, 60), allow_redirects=True) as r:
        if r.status_code == 416:  # already complete
            os.replace(part, dest)
            return dest
        r.raise_for_status()
        if have and r.status_code != 206:
            have = 0  # server ignored Range; restart
        total = int(r.headers.get("Content-Length", 0)) + have
        done = have
        with open(part, "ab" if have else "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                _check(cancel)
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total, label)
    os.replace(part, dest)
    return dest


def _run(cmd: List[str], timeout: int = 900, cancel: Optional[threading.Event] = None) -> Tuple[int, str]:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, creationflags=_NOWIN)
    start = time.time()
    while True:
        try:
            out, _ = proc.communicate(timeout=1)
            return proc.returncode, out or ""
        except subprocess.TimeoutExpired:
            if cancel is not None and cancel.is_set():
                proc.kill()
                raise SetupCancelled()
            if time.time() - start > timeout:
                proc.kill()
                raise SetupError(f"Timed out running {os.path.basename(cmd[0])}")


def _wait_for(predicate: Callable[[], bool], seconds: float, cancel=None) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        _check(cancel)
        if predicate():
            return True
        time.sleep(1)
    return predicate()


# ── Installing runtimes ───────────────────────────────────────────────────────

OLLAMA_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
LMSTUDIO_INSTALLER_URL = "https://lmstudio.ai/download/latest/win32/x64"
WINGET_IDS = {OLLAMA: "Ollama.Ollama", LMSTUDIO: "ElementLabs.LMStudio"}
_SILENT_ARGS = {OLLAMA: ["/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"],
                LMSTUDIO: ["/S"]}


def install_runtime(runtime: str, progress: Optional[ProgressCb] = None,
                    status: Optional[StatusCb] = None,
                    cancel: Optional[threading.Event] = None) -> str:
    """Download and silently install Ollama / LM Studio. Returns the installed path."""
    say = status or (lambda s: None)
    finder = find_ollama if runtime == OLLAMA else (lambda: find_lmstudio_app() or find_lms_cli())
    name = RUNTIME_LABELS[runtime]
    if finder():
        return finder()  # type: ignore

    # 1) Direct installer download (shows real progress)
    tmp = os.path.join(tempfile.gettempdir(), f"CommitMaster_{runtime}_setup.exe")
    err = ""
    try:
        say(f"Downloading {name} installer…")
        url = OLLAMA_INSTALLER_URL if runtime == OLLAMA else LMSTUDIO_INSTALLER_URL
        download_file(url, tmp, progress, cancel, f"Downloading {name}")
        _check(cancel)
        say(f"Installing {name} (this can take a minute)…")
        code, out = _run([tmp] + _SILENT_ARGS[runtime], timeout=900, cancel=cancel)
        log.info("%s installer exit=%s %s", name, code, out[-300:])
        _wait_for(lambda: bool(finder()), 30, cancel)
    except SetupCancelled:
        raise
    except Exception as exc:
        err = str(exc)
        log.warning("Direct %s install failed: %s", name, exc)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    # 2) winget fallback
    if not finder() and shutil.which("winget"):
        say(f"Installing {name} with winget…")
        try:
            code, out = _run(["winget", "install", "-e", "--id", WINGET_IDS[runtime], "--silent",
                              "--accept-package-agreements", "--accept-source-agreements"],
                             timeout=1200, cancel=cancel)
            log.info("winget %s exit=%s %s", name, code, out[-300:])
            _wait_for(lambda: bool(finder()), 30, cancel)
        except SetupCancelled:
            raise
        except Exception as exc:
            err = err or str(exc)

    path = finder()
    if not path:
        raise SetupError(
            f"Could not install {name} automatically{(' (' + err + ')') if err else ''}.\n"
            f"Please install it from {'https://ollama.com/download' if runtime == OLLAMA else 'https://lmstudio.ai'} "
            "and press Retry."
        )
    return path


# ── Server control ────────────────────────────────────────────────────────────

def ensure_server_running(runtime: str, host: str = DEFAULT_HOST, port: int = 0,
                          status: Optional[StatusCb] = None,
                          cancel: Optional[threading.Event] = None) -> bool:
    """Start the runtime's local API server if it isn't already answering."""
    say = status or (lambda s: None)
    if server_up(runtime, host, port):
        return True
    name = RUNTIME_LABELS[runtime]
    say(f"Starting {name} server…")
    try:
        if runtime == OLLAMA:
            exe = find_ollama()
            if not exe:
                return False
            env = dict(os.environ)
            if port and int(port) != DEFAULT_PORTS[OLLAMA]:
                env["OLLAMA_HOST"] = f"127.0.0.1:{int(port)}"
            subprocess.Popen([exe, "serve"], env=env, creationflags=_NOWIN | 0x00000008,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        else:
            cli = find_lms_cli()
            if not cli:
                app = find_lmstudio_app()
                if app:
                    # First launch creates the `lms` command-line tool.
                    subprocess.Popen([app], creationflags=0x00000008,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
                    _wait_for(lambda: bool(find_lms_cli()), 90, cancel)
                    cli = find_lms_cli()
            if cli:
                cmd = [cli, "server", "start"]
                if port:
                    cmd += ["--port", str(int(port))]
                _run(cmd, timeout=60, cancel=cancel)
    except SetupCancelled:
        raise
    except Exception as exc:
        log.warning("Could not start %s server: %s", name, exc)
    return _wait_for(lambda: server_up(runtime, host, port), 45, cancel)


# ── Models ────────────────────────────────────────────────────────────────────

def pull_ollama_model(tag: str, host: str = DEFAULT_HOST, port: int = 0,
                      progress: Optional[ProgressCb] = None,
                      cancel: Optional[threading.Event] = None) -> str:
    url = api_root(OLLAMA, host, port) + "/api/pull"
    with requests.post(url, json={"name": tag, "stream": True}, stream=True, timeout=(10, 120)) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            _check(cancel)
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("error"):
                raise SetupError(f"Ollama could not download '{tag}': {d['error']}")
            if progress:
                progress(int(d.get("completed", 0)), int(d.get("total", 0)), d.get("status", ""))
    return tag


def lmstudio_models_dir() -> str:
    home = os.path.expanduser("~")
    for d in (os.path.join(home, ".lmstudio", "models"), os.path.join(home, ".cache", "lm-studio", "models")):
        if os.path.isdir(d):
            return d
    return os.path.join(home, ".lmstudio", "models")


def resolve_hf_gguf(repo: str, quant: str = "Q4_K_M") -> Tuple[str, int]:
    """Find the single-file `quant` GGUF in a Hugging Face repo → (filename, size_bytes)."""
    r = requests.get(f"https://huggingface.co/api/models/{repo}", params={"blobs": "true"}, timeout=20)
    r.raise_for_status()
    files = [s for s in r.json().get("siblings", [])
             if s["rfilename"].lower().endswith(".gguf") and quant.lower() in s["rfilename"].lower()
             and "-of-" not in s["rfilename"].lower()]
    if not files:
        raise SetupError(f"No {quant} GGUF file found in {repo}.")
    f = files[0]
    return f["rfilename"], int(f.get("size") or 0)


def download_lmstudio_model(repo: str, progress: Optional[ProgressCb] = None,
                            cancel: Optional[threading.Event] = None) -> str:
    """Download a GGUF into LM Studio's models folder. Returns the file stem (model name hint)."""
    fname, _ = resolve_hf_gguf(repo)
    publisher, name = repo.split("/", 1)
    dest = os.path.join(lmstudio_models_dir(), publisher, name, fname)
    if os.path.exists(dest):
        return os.path.splitext(fname)[0]
    url = f"https://huggingface.co/{repo}/resolve/main/{fname}"
    download_file(url, dest, progress, cancel, f"Downloading {fname}")
    return os.path.splitext(fname)[0]


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def match_model(hint: str, available: List[str]) -> str:
    """Pick the available model id that best matches a downloaded file/tag name."""
    h = _norm(hint.split(":")[0] if ":" in hint else hint)
    for m in available:
        n = _norm(m)
        if h and (h in n or n in h):
            return m
    return available[0] if available else ""


# ── Applying the configuration ────────────────────────────────────────────────

def apply_setup(choices: Dict) -> Dict:
    """
    Persist wizard results into config.json.
    choices: mode ('local'|'api'|'both'), runtime, host, port, model (name/tag),
             api_provider, api_key
    """
    from commitmaster.config import load_config, get_manager

    cfg = load_config()
    ai = cfg["ai"]
    mode = choices.get("mode", "local")
    ai["ai_mode"] = mode

    if mode in ("local", "both"):
        rt = choices.get("runtime", OLLAMA)
        host = choices.get("host") or DEFAULT_HOST
        port = resolve_port(rt, choices.get("port") or 0)
        ai["provider"] = "ollama" if rt == OLLAMA else "bionic"
        ai["local_runtime"] = rt
        ai["local_host"] = host
        ai["local_port"] = port
        ai["base_url"] = openai_base_url(rt, host, port)
        ai["model"] = choices.get("model", "") or ""
        ai["api_key"] = ""

    if mode in ("api", "both"):
        prov = choices.get("api_provider", "openai")
        key = (choices.get("api_key") or "").strip()
        ai[f"{prov}_api_key"] = key
        if mode == "api":
            ai["provider"] = prov
            ai["model"] = ""
            ai["fallback_provider"] = ""
        else:
            ai["fallback_provider"] = prov
    else:
        ai["fallback_provider"] = ""

    cfg["setup_completed"] = True
    cfg["ai_setup"] = {k: v for k, v in choices.items() if k != "api_key"}
    get_manager().save(cfg)
    return cfg


def needs_first_run_setup() -> bool:
    from commitmaster.config import load_config
    return not load_config().get("setup_completed", False)


def mark_setup_skipped() -> None:
    from commitmaster.config import load_config, get_manager
    cfg = load_config()
    cfg["setup_completed"] = True
    cfg["ai_setup"] = {"mode": "skipped"}
    get_manager().save(cfg)


def auto_configure(status: Optional[StatusCb] = None) -> Optional[Dict]:
    """
    Run after the user signs in: make sure the local AI server is running and that
    host / port / base URL / model in config.json match what is really there.
    Safe to call repeatedly; does nothing when local AI isn't in use.
    """
    from commitmaster.config import load_config, get_manager

    cfg = load_config()
    ai = cfg["ai"]
    if ai.get("ai_mode") not in ("local", "both"):
        return None
    rt = ai.get("local_runtime") or (OLLAMA if ai.get("provider") == "ollama" else LMSTUDIO)
    host = ai.get("local_host") or DEFAULT_HOST
    port = resolve_port(rt, ai.get("local_port") or 0)

    if not server_up(rt, host, port):
        # The runtime may be listening on its other/default port.
        if port != DEFAULT_PORTS[rt] and server_up(rt, host, DEFAULT_PORTS[rt]):
            port = DEFAULT_PORTS[rt]
        else:
            ensure_server_running(rt, host, port, status)

    changed = False
    if server_up(rt, host, port):
        models = list_local_models(rt, host, port)
        current = (ai.get("model") or "").strip()
        if models and (not current or (current not in models and rt == LMSTUDIO)):
            hint = (cfg.get("ai_setup") or {}).get("model") or current
            ai["model"] = match_model(hint, models) if hint else models[0]
            changed = True
        elif models and rt == OLLAMA and current not in models:
            alt = [m for m in models if m.split(":")[0] == current.split(":")[0]]
            ai["model"] = alt[0] if alt else models[0]
            changed = True
    new_url = openai_base_url(rt, host, port)
    if ai.get("base_url") != new_url or ai.get("local_port") != port:
        ai["base_url"] = new_url
        ai["local_port"] = port
        changed = True
    if changed:
        get_manager().save(cfg)
        log.info("AI settings auto-configured: %s @ %s model=%s", rt, new_url, ai.get("model"))
    return cfg


def run_local_setup(choices: Dict, progress: Optional[ProgressCb] = None,
                    status: Optional[StatusCb] = None,
                    cancel: Optional[threading.Event] = None) -> Dict:
    """
    Full local pipeline used by the wizard:
    install runtime if needed → start server → download model → write config.
    Returns the updated choices (with the resolved model name).
    """
    say = status or (lambda s: None)
    rt = choices["runtime"]
    host = choices.get("host") or DEFAULT_HOST
    port = resolve_port(rt, choices.get("port") or 0)
    model = get_model(choices.get("model_id", "")) if choices.get("model_id") else None

    if rt == OLLAMA and not find_ollama():
        install_runtime(OLLAMA, progress, say, cancel)
    elif rt == LMSTUDIO and not (find_lmstudio_app() or find_lms_cli()):
        install_runtime(LMSTUDIO, progress, say, cancel)

    resolved = choices.get("existing_model", "")
    if model:
        if rt == OLLAMA:
            if not ensure_server_running(OLLAMA, host, port, say, cancel):
                raise SetupError("Ollama is installed but its server did not start. "
                                 "Open the Ollama app once and press Retry.")
            say(f"Downloading model {model['label']} ({model['size_gb']} GB)…")
            pull_ollama_model(model["ollama"], host, port, progress, cancel)
            resolved = model["ollama"]
        else:
            say(f"Downloading model {model['label']} ({model['size_gb']} GB)…")
            resolved = download_lmstudio_model(model["hf_repo"], progress, cancel)
            ensure_server_running(LMSTUDIO, host, port, say, cancel)
            models = list_local_models(LMSTUDIO, host, port)
            if models:
                resolved = match_model(resolved, models)
    else:
        ensure_server_running(rt, host, port, say, cancel)

    out = dict(choices)
    out["model"] = resolved
    return out
