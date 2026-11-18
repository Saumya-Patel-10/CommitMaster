"""
CommitMaster — Accessibility, display preferences, and performance tier detection.

Detects Windows reduced-motion preferences (SPI_GETCLIENTAREAANIMATION),
battery state, system RAM, and GPU capability to automatically classify
rendering performance tier ('high', 'medium', 'low') and provide user overrides.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from typing import Any, Dict, Optional

from commitmaster.logger import get

log = get("accessibility")

# Windows API Constants
SPI_GETCLIENTAREAANIMATION = 0x1042


def detect_reduced_motion() -> bool:
    """
    Check if the user has disabled animations in Windows Settings
    (Accessibility -> Visual effects -> Animation effects).
    Returns True if reduced motion is requested (animations are disabled).
    """
    if sys.platform != "win32":
        return False

    try:
        enabled = ctypes.c_int(1)
        res = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION,
            0,
            ctypes.byref(enabled),
            0,
        )
        if res:
            # If enabled.value == 0, animations are turned off in Windows -> reduced motion is requested
            return enabled.value == 0
    except Exception as exc:
        log.debug("Failed to query SPI_GETCLIENTAREAANIMATION: %s", exc)

    return False


def detect_battery_saver() -> bool:
    """
    Check if the system is currently running on battery and battery saver is active.
    """
    if sys.platform != "win32":
        return False

    try:
        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_byte),
                ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte),
                ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong),
            ]

        status = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            # SystemStatusFlag == 1 indicates Battery Saver is active
            # ACLineStatus == 0 indicates offline (on battery)
            is_on_battery = status.ACLineStatus == 0
            is_battery_saver = status.SystemStatusFlag == 1
            return is_on_battery or is_battery_saver
    except Exception as exc:
        log.debug("Failed to query GetSystemPowerStatus: %s", exc)

    return False


def detect_gpu_info() -> Dict[str, str]:
    """
    Query system video controllers to identify GPU type.
    Returns: {"name": str, "type": "integrated" | "dedicated" | "unknown"}
    """
    info = {"name": "Unknown", "type": "unknown"}
    if sys.platform != "win32":
        return info

    try:
        cmd = ["wmic", "path", "win32_VideoController", "get", "name"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip() and line.strip().lower() != "name"]
        if lines:
            gpu_name = lines[0]
            info["name"] = gpu_name
            lower = gpu_name.lower()
            if any(k in lower for k in ("nvidia", "geforce", "rtx", "gtx", "radeon rx", "arc")):
                info["type"] = "dedicated"
            elif any(k in lower for k in ("intel", "uhd", "iris", "hd graphics", "vega", "radeon graphics")):
                info["type"] = "integrated"
    except Exception as exc:
        log.debug("GPU detection query failed: %s", exc)

    return info


def classify_performance_tier() -> str:
    """
    Determine the visual performance tier: 'high', 'medium', or 'low'.
    - 'low': Battery saver active, < 4GB total RAM, or low-spec environment.
    - 'medium': Integrated GPU, or 4GB - 8GB RAM.
    - 'high': Dedicated GPU, >= 8GB RAM, and AC power.
    """
    if detect_battery_saver():
        return "low"

    total_ram_gb = 8.0
    try:
        import psutil
        total_ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        pass

    if total_ram_gb < 4.5:
        return "low"

    gpu = detect_gpu_info()
    if gpu.get("type") == "integrated" or total_ram_gb < 8.0:
        return "medium"

    return "high"


def get_accessibility_state(user_prefs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Assemble the complete accessibility and performance state.
    User preferences explicitly override OS detections if set.
    """
    prefs = user_prefs or {}

    # Reduced motion override or auto-detect
    if "reduced_motion" in prefs:
        reduced_motion = bool(prefs["reduced_motion"])
    else:
        reduced_motion = detect_reduced_motion()

    # Performance tier override or auto-detect
    if prefs.get("performance_tier") in ("high", "medium", "low"):
        perf_tier = prefs["performance_tier"]
    else:
        perf_tier = classify_performance_tier()

    # 3D enabled toggle (defaults to True unless in low-resource mode or explicit False)
    low_resource_mode = bool(prefs.get("low_resource_mode", False))
    enable_3d = bool(prefs.get("enable_3d", True)) and not low_resource_mode

    return {
        "reduced_motion": reduced_motion,
        "performance_tier": perf_tier,
        "3d_enabled": enable_3d,
        "low_resource_mode": low_resource_mode,
        "gpu": detect_gpu_info(),
    }
