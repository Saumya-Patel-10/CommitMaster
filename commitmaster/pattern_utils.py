"""
CommitMaster — Pattern & Texture Generation Engine.
===================================================
Generates high-performance, seamless procedural patterns, tech grids,
carbon fiber textures, circuit meshes, and illuminated backdrops using Pillow.
Elevates the desktop UI beyond flat solid colors into a state-of-the-art,
professional developer experience.
"""
import math
from typing import Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageTk

# ── Supported Pattern Definitions ─────────────────────────────────────────────
PATTERNS: Dict[str, Dict[str, str]] = {
    "dot_matrix": {
        "name": "Tech Dot Matrix",
        "desc": "Developer coordinate grid with precision alignment micro-dots",
        "icon": "⠶",
    },
    "circuit_mesh": {
        "name": "Circuit Mesh",
        "desc": "Futuristic microchip traces, 45° bus lines, and silicon junction pads",
        "icon": "⚡",
    },
    "carbon_weave": {
        "name": "Carbon Weave",
        "desc": "Executive tactile diagonal composite weave with depth",
        "icon": "🛡️",
    },
    "blueprint_grid": {
        "name": "Blueprint Grid",
        "desc": "Clean isometric engineering coordinate grid with crosshairs",
        "icon": "📐",
    },
    "hex_mesh": {
        "name": "Hexagon Mesh",
        "desc": "Futuristic cyber honeycomb wireframe geometry",
        "icon": "⬡",
    },
    "ambient_glow": {
        "name": "Ambient Radial",
        "desc": "Soft luminous radial spotlight with subtle noise texture",
        "icon": "✨",
    },
    "clean_solid": {
        "name": "Clean Solid",
        "desc": "Minimalist flat dark surface with crisp accent borders",
        "icon": "▫️",
    },
}

# Image / PhotoImage cache to ensure 60fps responsiveness
_CACHE: Dict[str, Any] = {}
_MAX_CACHE_SIZE = 128


def _get_cache_key(*args) -> str:
    return ":".join(str(a) for a in args)


def hex_to_rgb(hex_code: str) -> Tuple[int, int, int]:
    """Parse hex string to (R, G, B) tuple safely."""
    if not hex_code:
        return (13, 17, 23)
    s = hex_code.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    elif len(s) > 6:
        s = s[:6]
    try:
        val = int(s, 16)
        return ((val >> 16) & 255, (val >> 8) & 255, val & 255)
    except Exception:
        return (13, 17, 23)


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Format (R, G, B) tuple as #rrggbb."""
    r, g, b = max(0, min(255, rgb[0])), max(0, min(255, rgb[1])), max(0, min(255, rgb[2]))
    return f"#{r:02x}{g:02x}{b:02x}"


def blend_colors(c1: Tuple[int, int, int], c2: Tuple[int, int, int], alpha: float) -> Tuple[int, int, int]:
    """Blend two RGB colors by alpha factor (0.0 = c1, 1.0 = c2)."""
    alpha = max(0.0, min(1.0, alpha))
    return (
        int(round(c1[0] * (1 - alpha) + c2[0] * alpha)),
        int(round(c1[1] * (1 - alpha) + c2[1] * alpha)),
        int(round(c1[2] * (1 - alpha) + c2[2] * alpha)),
    )


