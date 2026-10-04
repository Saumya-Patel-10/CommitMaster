"""
CommitMaster — Centralized design system, theme tokens, and dynamic customization.
"""
from typing import Dict, Any, Optional

# ── Base Theme Presets ─────────────────────────────────────────────────────────
THEMES: Dict[str, Dict[str, str]] = {
    "github_dark": {
        "name": "GitHub Dark (Default)",
        "bg_darkest":    "#0d1117",
        "bg_dark":       "#161b22",
        "bg_medium":     "#1c2128",
        "bg_card":       "#21262d",
        "bg_card_hover": "#2d333b",
        "bg_input":      "#1c2128",
        "bg_sidebar":    "#13171e",
        "text_primary":  "#e6edf3",
        "text_secondary":"#8b949e",
        "text_muted":    "#484f58",
        "border":        "#30363d",
        "border_focus":  "#3fb950",
    },
    "midnight": {
        "name": "Midnight Obsidian (OLED)",
        "bg_darkest":    "#050508",
        "bg_dark":       "#0b0c10",
        "bg_medium":     "#12141c",
        "bg_card":       "#171924",
        "bg_card_hover": "#222534",
        "bg_input":      "#12141c",
        "bg_sidebar":    "#07080c",
        "text_primary":  "#f0f6fc",
        "text_secondary":"#8c96a3",
        "text_muted":    "#4b5360",
        "border":        "#26293a",
        "border_focus":  "#58a6ff",
    },
    "dracula": {
        "name": "Dracula Violet",
        "bg_darkest":    "#191a21",
        "bg_dark":       "#21222c",
        "bg_medium":     "#282a36",
        "bg_card":       "#343746",
        "bg_card_hover": "#44475a",
        "bg_input":      "#21222c",
        "bg_sidebar":    "#16171d",
        "text_primary":  "#f8f8f2",
        "text_secondary":"#bd93f9",
        "text_muted":    "#6272a4",
        "border":        "#44475a",
        "border_focus":  "#ff79c6",
    },
    "cyberpunk": {
        "name": "Cyberpunk Neon",
        "bg_darkest":    "#0a0e17",
        "bg_dark":       "#111827",
        "bg_medium":     "#172033",
        "bg_card":       "#1e293b",
        "bg_card_hover": "#2e3f5c",
        "bg_input":      "#131d2e",
        "bg_sidebar":    "#0b111c",
        "text_primary":  "#e0f2fe",
        "text_secondary":"#7dd3fc",
        "text_muted":    "#38bdf8",
        "border":        "#0369a1",
        "border_focus":  "#38bdf8",
    },
    "nord": {
        "name": "Nordic Frost",
        "bg_darkest":    "#242933",
        "bg_dark":       "#2e3440",
        "bg_medium":     "#3b4252",
        "bg_card":       "#434c5e",
        "bg_card_hover": "#4c566a",
        "bg_input":      "#2e3440",
        "bg_sidebar":    "#1e222a",
        "text_primary":  "#eceff4",
        "text_secondary":"#d8dee9",
        "text_muted":    "#7b88a1",
        "border":        "#4c566a",
        "border_focus":  "#88c0d0",
    },
    "monokai": {
        "name": "Monokai Pro Charcoal",
        "bg_darkest":    "#19181a",
        "bg_dark":       "#221f22",
        "bg_medium":     "#2d2a2e",
        "bg_card":       "#363337",
        "bg_card_hover": "#403e41",
        "bg_input":      "#2d2a2e",
        "bg_sidebar":    "#171517",
        "text_primary":  "#fcfcfa",
        "text_secondary":"#939293",
        "text_muted":    "#5b595c",
        "border":        "#4a474b",
        "border_focus":  "#ffd866",
    },
    "light": {
        "name": "Modern Clean Light",
        "bg_darkest":    "#eef2f6",
        "bg_dark":       "#f6f8fa",
        "bg_medium":     "#ffffff",
        "bg_card":       "#ffffff",
        "bg_card_hover": "#f3f4f6",
        "bg_input":      "#f8fafc",
        "bg_sidebar":    "#e5e7eb",
        "text_primary":  "#1f2328",
        "text_secondary":"#656d76",
        "text_muted":    "#8c959f",
        "border":        "#d0d7de",
        "border_focus":  "#0969da",
    },
}

# ── Accent Presets ─────────────────────────────────────────────────────────────
ACCENTS: Dict[str, Dict[str, str]] = {
    "green": {
        "name": "Emerald Green",
        "accent": "#3fb950",
        "accent_dark": "#2ea043",
        "accent_hover": "#56d364",
        "accent_glow": "#3fb95040",
    },
    "cyan": {
        "name": "Neon Cyan",
        "accent": "#58a6ff",
        "accent_dark": "#1f6feb",
        "accent_hover": "#79c0ff",
        "accent_glow": "#58a6ff40",
    },
    "purple": {
        "name": "Royal Violet",
        "accent": "#bc8cff",
        "accent_dark": "#8957e5",
        "accent_hover": "#d2a8ff",
        "accent_glow": "#bc8cff40",
    },
    "orange": {
        "name": "Sunset Amber",
        "accent": "#f0883e",
        "accent_dark": "#db6d28",
        "accent_hover": "#ffa657",
        "accent_glow": "#f0883e40",
    },
    "red": {
        "name": "Crimson Red",
        "accent": "#f85149",
        "accent_dark": "#da3633",
        "accent_hover": "#ff7b72",
        "accent_glow": "#f8514940",
    },
    "rose": {
        "name": "Rose Pink",
        "accent": "#f43f5e",
        "accent_dark": "#e11d48",
        "accent_hover": "#fb7185",
        "accent_glow": "#f43f5e40",
    },
    "teal": {
        "name": "Mint Teal",
        "accent": "#2dd4bf",
        "accent_dark": "#0d9488",
        "accent_hover": "#5eead4",
        "accent_glow": "#2dd4bf40",
    },
}

