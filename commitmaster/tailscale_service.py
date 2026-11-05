"""
CommitMaster — Tailscale Mesh Networking & Identity Service.
============================================================
Provides zero-config peer discovery, local node status detection, MagicDNS
resolution, Tailscale Whois identity verification, and AI compute node discovery
across the developer's private Tailnet.
"""
import json
import os
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from commitmaster.logger import get

log = get("tailscale_service")

# Standard Windows installation paths for Tailscale
_STANDARD_WINDOWS_PATHS = [
    r"C:\Program Files\Tailscale\tailscale.exe",
    r"C:\Program Files (x86)\Tailscale\tailscale.exe",
]

_STATUS_CACHE: Optional[Dict[str, Any]] = None
_STATUS_CACHE_TIME: float = 0.0
_CACHE_TTL_SECONDS: float = 15.0


def _subprocess_kwargs() -> dict:
    """Return subprocess kwargs to run commands silently without console flash."""
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = si
    return kwargs


def get_tailscale_binary() -> Optional[str]:
    """Find the path to the tailscale executable on the system."""
    # 1. Check PATH
    bin_in_path = shutil.which("tailscale")
    if bin_in_path:
        return bin_in_path

    # 2. Check standard Windows directories
    for path in _STANDARD_WINDOWS_PATHS:
        if os.path.exists(path):
            return path

    # 3. Check LocalAppData Programs
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        candidate = os.path.join(local_app_data, "Programs", "Tailscale", "tailscale.exe")
        if os.path.exists(candidate):
            return candidate

    return None


def is_tailscale_installed() -> bool:
    """Return True if Tailscale CLI binary is found on this machine."""
    return get_tailscale_binary() is not None