def adjust_brightness(rgb: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    """Adjust color brightness (1.0 = unchanged, >1 brighter, <1 darker)."""
    return (
        max(0, min(255, int(round(rgb[0] * factor)))),
        max(0, min(255, int(round(rgb[1] * factor)))),
        max(0, min(255, int(round(rgb[2] * factor)))),
    )


# ── Procedural Tile Generators ────────────────────────────────────────────────

def generate_tile(pattern_name: str, bg_rgb: Tuple[int, int, int], accent_rgb: Tuple[int, int, int]) -> Image.Image:
    """Generate a single seamless procedural pattern tile image."""
    key = _get_cache_key("tile", pattern_name, bg_rgb, accent_rgb)
    if key in _CACHE:
        return _CACHE[key]

    name = pattern_name if pattern_name in PATTERNS else "dot_matrix"

    if name == "clean_solid":
        tile = Image.new("RGB", (32, 32), bg_rgb)

    elif name == "dot_matrix":
        # 32x32 Developer Grid with subtle micro-dots and coordinate nodes
        sz = 32
        tile = Image.new("RGB", (sz, sz), bg_rgb)
        draw = ImageDraw.Draw(tile)
        dot_col = blend_colors(bg_rgb, accent_rgb, 0.22)
        node_col = blend_colors(bg_rgb, (255, 255, 255), 0.12)
        # Center micro-dot
        draw.ellipse((14, 14, 17, 17), fill=dot_col)
        # Corner micro-ticks
        draw.point((0, 0), fill=node_col)
        draw.point((sz - 1, 0), fill=node_col)
        draw.point((0, sz - 1), fill=node_col)
        draw.point((sz - 1, sz - 1), fill=node_col)
        # Subtle crosshair tick
        cross_col = blend_colors(bg_rgb, (255, 255, 255), 0.06)
        draw.line([(0, 15), (2, 15)], fill=cross_col)
        draw.line([(15, 0), (15, 2)], fill=cross_col)

    elif name == "circuit_mesh":
        # 48x48 Silicon Circuit traces and junction pads (seamless on wrapping edges)
        sz = 48
        tile = Image.new("RGB", (sz, sz), bg_rgb)
        draw = ImageDraw.Draw(tile)
        trace_col = blend_colors(bg_rgb, accent_rgb, 0.16)
        bright_trace = blend_colors(bg_rgb, accent_rgb, 0.28)
        pad_col = blend_colors(bg_rgb, (255, 255, 255), 0.20)

        # Trace 1: (0, 16) -> (16, 16) -> (24, 24) -> (48, 24)
        draw.line([(0, 16), (16, 16), (24, 24), (48, 24)], fill=trace_col, width=1)
        # Trace 2: (24, 0) -> (24, 12) -> (36, 24) -> (36, 48)
        draw.line([(24, 0), (24, 12), (36, 24), (36, 48)], fill=trace_col, width=1)
        # Trace 3: (0, 36) -> (12, 36) -> (24, 48)
        draw.line([(0, 36), (12, 36), (24, 48)], fill=trace_col, width=1)
        # Silicon Pads
        draw.rectangle((14, 14, 18, 18), fill=pad_col)
        draw.rectangle((34, 22, 38, 26), fill=bright_trace)
        draw.ellipse((22, 10, 26, 14), fill=trace_col)

    elif name == "carbon_weave":
        # 16x16 Tactile Carbon Fiber diagonal weave
        sz = 16
        tile = Image.new("RGB", (sz, sz), bg_rgb)
        draw = ImageDraw.Draw(tile)
        light_fiber = blend_colors(bg_rgb, (255, 255, 255), 0.11)
        deep_fiber = adjust_brightness(bg_rgb, 0.75)
        accent_fiber = blend_colors(bg_rgb, accent_rgb, 0.08)

        for offset in range(-16, 32, 4):
            draw.line([(offset, 0), (offset + 16, 16)], fill=light_fiber, width=1)
            draw.line([(offset + 2, 0), (offset + 18, 16)], fill=deep_fiber, width=1)
        draw.line([(0, 8), (16, 8)], fill=accent_fiber, width=1)

    elif name == "blueprint_grid":
        # 32x32 Engineering Blueprint Grid with crosshairs
        sz = 32
        tile = Image.new("RGB", (sz, sz), bg_rgb)
        draw = ImageDraw.Draw(tile)
        grid_col = blend_colors(bg_rgb, accent_rgb, 0.14)
        cross_col = blend_colors(bg_rgb, (255, 255, 255), 0.25)
        # Grid border lines
        draw.line([(0, 0), (sz - 1, 0)], fill=grid_col)
        draw.line([(0, 0), (0, sz - 1)], fill=grid_col)
        # Tiny '+' at corners
        draw.line([(0, 2), (0, 0), (2, 0)], fill=cross_col)
        draw.line([(sz - 3, 0), (sz - 1, 0), (sz - 1, 2)], fill=cross_col)

    elif name == "hex_mesh":
        # 40x40 Cyber Honeycomb wireframe
        sz = 40
        tile = Image.new("RGB", (sz, sz), bg_rgb)
        draw = ImageDraw.Draw(tile)
        hex_col = blend_colors(bg_rgb, accent_rgb, 0.15)
        # Hexagonal node lines
        pts1 = [(10, 0), (20, 5), (20, 15), (10, 20), (0, 15), (0, 5)]
        pts2 = [(30, 20), (40, 25), (40, 35), (30, 40), (20, 35), (20, 25)]
        draw.polygon(pts1, outline=hex_col)
        draw.polygon(pts2, outline=hex_col)
        # Mini core
        draw.point((10, 10), fill=blend_colors(bg_rgb, accent_rgb, 0.35))
        draw.point((30, 30), fill=blend_colors(bg_rgb, accent_rgb, 0.35))

    elif name == "ambient_glow":
        # 48x48 Soft ambient micro-cell
        sz = 48
        tile = Image.new("RGB", (sz, sz), bg_rgb)
        draw = ImageDraw.Draw(tile)
        for r in range(16, 0, -3):
            glow_col = blend_colors(bg_rgb, accent_rgb, (16 - r) * 0.012)
            draw.ellipse((24 - r, 24 - r, 24 + r, 24 + r), fill=glow_col)
        draw.point((24, 24), fill=blend_colors(bg_rgb, accent_rgb, 0.40))

    else:
        tile = Image.new("RGB", (32, 32), bg_rgb)

    if len(_CACHE) > _MAX_CACHE_SIZE:
        _CACHE.clear()
    _CACHE[key] = tile
    return tile


def tile_pattern(width: int, height: int, pattern_name: str, bg_rgb: Tuple[int, int, int], accent_rgb: Tuple[int, int, int]) -> Image.Image:
    """Tile a pattern across width x height."""
    tile = generate_tile(pattern_name, bg_rgb, accent_rgb)
    tw, th = tile.size
    img = Image.new("RGB", (width, height), bg_rgb)
    for x in range(0, width, tw):
        for y in range(0, height, th):
            img.paste(tile, (x, y))
    return img


# ── Composite Banners & Backdrops ─────────────────────────────────────────────

def generate_login_backdrop(width: int, height: int, bg_hex: str, accent_hex: str, pattern_name: str = "dot_matrix") -> ImageTk.PhotoImage:
    """
    Generate a full-window backdrop for the Login window.
    Features:
      • Procedural pattern grid tiled seamlessly across the screen.
      • Soft ambient radial spotlight centered where the login card sits.
      • Subtle vignette around window edges for cinematic focus.
    """
    w = max(400, width)
    h = max(400, height)
    key = _get_cache_key("login_bg", w, h, bg_hex, accent_hex, pattern_name)
    if key in _CACHE:
        return _CACHE[key]

    bg_rgb = hex_to_rgb(bg_hex)
    accent_rgb = hex_to_rgb(accent_hex)

    # 1. Tile base pattern
    base_img = tile_pattern(w, h, pattern_name, bg_rgb, accent_rgb)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 2. Ambient radial spotlight centered at (w/2, h/2 - 20)
    cx = w // 2
    cy = max(120, h // 2 - 30)
    max_radius = int(math.hypot(w, h) * 0.45)
    steps = 24
    for i in range(steps, 0, -1):
        radius = int(max_radius * (i / steps))
        factor = (1.0 - (i / steps)) ** 1.8
        glow_alpha = int(45 * factor)
        r, g, b = blend_colors(bg_rgb, accent_rgb, 0.45 * factor)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(r, g, b, glow_alpha))

    # 3. Outer border vignette
    vignette_depth = min(60, min(w, h) // 8)
    for step in range(vignette_depth):
        alpha = int(70 * (1.0 - (step / vignette_depth)))
        draw.rectangle((step, step, w - step - 1, h - step - 1), outline=(0, 0, 0, alpha))

    # Composite
    base_rgba = base_img.convert("RGBA")
    final_img = Image.alpha_composite(base_rgba, overlay).convert("RGB")
    photo = ImageTk.PhotoImage(final_img)

    if len(_CACHE) > _MAX_CACHE_SIZE:
        _CACHE.clear()
    _CACHE[key] = photo
    return photo


def generate_header_banner(width: int, height: int, bg_hex: str, accent_hex: str, pattern_name: str = "dot_matrix") -> ImageTk.PhotoImage:
    """
    Generate an executive header banner with subtle pattern,
    horizontal gradient wash, and bottom accent glow hairline.
    """
    w = max(200, width)
    h = max(40, height)
    key = _get_cache_key("hdr_banner", w, h, bg_hex, accent_hex, pattern_name)
    if key in _CACHE:
        return _CACHE[key]

    bg_rgb = hex_to_rgb(bg_hex)
    accent_rgb = hex_to_rgb(accent_hex)

    # 1. Tile pattern
    base_img = tile_pattern(w, h, pattern_name, bg_rgb, accent_rgb)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # 2. Subtle horizontal gradient from left to right
    for x in range(w):
        # subtle wave on header
        ratio = x / max(1, w)
        # soft accent wash towards the right side
        wash_alpha = int(18 * math.sin(ratio * math.pi))
        r, g, b = blend_colors(bg_rgb, accent_rgb, 0.3)
        draw.line([(x, 0), (x, h - 2)], fill=(r, g, b, wash_alpha))

    # 3. Bottom accent hairline glow (h-2 and h-1)
    glow_col = blend_colors(bg_rgb, accent_rgb, 0.35)
    sharp_col = blend_colors(bg_rgb, accent_rgb, 0.85)
    draw.line([(0, h - 2), (w, h - 2)], fill=(*glow_col, 140))
    draw.line([(0, h - 1), (w, h - 1)], fill=(*sharp_col, 220))

    base_rgba = base_img.convert("RGBA")
    final_img = Image.alpha_composite(base_rgba, overlay).convert("RGB")
    photo = ImageTk.PhotoImage(final_img)

    if len(_CACHE) > _MAX_CACHE_SIZE:
        _CACHE.clear()
    _CACHE[key] = photo
    return photo


def generate_hero_card_banner(width: int, height: int, bg_hex: str, accent_hex: str, pattern_name: str = "dot_matrix") -> ImageTk.PhotoImage:
    """
    Generate a hero welcome card background with pattern texture,
    radial accent spotlight, and refined border.
    """
    w = max(300, width)
    h = max(80, height)
    key = _get_cache_key("hero_banner", w, h, bg_hex, accent_hex, pattern_name)
    if key in _CACHE:
        return _CACHE[key]

    bg_rgb = hex_to_rgb(bg_hex)
    accent_rgb = hex_to_rgb(accent_hex)

    base_img = tile_pattern(w, h, pattern_name, bg_rgb, accent_rgb)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Radial bloom on the right side of the hero card
    cx = int(w * 0.82)
    cy = h // 2
    max_r = int(h * 1.2)
    steps = 16
    for i in range(steps, 0, -1):
        radius = int(max_r * (i / steps))
        factor = (1.0 - (i / steps)) ** 1.6
        alpha = int(48 * factor)
        r, g, b = blend_colors(bg_rgb, accent_rgb, 0.5 * factor)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(r, g, b, alpha))

    # Top accent highlight line
    draw.line([(0, 0), (w, 0)], fill=(*accent_rgb, 200))
    draw.line([(0, 1), (w, 1)], fill=(*blend_colors(bg_rgb, accent_rgb, 0.4), 100))

    base_rgba = base_img.convert("RGBA")
    final_img = Image.alpha_composite(base_rgba, overlay).convert("RGB")
    photo = ImageTk.PhotoImage(final_img)

    if len(_CACHE) > _MAX_CACHE_SIZE:
        _CACHE.clear()
    _CACHE[key] = photo
    return photo


def generate_sidebar_header_banner(width: int, height: int, bg_hex: str, accent_hex: str, pattern_name: str = "dot_matrix") -> ImageTk.PhotoImage:
    """Generate a patterned header banner for the sidebar branding."""
    w = max(120, width)
    h = max(40, height)
    key = _get_cache_key("sb_hdr", w, h, bg_hex, accent_hex, pattern_name)
    if key in _CACHE:
        return _CACHE[key]

    bg_rgb = hex_to_rgb(bg_hex)
    accent_rgb = hex_to_rgb(accent_hex)

    base_img = tile_pattern(w, h, pattern_name, bg_rgb, accent_rgb)
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Subtle diagonal accent stripe on left
    for x in range(min(40, w)):
        alpha = int(25 * (1.0 - (x / 40.0)))
        draw.line([(x, 0), (x, h)], fill=(*accent_rgb, alpha))

    # Bottom border
    border_col = blend_colors(bg_rgb, accent_rgb, 0.35)
    draw.line([(0, h - 1), (w, h - 1)], fill=(*border_col, 180))

    base_rgba = base_img.convert("RGBA")
    final_img = Image.alpha_composite(base_rgba, overlay).convert("RGB")
    photo = ImageTk.PhotoImage(final_img)

    if len(_CACHE) > _MAX_CACHE_SIZE:
        _CACHE.clear()
    _CACHE[key] = photo
    return photo


def generate_pattern_preview_card(pattern_key: str, bg_hex: str, accent_hex: str, width: int = 140, height: int = 80) -> ImageTk.PhotoImage:
    """Generate a crisp thumbnail preview for the pattern picker in Settings/Customization."""
    key = _get_cache_key("preview", pattern_key, bg_hex, accent_hex, width, height)
    if key in _CACHE:
        return _CACHE[key]

    bg_rgb = hex_to_rgb(bg_hex)
    accent_rgb = hex_to_rgb(accent_hex)

    img = tile_pattern(width, height, pattern_key, bg_rgb, accent_rgb)
    draw = ImageDraw.Draw(img)

    # Border & subtle inner shadow
    border_rgb = blend_colors(bg_rgb, accent_rgb, 0.4)
    draw.rectangle((0, 0, width - 1, height - 1), outline=border_rgb, width=1)
    # Accent top dot
    draw.ellipse((width - 14, 6, width - 6, 14), fill=accent_rgb)

    photo = ImageTk.PhotoImage(img)
    if len(_CACHE) > _MAX_CACHE_SIZE:
        _CACHE.clear()
    _CACHE[key] = photo
    return photo


def generate_medallion(size: int, bg_hex: str, accent_hex: str, icon_char: str = "⚡") -> ImageTk.PhotoImage:
    """Generate a glowing rounded medallion badge with subtle micro-pattern."""
    key = _get_cache_key("medallion", size, bg_hex, accent_hex, icon_char)
    if key in _CACHE:
        return _CACHE[key]

    sz = max(24, size)
    bg_rgb = hex_to_rgb(bg_hex)
    accent_rgb = hex_to_rgb(accent_hex)

    img = Image.new("RGBA", (sz, sz), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer soft glow ring
    draw.rounded_rectangle((1, 1, sz - 2, sz - 2), radius=sz // 4, fill=(*bg_rgb, 230), outline=(*accent_rgb, 140), width=1)
    # Accent inner border
    inner_pad = 3
    draw.rounded_rectangle(
        (inner_pad, inner_pad, sz - inner_pad - 1, sz - inner_pad - 1),
        radius=(sz // 4) - 2,
        fill=(*blend_colors(bg_rgb, accent_rgb, 0.12), 240),
        outline=(*blend_colors(bg_rgb, accent_rgb, 0.45), 180),
        width=1
    )

    photo = ImageTk.PhotoImage(img)
    if len(_CACHE) > _MAX_CACHE_SIZE:
        _CACHE.clear()
    _CACHE[key] = photo
    return photo