# ── Available Font Families ────────────────────────────────────────────────────
FONT_FAMILIES = ["Segoe UI", "Consolas", "Inter", "Roboto", "Cascadia Code", "Arial"]

# ── Available Font Scales ──────────────────────────────────────────────────────
FONT_SCALES = {
    "compact": 0.9,
    "standard": 1.0,
    "large": 1.15,
}

# ── Color Palette (Active Tokens) ──────────────────────────────────────────────
COLORS: Dict[str, str] = {
    # Backgrounds
    "bg_darkest":    "#0d1117",
    "bg_dark":       "#161b22",
    "bg_medium":     "#1c2128",
    "bg_card":       "#21262d",
    "bg_card_hover": "#2d333b",
    "bg_input":      "#1c2128",
    "bg_sidebar":    "#13171e",

    # Accent — GitHub green default
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

# ── Base Font Definitions ──────────────────────────────────────────────────────
BASE_FONT_SIZES = {
    "heading_xl": 28,
    "heading_lg": 20,
    "heading_md": 16,
    "heading_sm": 13,
    "body_lg":    14,
    "body_md":    12,
    "body_sm":    11,
    "mono":       11,
    "mono_sm":    10,
    "label":      11,
    "label_bold": 11,
    "caption":    10,
}

# Active FONTS dict
FONTS: Dict[str, tuple] = {
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
SIZES: Dict[str, int] = {
    "sidebar_width":   220,
    "header_height":   60,
    "card_radius":     12,
    "btn_radius":      8,
    "input_radius":    6,
    "padding_lg":      24,
    "padding_md":      16,
    "padding_sm":      8,
}

# Active customization state tracking
_ACTIVE_CUSTOMIZATION = {
    "theme": "github_dark",
    "accent": "green",
    "accent_hex": "#3fb950",
    "font_family": "Segoe UI",
    "font_scale": "standard",
    "ui_density": "comfortable",
}


def get_active_customization() -> Dict[str, Any]:
    """Return a copy of currently active customization settings."""
    return dict(_ACTIVE_CUSTOMIZATION)


def apply_customization(
    theme: Optional[str] = None,
    accent: Optional[str] = None,
    font_family: Optional[str] = None,
    font_scale: Optional[str] = None,
    ui_density: Optional[str] = None,
) -> None:
    """
    Apply customization settings in-place to COLORS, FONTS, and SIZES.
    """
    # 1. Theme colors
    if theme and theme in THEMES:
        _ACTIVE_CUSTOMIZATION["theme"] = theme
        theme_def = THEMES[theme]
        for k in ["bg_darkest", "bg_dark", "bg_medium", "bg_card", "bg_card_hover",
                  "bg_input", "bg_sidebar", "text_primary", "text_secondary", "text_muted", "border"]:
            if k in theme_def:
                COLORS[k] = theme_def[k]

    # 2. Accent colors
    if accent:
        accent_info = None
        if accent in ACCENTS:
            accent_info = ACCENTS[accent]
            _ACTIVE_CUSTOMIZATION["accent"] = accent
            _ACTIVE_CUSTOMIZATION["accent_hex"] = accent_info["accent"]
        elif accent.startswith("#"):
            # Custom hex accent
            _ACTIVE_CUSTOMIZATION["accent"] = "custom"
            _ACTIVE_CUSTOMIZATION["accent_hex"] = accent
            accent_info = {
                "accent": accent,
                "accent_dark": accent,
                "accent_hover": accent,
                "accent_glow": accent + "40" if len(accent) == 7 else accent,
            }

        if accent_info:
            COLORS["accent"] = accent_info["accent"]
            COLORS["accent_dark"] = accent_info["accent_dark"]
            COLORS["accent_hover"] = accent_info["accent_hover"]
            COLORS["accent_glow"] = accent_info.get("accent_glow", accent_info["accent"] + "40")
            COLORS["text_accent"] = accent_info["accent"]
            COLORS["border_focus"] = accent_info["accent"]
            COLORS["chart_commits"] = accent_info["accent"]

    # 3. Typography
    family = font_family or _ACTIVE_CUSTOMIZATION["font_family"]
    if family:
        _ACTIVE_CUSTOMIZATION["font_family"] = family

    scale_key = font_scale or _ACTIVE_CUSTOMIZATION["font_scale"]
    multiplier = FONT_SCALES.get(scale_key, 1.0)
    _ACTIVE_CUSTOMIZATION["font_scale"] = scale_key

    mono_fam = "Consolas" if family != "Cascadia Code" else "Cascadia Code"

    for key, base_sz in BASE_FONT_SIZES.items():
        scaled_sz = max(8, int(round(base_sz * multiplier)))
        is_bold = "bold" if "bold" in key or "heading" in key else None
        fam = mono_fam if "mono" in key else family
        if is_bold:
            FONTS[key] = (fam, scaled_sz, is_bold)
        else:
            FONTS[key] = (fam, scaled_sz)

    # 4. UI Density
    density = ui_density or _ACTIVE_CUSTOMIZATION["ui_density"]
    _ACTIVE_CUSTOMIZATION["ui_density"] = density
    if density == "compact":
        SIZES["sidebar_width"] = 200
        SIZES["header_height"] = 52
        SIZES["padding_lg"] = 18
        SIZES["padding_md"] = 12
        SIZES["padding_sm"] = 6
    else:
        SIZES["sidebar_width"] = 220
        SIZES["header_height"] = 60
        SIZES["padding_lg"] = 24
        SIZES["padding_md"] = 16
        SIZES["padding_sm"] = 8