def get_tailscale_status(force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """
    Execute 'tailscale status --json' and return the parsed JSON dictionary.
    Cached for _CACHE_TTL_SECONDS to avoid thrashing subprocesses.
    """
    global _STATUS_CACHE, _STATUS_CACHE_TIME

    now = time.time()
    if not force_refresh and _STATUS_CACHE is not None and (now - _STATUS_CACHE_TIME) < _CACHE_TTL_SECONDS:
        return _STATUS_CACHE

    binary = get_tailscale_binary()
    if not binary:
        return None

    try:
        proc = subprocess.run(
            [binary, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
            **_subprocess_kwargs(),
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            _STATUS_CACHE = data
            _STATUS_CACHE_TIME = now
            return data
    except Exception as exc:
        log.debug("Tailscale status command failed: %s", exc)

    return None


def get_tailscale_ip() -> Optional[str]:
    """Return the IPv4 Tailscale address (100.x.y.z) of this device, or None."""
    status = get_tailscale_status()
    if status and "Self" in status:
        tailscale_ips = status["Self"].get("TailscaleIPs", [])
        for ip in tailscale_ips:
            if "." in ip and ip.startswith("100."):
                return ip

    # Fallback: directly run 'tailscale ip -4'
    binary = get_tailscale_binary()
    if binary:
        try:
            proc = subprocess.run(
                [binary, "ip", "-4"],
                capture_output=True,
                text=True,
                timeout=4,
                **_subprocess_kwargs(),
            )
            if proc.returncode == 0:
                ip = proc.stdout.strip().splitlines()[0].strip()
                if ip.startswith("100."):
                    return ip
        except Exception:
            pass
    return None


def is_tailnet_connected() -> bool:
    """Return True if this device is authenticated and online on its Tailnet."""
    status = get_tailscale_status()
    if status and "Self" in status:
        return bool(status["Self"].get("Online", False))
    return get_tailscale_ip() is not None


def get_magic_dns_name() -> Optional[str]:
    """Return the MagicDNS fully qualified domain name (e.g. saumya-pc.tailnet.ts.net)."""
    status = get_tailscale_status()
    if status and "Self" in status:
        dns_name = status["Self"].get("DNSName", "").rstrip(".")
        if dns_name:
            return dns_name
    return None


def get_device_hostname() -> str:
    """Return this node's hostname as reported by Tailscale (or local hostname fallback)."""
    status = get_tailscale_status()
    if status and "Self" in status:
        name = status["Self"].get("HostName", "")
        if name:
            return name
    return os.getenv("COMPUTERNAME", "localhost")


def get_tailnet_user() -> Optional[Dict[str, Any]]:
    """Return the current signed-in Tailnet user profile from status JSON."""
    status = get_tailscale_status()
    if not status:
        return None

    # Status contains User map: { "<id>": { "LoginName": "...", "DisplayName": "..." } }
    users = status.get("User", {})
    self_node = status.get("Self", {})
    user_id = str(self_node.get("UserID", ""))

    if user_id and user_id in users:
        return users[user_id]
    elif users:
        # First user in map
        return next(iter(users.values()))
    return None


def get_tailnet_peers() -> List[Dict[str, Any]]:
    """
    Return a normalized list of all other active nodes/peers on the Tailnet.
    Format:
      [
        {
          "hostname": "saumya-laptop",
          "ip": "100.108.102.82",
          "dns_name": "saumya-laptop.tailnet.ts.net",
          "os": "windows",
          "online": True,
          "last_seen": "2026-11-03T20:30:00Z"
        }, ...
      ]
    """
    status = get_tailscale_status()
    if not status or "Peer" not in status:
        return []

    peers: List[Dict[str, Any]] = []
    for peer_key, peer_info in status["Peer"].items():
        ips = peer_info.get("TailscaleIPs", [])
        ipv4 = next((ip for ip in ips if "." in ip and ip.startswith("100.")), "")
        peers.append({
            "hostname": peer_info.get("HostName", "Unknown"),
            "ip": ipv4,
            "dns_name": peer_info.get("DNSName", "").rstrip("."),
            "os": peer_info.get("OS", "unknown"),
            "online": bool(peer_info.get("Online", False)),
            "last_seen": peer_info.get("LastSeen", ""),
            "cur_addr": peer_info.get("CurAddr", ""),
            "rx_bytes": peer_info.get("RxBytes", 0),
            "tx_bytes": peer_info.get("TxBytes", 0),
        })

    # Sort online peers first, then alphabetically by hostname
    peers.sort(key=lambda p: (not p["online"], p["hostname"].lower()))
    return peers


def whois(client_ip: str) -> Optional[Dict[str, Any]]:
    """
    Query Tailscale Whois for an incoming client IP address.
    Returns:
      {
        "login_name": "user@example.com",
        "display_name": "User Name",
        "hostname": "client-laptop",
        "os": "windows"
      }
    """
    if not client_ip or not client_ip.startswith("100."):
        return None

    binary = get_tailscale_binary()
    if not binary:
        return None

    try:
        proc = subprocess.run(
            [binary, "whois", "--json", client_ip],
            capture_output=True,
            text=True,
            timeout=4,
            **_subprocess_kwargs(),
        )
        if proc.returncode == 0 and proc.stdout.strip():
            raw = json.loads(proc.stdout)
            user_profile = raw.get("UserProfile", {})
            node = raw.get("Node", {})
            return {
                "login_name": user_profile.get("LoginName", ""),
                "display_name": user_profile.get("DisplayName", ""),
                "hostname": node.get("HostName", ""),
                "os": node.get("OS", ""),
                "node_id": node.get("ID", ""),
            }
    except Exception as exc:
        log.debug("Tailscale whois query failed for %s: %s", client_ip, exc)

    # Fallback to local status peers if whois fails (e.g. pipe permissions)
    peers = get_tailnet_peers()
    for p in peers:
        if p["ip"] == client_ip:
            return {
                "login_name": "",
                "display_name": p["hostname"],
                "hostname": p["hostname"],
                "os": p["os"],
                "node_id": "",
            }
    return None


def probe_tailnet_hub(peer_ip_or_host: str, port: int = 8000, timeout: float = 1.5) -> Optional[Dict[str, Any]]:
    """Check if a CommitMaster server is listening on a peer node."""
    import requests
    url = f"http://{peer_ip_or_host}:{port}/api/health"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("service") == "CommitMaster-Server":
                return {
                    "url": f"http://{peer_ip_or_host}:{port}",
                    "version": data.get("version"),
                    "status": "online",
                    "latency_ms": int(resp.elapsed.total_seconds() * 1000),
                }
    except Exception:
        pass
    return None


def probe_tailnet_ai_node(peer_ip_or_host: str, runtime: str = "ollama", timeout: float = 1.5) -> Optional[Dict[str, Any]]:
    """Check if Ollama (11434) or LM Studio (1234) is reachable on a peer node."""
    import requests
    port = 11434 if runtime == "ollama" else 1234
    endpoint = f"http://{peer_ip_or_host}:{port}/v1/models"
    try:
        start = time.time()
        resp = requests.get(endpoint, timeout=timeout)
        elapsed_ms = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            models_data = resp.json()
            model_ids = [m.get("id") for m in models_data.get("data", []) if isinstance(m, dict) and "id" in m]
            return {
                "base_url": f"http://{peer_ip_or_host}:{port}/v1",
                "runtime": runtime,
                "models": model_ids,
                "latency_ms": elapsed_ms,
            }
    except Exception:
        pass
    return None


def discover_tailnet_ai_nodes() -> List[Dict[str, Any]]:
    """Scan all active Tailnet peers for listening Ollama or LM Studio endpoints."""
    nodes: List[Dict[str, Any]] = []

    # First check localhost
    for rt in ("ollama", "lm_studio"):
        info = probe_tailnet_ai_node("127.0.0.1", runtime=rt, timeout=0.8)
        if info:
            info["host"] = "localhost (This PC)"
            nodes.append(info)

    # Then check all online Tailnet peers
    peers = get_tailnet_peers()
    for peer in peers:
        if not peer.get("online") or not peer.get("ip"):
            continue
        peer_ip = peer["ip"]
        for rt in ("ollama", "lm_studio"):
            info = probe_tailnet_ai_node(peer_ip, runtime=rt, timeout=1.2)
            if info:
                info["host"] = f"{peer['hostname']} ({peer_ip})"
                nodes.append(info)

    return nodes

