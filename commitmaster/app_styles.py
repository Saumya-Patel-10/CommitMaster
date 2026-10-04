"""
CommitMaster — Centralized design system / style tokens.
"""

# ── Color Palette ──────────────────────────────────────────────────────────────
COLORS = {
    # Backgrounds
    "bg_darkest":    "#0d1117",
    "bg_dark":       "#161b22",
    "bg_medium":     "#1c2128",
    "bg_card":       "#21262d",
    "bg_card_hover": "#2d333b",
    "bg_input":      "#1c2128",
    "bg_sidebar":    "#13171e",

    # Accent — GitHub green
    "accent":        "#3fb950",
    "accent_dark":   "#2ea043",
    "accent_hover":  "#56d364",
    "accent_glow":   "#3fb95040",

    # Secondary accent — orange (admin)
    "admin":         "#f0883e",
    "admin_dark":    "#db6d28",

    # Text
    "text_primary":  "#e6edf3",
    "text_secondary":"#8b949e",
    "text_muted":    "#484f58",
    "text_accent":   "#3fb950",

    # Status colours
    "success":       "#3fb950",
    "warning":       "#d29922",
    "error":         "#f85149",
    "info":          "#58a6ff",

    # Borders
    "border":        "#30363d",
    "border_focus":  "#3fb950",

    # Chart colours
    "chart_commits": "#3fb950",
    "chart_sessions":"#58a6ff",
    "chart_users":   "#f0883e",
}

# ── Avatar colours (cycling pool) ─────────────────────────────────────────────
AVATAR_COLORS = [
    "#3fb950", "#58a6ff", "#f0883e", "#f85149",
    "#d29922", "#bc8cff", "#39d353", "#ffa657",
]

# ── Fonts ──────────────────────────────────────────────────────────────────────
FONTS = {
    "heading_xl": ("Segoe UI", 28, "bold"),
    "heading_lg": ("Segoe UI", 20, "bold"),
    "heading_md": ("Segoe UI", 16, "bold"),
    "heading_sm": ("Segoe UI", 13, "bold"),
    "body_lg":    ("Segoe UI", 14),
    "body_md":    ("Segoe UI", 12),
    "body_sm":    ("Segoe UI", 11),
    "mono":       ("Consolas", 11),
    "mono_sm":    ("Consolas", 10),
    "label":      ("Segoe UI", 11),
    "label_bold": ("Segoe UI", 11, "bold"),
    "caption":    ("Segoe UI", 10),
}

# ── Sizes ──────────────────────────────────────────────────────────────────────
SIZES = {
    "sidebar_width":   220,
    "header_height":   60,
    "card_radius":     12,
    "btn_radius":      8,
    "input_radius":    6,
    "padding_lg":      24,
    "padding_md":      16,
    "padding_sm":      8,
}
