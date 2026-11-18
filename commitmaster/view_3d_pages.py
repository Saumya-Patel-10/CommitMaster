"""
CommitMaster — Native Desktop 3D Visualization Pages.

Provides rich page renderers for the Windows desktop applications (User, Admin, Demo)
and manages native hardware-accelerated 3D viewports directly on the Windows desktop.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Dict, Optional

from commitmaster import accessibility, scene_data, webview_host
from commitmaster.app_styles import COLORS, FONTS
from commitmaster.logger import get

log = get("view_3d_pages")

_active_3d_windows: Dict[str, Any] = {}


def open_native_3d_viewport(scene_name: str, repo_path: Optional[str] = None) -> None:
    """
    Launch a native desktop 3D window for the given visualization scene.
    Runs on a dedicated background thread to keep the Tkinter UI perfectly responsive.
    """
    def _run():
        try:
            import webview

            dist_path = webview_host.get_web_dist_path()
            file_url = f"file:///{os.path.abspath(dist_path).replace(os.sep, '/')}#{scene_name}"

            title = f"CommitMaster 3D — {scene_name.replace('_', ' ').title()}"

            win = webview.create_window(
                title=title,
                url=file_url,
                width=1280,
                height=820,
                background_color="#0a0e17",
                text_select=False,
            )
            _active_3d_windows[scene_name] = win
            webview.start()
        except Exception as exc:
            log.error("Failed to launch native 3D viewport for '%s': %s", scene_name, exc)

    t = threading.Thread(target=_run, daemon=True, name=f"3D-Viewport-{scene_name}")
    t.start()


def _get_parent(dashboard) -> tk.Frame:
    return getattr(dashboard, "_cf", None) or getattr(dashboard, "_content_frame", None)


# ── Page Builders for User App ────────────────────────────────────────────────

def render_3d_hub_page(dashboard) -> None:
    """Render the 3D Animated Specialist Hub overview."""
    parent = _get_parent(dashboard)

    def _actions(row):
        btn = tk.Button(
            row,
            text="✨ Launch 3D Animated Hub",
            font=FONTS["label_bold"],
            bg=COLORS["accent"],
            fg=COLORS["bg_darkest"],
            activebackground=COLORS["accent_hover"],
            activeforeground=COLORS["bg_darkest"],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=16,
            pady=7,
            command=lambda: open_native_3d_viewport("hub"),
        )
        btn.pack(side="right", padx=(0, 4))

    dashboard._create_page_header_panel(
        parent,
        title="3D Specialist Hub",
        subtitle="Seven AI specialists orbit the core. Each with its own memory, expertise, and 3D output format.",
        icon="✨",
        actions_fn=_actions,
    )

    # Hero Banner with launch button
    hero_card = dashboard._card(parent)
    hero_card.pack(fill="x", pady=(0, 16))
    tk.Frame(hero_card, height=3, bg=COLORS["accent"]).pack(fill="x")
    inner = tk.Frame(hero_card, bg=COLORS["bg_card"], padx=24, pady=22)
    inner.pack(fill="both")

    tk.Label(inner, text="Pick the specialist, not the chatbot.", font=FONTS["heading_lg"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
    tk.Label(inner, text="Seven interactive 3D agents orbit the CommitMaster core. Each specialist runs in 60 FPS 3D space with dedicated memory, AST inspection, and conventional formatters.", font=FONTS["body_md"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"], wraplength=720).pack(anchor="w", pady=(6, 16))

    btn_f = tk.Frame(inner, bg=COLORS["bg_card"])
    btn_f.pack(anchor="w")

    launch_btn = tk.Button(
        btn_f,
        text="  🚀 Launch Full 3D Animated Specialist Hub  ",
        font=FONTS["heading_sm"],
        bg=COLORS["accent"],
        fg=COLORS["bg_darkest"],
        activebackground=COLORS["accent_hover"],
        activeforeground=COLORS["bg_darkest"],
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=22,
        pady=12,
        command=lambda: open_native_3d_viewport("hub"),
    )
    launch_btn.pack(side="left")

    # Grid of the 7 Specialists
    dashboard._section_title(parent, "7 Active Specialists Orbiting Core")
    grid = tk.Frame(parent, bg=COLORS["bg_dark"])
    grid.pack(fill="x", pady=(0, 16))

    specialists = [
        ("AGENT 04", "Debugger & Git Galaxy", "#eab308", "commit_galaxy", "Visualizes branches, commits, and merge spirals in 3D space."),
        ("AGENT 03", "Code Reviewer", "#00e5ff", "architecture", "Reviews your diff like a staff engineer, AST syntax & symbols."),
        ("AGENT 02", "Security Inspector", "#f85149", "security_map", "Finds leaked keys, CWE-798 secrets, and risky changes."),
        ("AGENT 01", "Commit Drafter", "#3fb950", "diff_comparator", "Turns your diff into clean Conventional Commits."),
        ("AGENT 05", "Productivity & Health", "#a855f7", "health_globe", "Reads your sessions, maps technical debt in 3D."),
        ("AGENT 06", "Analytics Analyst", "#38bdf8", "analytics", "Turns commit history into an interactive 3D story."),
        ("AGENT 07", "Feature & Mesh Topology", "#ec4899", "device_topology", "Monitors connected Tailscale devices and mesh status."),
    ]

    for tag, name, col, scene, desc in specialists:
        card = dashboard._card(grid)
        card.pack(fill="x", pady=4)
        tk.Frame(card, width=4, bg=col).pack(side="left", fill="y")
        c_inner = tk.Frame(card, bg=COLORS["bg_card"], padx=14, pady=10)
        c_inner.pack(side="left", fill="both", expand=True)
        top = tk.Frame(c_inner, bg=COLORS["bg_card"])
        top.pack(fill="x")
        tk.Label(top, text=f"{tag} · {name}", font=FONTS["label_bold"], fg=col, bg=COLORS["bg_card"]).pack(side="left")
        tk.Button(top, text="OPEN 3D →", font=FONTS["caption"], bg=COLORS["bg_medium"], fg=col, relief="flat", bd=0, cursor="hand2", padx=10, pady=3, command=lambda s=scene: open_native_3d_viewport(s)).pack(side="right")
        tk.Label(c_inner, text=desc, font=FONTS["caption"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(2, 0))


def render_3d_galaxy_page(dashboard) -> None:
    """Render 3D Git Commit Galaxy view inside User Dashboard."""
    parent = _get_parent(dashboard)
    repo_path = getattr(dashboard, "_gd_selected_repo", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 1. Header Banner
    def _actions(row):
        btn = tk.Button(
            row,
            text="🌌 Open 3D Viewport",
            font=FONTS["label_bold"],
            bg=COLORS["accent"],
            fg=COLORS["bg_darkest"],
            activebackground=COLORS["accent_hover"],
            activeforeground=COLORS["bg_darkest"],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=14,
            pady=6,
            command=lambda: open_native_3d_viewport("commit_galaxy", repo_path),
        )
        btn.pack(side="right", padx=(0, 4))

    dashboard._create_page_header_panel(
        parent,
        title="3D Git Commit Galaxy",
        subtitle="Interactive 3D galaxy visualization of Git repositories, branches, and merges.",
        icon="🌌",
        actions_fn=_actions,
    )

    # 2. Extract Data
    galaxy_data = scene_data.build_commit_galaxy_data(repo_path, max_commits=200)
    summary = galaxy_data.get("summary", {})
    nodes = galaxy_data.get("nodes", [])
    branches = galaxy_data.get("branches", [])

    # 3. Top Metrics Row
    stats_row = tk.Frame(parent, bg=COLORS["bg_dark"])
    stats_row.pack(fill="x", pady=(0, 14))

    dashboard._stat_card(stats_row, "TOTAL COMMITS", str(summary.get("totalCommits", len(nodes))), COLORS["accent"], "🌌")
    dashboard._stat_card(stats_row, "ACTIVE BRANCHES", str(summary.get("totalBranches", len(branches))), COLORS["warning"], "🌿")
    dashboard._stat_card(stats_row, "HEAD COMMIT", str(summary.get("headHash", "HEAD")[:8]), COLORS["success"], "⚓")

    # 4. 3D Viewport Launcher Card
    hero_card = dashboard._card(parent)
    hero_card.pack(fill="x", pady=(0, 16))
    tk.Frame(hero_card, height=3, bg=COLORS["accent"]).pack(fill="x")

    inner = tk.Frame(hero_card, bg=COLORS["bg_card"], padx=20, pady=18)
    inner.pack(fill="both")

    tk.Label(
        inner,
        text="3D Hardware-Accelerated Commit Galaxy",
        font=FONTS["heading_md"],
        fg=COLORS["text_primary"],
        bg=COLORS["bg_card"],
    ).pack(anchor="w")

    tk.Label(
        inner,
        text="Rendered in native WebGL / Three.js at 60 FPS with Orbit, Pan, Zoom, and branch-raycasting. Click below to launch the dedicated 3D scene:",
        font=FONTS["body_sm"],
        fg=COLORS["text_secondary"],
        bg=COLORS["bg_card"],
        wraplength=700,
    ).pack(anchor="w", pady=(4, 14))

    btn_row = tk.Frame(inner, bg=COLORS["bg_card"])
    btn_row.pack(anchor="w")

    launch_btn = tk.Button(
        btn_row,
        text="  🌌 Launch Native 3D Commit Galaxy Window  ",
        font=FONTS["label_bold"],
        bg=COLORS["accent"],
        fg=COLORS["bg_darkest"],
        activebackground=COLORS["accent_hover"],
        activeforeground=COLORS["bg_darkest"],
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=18,
        pady=9,
        command=lambda: open_native_3d_viewport("commit_galaxy", repo_path),
    )
    launch_btn.pack(side="left")

    # 5. Commit Explorer Table
    dashboard._section_title(parent, "Recent Commits in Galaxy Topology")

    table_card = dashboard._card(parent)
    table_card.pack(fill="both", expand=True)

    tree_f = tk.Frame(table_card, bg=COLORS["bg_card"], padx=12, pady=12)
    tree_f.pack(fill="both", expand=True)

    cols = ("hash", "branch", "author", "message", "files")
    tree = ttk.Treeview(tree_f, columns=cols, show="headings", height=8)
    tree.heading("hash", text="Commit")
    tree.heading("branch", text="Branch")
    tree.heading("author", text="Author")
    tree.heading("message", text="Commit Message")
    tree.heading("files", text="Changes")

    tree.column("hash", width=90, anchor="center")
    tree.column("branch", width=120)
    tree.column("author", width=140)
    tree.column("message", width=340)
    tree.column("files", width=90, anchor="center")

    for n in nodes[:25]:
        tree.insert("", "end", values=(
            n.get("hash", ""),
            n.get("branch", "main"),
            n.get("author", ""),
            n.get("message", ""),
            f"{n.get('filesChanged', 1)} files",
        ))

    tree.pack(fill="both", expand=True)


def render_3d_architecture_page(dashboard) -> None:
    """Render 3D Codebase Architecture Explorer view inside User Dashboard."""
    parent = _get_parent(dashboard)
    repo_path = getattr(dashboard, "_gd_selected_repo", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _actions(row):
        btn = tk.Button(
            row,
            text="🏛️ Open 3D Viewport",
            font=FONTS["label_bold"],
            bg=COLORS["accent"],
            fg=COLORS["bg_darkest"],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=14,
            pady=6,
            command=lambda: open_native_3d_viewport("architecture", repo_path),
        )
        btn.pack(side="right")

    dashboard._create_page_header_panel(
        parent,
        title="3D Codebase Architecture Explorer",
        subtitle="Hierarchical 3D representation of directories, classes, functions, and dependency linkages.",
        icon="🏛️",
        actions_fn=_actions,
    )

    arch_data = scene_data.build_architecture_data(repo_path)
    metrics = arch_data.get("metrics", {})

    stats_row = tk.Frame(parent, bg=COLORS["bg_dark"])
    stats_row.pack(fill="x", pady=(0, 14))

    dashboard._stat_card(stats_row, "SOURCE FILES", str(metrics.get("totalFiles", 0)), COLORS["accent"], "📄")
    dashboard._stat_card(stats_row, "DIRECTORIES", str(metrics.get("totalDirectories", 0)), COLORS["warning"], "📁")
    dashboard._stat_card(stats_row, "TOTAL LINES OF CODE", str(metrics.get("totalLines", 0)), COLORS["success"], "📊")

    hero_card = dashboard._card(parent)
    hero_card.pack(fill="x", pady=(0, 16))
    tk.Frame(hero_card, height=3, bg=COLORS["accent"]).pack(fill="x")
    inner = tk.Frame(hero_card, bg=COLORS["bg_card"], padx=20, pady=18)
    inner.pack(fill="both")

    tk.Label(inner, text="Interactive Codebase Architecture Graph", font=FONTS["heading_md"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
    tk.Label(inner, text="Explore modules, circular dependencies, and file relationships in 3D force-directed layout:", font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 14))

    tk.Button(
        inner,
        text="  🏛️ Launch Native 3D Architecture Window  ",
        font=FONTS["label_bold"],
        bg=COLORS["accent"],
        fg=COLORS["bg_darkest"],
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=18,
        pady=9,
        command=lambda: open_native_3d_viewport("architecture", repo_path),
    ).pack(anchor="w")


def render_3d_security_page(dashboard) -> None:
    """Render 3D Security Risk Map view inside User Dashboard."""
    parent = _get_parent(dashboard)
    repo_path = getattr(dashboard, "_gd_selected_repo", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _actions(row):
        btn = tk.Button(
            row,
            text="🛡️ Open 3D Viewport",
            font=FONTS["label_bold"],
            bg=COLORS["danger"],
            fg=COLORS["text_primary"],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=14,
            pady=6,
            command=lambda: open_native_3d_viewport("security_map", repo_path),
        )
        btn.pack(side="right")

    dashboard._create_page_header_panel(
        parent,
        title="3D Security Risk Map",
        subtitle="Color-coded 3D visualization of vulnerabilities, CWE-798 secrets, and syntax security findings.",
        icon="🛡️",
        actions_fn=_actions,
    )

    sec_data = scene_data.build_security_data(repo_path)
    summary = sec_data.get("summary", {})

    stats_row = tk.Frame(parent, bg=COLORS["bg_dark"])
    stats_row.pack(fill="x", pady=(0, 14))

    dashboard._stat_card(stats_row, "SECURITY HEALTH SCORE", f"{sec_data.get('healthScore', 100)}/100", COLORS["success"], "🛡️")
    dashboard._stat_card(stats_row, "CRITICAL RISK", str(summary.get("critical", 0)), COLORS["danger"], "🚨")
    dashboard._stat_card(stats_row, "HIGH / MEDIUM FINDINGS", str(summary.get("high", 0) + summary.get("medium", 0)), COLORS["warning"], "⚠️")

    hero_card = dashboard._card(parent)
    hero_card.pack(fill="x", pady=(0, 16))
    tk.Frame(hero_card, height=3, bg=COLORS["danger"]).pack(fill="x")
    inner = tk.Frame(hero_card, bg=COLORS["bg_card"], padx=20, pady=18)
    inner.pack(fill="both")

    tk.Label(inner, text="Interactive 3D Vulnerability Heatmap", font=FONTS["heading_md"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
    tk.Label(inner, text="Inspect affected lines, secret exposures, and AI-generated remediation recommendations in 3D:", font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 14))

    tk.Button(
        inner,
        text="  🛡️ Launch Native 3D Security Risk Map Window  ",
        font=FONTS["label_bold"],
        bg=COLORS["danger"],
        fg=COLORS["text_primary"],
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=18,
        pady=9,
        command=lambda: open_native_3d_viewport("security_map", repo_path),
    ).pack(anchor="w")


def render_3d_agents_page(dashboard) -> None:
    """Render AI Multi-Agent Workflow Visualization view."""
    parent = _get_parent(dashboard)

    dashboard._create_page_header_panel(
        parent,
        title="AI Multi-Agent Workflow Pipeline",
        subtitle="Interactive visualization of AI agents (Reviewer, Auditor, Tester, Composer, Deployer).",
        icon="🤖",
        actions_fn=lambda row: tk.Button(
            row,
            text="🤖 Open 3D Viewport",
            font=FONTS["label_bold"],
            bg=COLORS["accent"],
            fg=COLORS["bg_darkest"],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=14,
            pady=6,
            command=lambda: open_native_3d_viewport("agent_workflow"),
        ).pack(side="right"),
    )

    agent_data = scene_data.build_agent_workflow_data()
    agents = agent_data.get("agents", [])

    hero_card = dashboard._card(parent)
    hero_card.pack(fill="x", pady=(0, 16))
    tk.Frame(hero_card, height=3, bg=COLORS["accent"]).pack(fill="x")
    inner = tk.Frame(hero_card, bg=COLORS["bg_card"], padx=20, pady=18)
    inner.pack(fill="both")

    tk.Label(inner, text="Real-Time AI Agent Topology", font=FONTS["heading_md"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
    tk.Label(inner, text="Inspect active agent communication, task dependencies, and human approval checkpoints:", font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 14))

    tk.Button(
        inner,
        text="  🤖 Launch Native 3D Agent Workflow Window  ",
        font=FONTS["label_bold"],
        bg=COLORS["accent"],
        fg=COLORS["bg_darkest"],
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=18,
        pady=9,
        command=lambda: open_native_3d_viewport("agent_workflow"),
    ).pack(anchor="w")


def render_3d_merge_page(dashboard) -> None:
    """Render 3D Branch Merge Simulator view."""
    parent = _get_parent(dashboard)

    dashboard._create_page_header_panel(
        parent,
        title="3D Branch Merge Simulator",
        subtitle="Simulate and preview branch merges, conflict detection, and impact blast-radii.",
        icon="🔀",
        actions_fn=lambda row: tk.Button(
            row,
            text="🔀 Open 3D Viewport",
            font=FONTS["label_bold"],
            bg=COLORS["accent"],
            fg=COLORS["bg_darkest"],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=14,
            pady=6,
            command=lambda: open_native_3d_viewport("merge_simulator"),
        ).pack(side="right"),
    )

    hero_card = dashboard._card(parent)
    hero_card.pack(fill="x", pady=(0, 16))
    tk.Frame(hero_card, height=3, bg=COLORS["accent"]).pack(fill="x")
    inner = tk.Frame(hero_card, bg=COLORS["bg_card"], padx=20, pady=18)
    inner.pack(fill="both")

    tk.Label(inner, text="Branch Merge Readiness Simulation", font=FONTS["heading_md"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
    tk.Label(inner, text="Simulate merge outcomes before modifying repository history with AI conflict assistance:", font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 14))

    tk.Button(
        inner,
        text="  🔀 Launch Native 3D Merge Simulator Window  ",
        font=FONTS["label_bold"],
        bg=COLORS["accent"],
        fg=COLORS["bg_darkest"],
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=18,
        pady=9,
        command=lambda: open_native_3d_viewport("merge_simulator"),
    ).pack(anchor="w")


# ── Page Builders for Admin App ───────────────────────────────────────────────

def render_3d_topology_page(admin) -> None:
    """Render 3D Device & Network Topology view inside Admin App."""
    parent = _get_parent(admin)

    admin._create_page_header_panel(
        parent,
        title="3D Device & Network Topology",
        subtitle="Interactive visualization of connected Tailscale workstations, authorization states, and traffic.",
        icon="🌐",
        actions_fn=lambda row: tk.Button(
            row,
            text="🌐 Open 3D Viewport",
            font=FONTS["label_bold"],
            bg=COLORS["accent"],
            fg=COLORS["bg_darkest"],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=14,
            pady=6,
            command=lambda: open_native_3d_viewport("device_topology"),
        ).pack(side="right"),
    )

    topo_data = scene_data.build_device_topology_data()
    devices = topo_data.get("devices", [])

    stats_row = tk.Frame(parent, bg=COLORS["bg_dark"])
    stats_row.pack(fill="x", pady=(0, 14))

    admin._stat_card(stats_row, "CONNECTED DEVICES", str(len(devices)), COLORS["accent"], "💻")
    admin._stat_card(stats_row, "AUTHORIZED NODES", str(sum(1 for d in devices if d.get("authorized"))), COLORS["success"], "✅")
    admin._stat_card(stats_row, "NETWORK HEALTH", "Optimal (0 ms)", COLORS["warning"], "📡")

    hero_card = admin._card(parent)
    hero_card.pack(fill="x", pady=(0, 16))
    tk.Frame(hero_card, height=3, bg=COLORS["accent"]).pack(fill="x")
    inner = tk.Frame(hero_card, bg=COLORS["bg_card"], padx=20, pady=18)
    inner.pack(fill="both")

    tk.Label(inner, text="Interactive Tailnet Mesh Topology", font=FONTS["heading_md"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
    tk.Label(inner, text="Visualize network relationships, device authentication, and highlight suspicious connections in 3D:", font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 14))

    tk.Button(
        inner,
        text="  🌐 Launch Native 3D Device Topology Window  ",
        font=FONTS["label_bold"],
        bg=COLORS["accent"],
        fg=COLORS["bg_darkest"],
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=18,
        pady=9,
        command=lambda: open_native_3d_viewport("device_topology"),
    ).pack(anchor="w")


def render_3d_health_page(admin) -> None:
    """Render AI Code Health Globe view inside Admin App."""
    parent = _get_parent(admin)

    admin._create_page_header_panel(
        parent,
        title="AI Code Health Globe",
        subtitle="Rotatable 3D sphere mapping repository code quality, technical debt, and security findings.",
        icon="🌍",
        actions_fn=lambda row: tk.Button(
            row,
            text="🌍 Open 3D Viewport",
            font=FONTS["label_bold"],
            bg=COLORS["accent"],
            fg=COLORS["bg_darkest"],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=14,
            pady=6,
            command=lambda: open_native_3d_viewport("health_globe"),
        ).pack(side="right"),
    )

    hero_card = admin._card(parent)
    hero_card.pack(fill="x", pady=(0, 16))
    tk.Frame(hero_card, height=3, bg=COLORS["accent"]).pack(fill="x")
    inner = tk.Frame(hero_card, bg=COLORS["bg_card"], padx=20, pady=18)
    inner.pack(fill="both")

    tk.Label(inner, text="Rotatable 3D Repository Health Globe", font=FONTS["heading_md"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
    tk.Label(inner, text="Continental regions represent system subsystems, with elevation and coloration mapping to technical debt:", font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 14))

    tk.Button(
        inner,
        text="  🌍 Launch Native 3D Code Health Globe Window  ",
        font=FONTS["label_bold"],
        bg=COLORS["accent"],
        fg=COLORS["bg_darkest"],
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=18,
        pady=9,
        command=lambda: open_native_3d_viewport("health_globe"),
    ).pack(anchor="w")


def render_3d_pipeline_page(admin) -> None:
    """Render 3D Deployment Pipeline view inside Admin App."""
    parent = _get_parent(admin)

    admin._create_page_header_panel(
        parent,
        title="3D Deployment Pipeline",
        subtitle="Interactive 3D visualization of build, test, scan, approval, and production deployment stages.",
        icon="🚀",
        actions_fn=lambda row: tk.Button(
            row,
            text="🚀 Open 3D Viewport",
            font=FONTS["label_bold"],
            bg=COLORS["accent"],
            fg=COLORS["bg_darkest"],
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=14,
            pady=6,
            command=lambda: open_native_3d_viewport("deployment_pipeline"),
        ).pack(side="right"),
    )

    hero_card = admin._card(parent)
    hero_card.pack(fill="x", pady=(0, 16))
    tk.Frame(hero_card, height=3, bg=COLORS["accent"]).pack(fill="x")
    inner = tk.Frame(hero_card, bg=COLORS["bg_card"], padx=20, pady=18)
    inner.pack(fill="both")

    tk.Label(inner, text="Interactive 3D Deployment Stages", font=FONTS["heading_md"], fg=COLORS["text_primary"], bg=COLORS["bg_card"]).pack(anchor="w")
    tk.Label(inner, text="Inspect CI/CD build progress, failure points, and deployment security gates in 3D:", font=FONTS["body_sm"], fg=COLORS["text_secondary"], bg=COLORS["bg_card"]).pack(anchor="w", pady=(4, 14))

    tk.Button(
        inner,
        text="  🚀 Launch Native 3D Deployment Pipeline Window  ",
        font=FONTS["label_bold"],
        bg=COLORS["accent"],
        fg=COLORS["bg_darkest"],
        relief="flat",
        bd=0,
        cursor="hand2",
        padx=18,
        pady=9,
        command=lambda: open_native_3d_viewport("deployment_pipeline"),
    ).pack(anchor="w")
