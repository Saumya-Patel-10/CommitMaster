"""Line charts (with data-point markers, hover tooltips, clickable legend) and the
admin analytics builders shared by the Admin Portal and the unified Admin App."""
import tkinter as tk
from typing import Any, Dict, List, Optional

from commitmaster import database as db
from commitmaster.app_styles import COLORS, FONTS

# Series colours that stay readable on every theme
C_GREEN, C_BLUE, C_ORANGE, C_RED, C_PURPLE, C_YELLOW, C_TEAL, C_PINK = (
    "#3fb950", "#58a6ff", "#f0883e", "#f85149", "#bc8cff", "#e3b341", "#2dd4bf", "#f778ba")
USER_PALETTE = [C_BLUE, C_GREEN, C_ORANGE, C_PURPLE, C_PINK, C_TEAL]


def _nice_max(value: float) -> int:
    """Round up so that 4 equal grid steps land on 'nice' numbers (4, 8, 20, 40, 100 ...)."""
    if value <= 4:
        return 4
    raw = value / 4.0
    mag = 1
    while mag * 10 <= raw:
        mag *= 10
    for m in (1, 2, 5, 10):
        step = m * mag
        if step >= raw:
            return int(step * 4)
    return int(mag * 40)


class LineChart(tk.Canvas):
    """
    Responsive multi-series line chart.
      • a marker on every data point
      • hover: guide line + tooltip with all values for that day
      • click a legend entry to hide / show that series
    series = [{"name": str, "color": "#hex", "values": [numbers], "fill": bool}, ...]
    """
    PAD_L, PAD_R, PAD_T, PAD_B = 44, 18, 34, 28

    def __init__(self, parent, dates: List[str], series: List[Dict[str, Any]], height: int = 230,
                 empty_text: str = "No activity recorded in this period"):
        super().__init__(parent, height=height, bg=COLORS["bg_card"], highlightthickness=0)
        self.dates = dates
        self.series = [dict(s) for s in series]
        self.hidden: set = set()
        self.empty_text = empty_text
        self._legend_boxes: List[tuple] = []
        self._hover_idx: Optional[int] = None
        self._last_dims = (0, 0)
        self._cur_cursor = ""
        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _on_configure(self, event):
        if (event.width, event.height) != self._last_dims and event.width > 10 and event.height > 10:
            self._last_dims = (event.width, event.height)
            self.redraw()

    # ── geometry helpers ─────────────────────────────────────────────────────
    def _plot_box(self):
        w, h = self.winfo_width(), self.winfo_height()
        top = self.PAD_T + 18 * (self._legend_rows() - 1)
        return self.PAD_L, top, w - self.PAD_R, h - self.PAD_B

    def _legend_rows(self) -> int:
        import tkinter.font as tkfont
        f = tkfont.Font(font=FONTS["caption"])
        avail = max(60, self.winfo_width() - self.PAD_L - self.PAD_R)
        rows, x = 1, 0
        for s in self.series:
            wdt = 22 + f.measure(f"{s['name']}  ({sum(s['values']):g})") + 20
            if x and x + wdt > avail:
                rows += 1
                x = 0
            x += wdt
        return rows

    def _x(self, i: int) -> float:
        x0, _, x1, _ = self._plot_box()
        n = len(self.dates)
        return x0 + (x1 - x0) * (i / (n - 1) if n > 1 else 0.5)

    def _y(self, v: float) -> float:
        _, y0, _, y1 = self._plot_box()
        return y1 - (y1 - y0) * (v / self.y_max if self.y_max else 0)

    # ── drawing ──────────────────────────────────────────────────────────────
    def redraw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 80 or h < 80:
            return
        x0, y0, x1, y1 = self._plot_box()
        visible = [s for s in self.series if s["name"] not in self.hidden]
        peak = max((max(s["values"], default=0) for s in visible), default=0)
        self.y_max = _nice_max(peak)
        has_data = any(any(v for v in s["values"]) for s in self.series)

        # gridlines + y labels
        ticks = 4
        for t in range(ticks + 1):
            val = self.y_max * t / ticks
            y = self._y(val)
            self.create_line(x0, y, x1, y, fill=COLORS["border"], dash=(2, 4) if t else None)
            label = f"{val:g}" if val == int(val) else f"{val:.1f}"
            self.create_text(x0 - 8, y, text=label, anchor="e", fill=COLORS["text_muted"], font=FONTS["caption"])

        # x labels
        n = len(self.dates)
        step = max(1, round(n / 8))
        for i in range(0, n, step):
            self.create_text(self._x(i), y1 + 14, text=self.dates[i][5:], fill=COLORS["text_muted"],
                             font=FONTS["caption"])

        # series
        show_points = n <= 45
        for s in visible:
            vals = s["values"]
            pts = [(self._x(i), self._y(v)) for i, v in enumerate(vals)]
            if len(pts) > 1:
                if s.get("fill"):
                    poly = [pts[0][0], y1] + [c for p in pts for c in p] + [pts[-1][0], y1]
                    self.create_polygon(poly, fill=_blend(s["color"], COLORS["bg_card"], 0.82), outline="")
                flat = [c for p in pts for c in p]
                self.create_line(*flat, fill=s["color"], width=2, capstyle="round", joinstyle="round")
            if show_points:
                for (px, py), v in zip(pts, vals):
                    r = 3.5
                    self.create_oval(px - r, py - r, px + r, py + r, fill=COLORS["bg_card"],
                                     outline=s["color"], width=2)

        if not has_data:
            self.create_text((x0 + x1) / 2, (y0 + y1) / 2, text=self.empty_text,
                             fill=COLORS["text_muted"], font=FONTS["body_sm"])

        self._draw_legend()
        if self._hover_idx is not None:
            self._draw_hover(self._hover_idx)

    def _draw_legend(self) -> None:
        self._legend_boxes = []
        x, y = self.PAD_L, 14
        limit = self.winfo_width() - self.PAD_R
        for s in self.series:
            off = s["name"] in self.hidden
            color = COLORS["text_muted"] if off else s["color"]
            label = f"{s['name']}  ({sum(s['values']):g})"
            t = self.create_text(x + 22, y, text=label, anchor="w", fill=color, font=FONTS["caption"])
            bbox = self.bbox(t)
            if x > self.PAD_L and bbox[2] > limit:
                self.delete(t)
                x, y = self.PAD_L, y + 18
                t = self.create_text(x + 22, y, text=label, anchor="w", fill=color, font=FONTS["caption"])
                bbox = self.bbox(t)
            self.create_line(x, y, x + 16, y, fill=color, width=2)
            self.create_oval(x + 5, y - 3, x + 11, y + 3, fill=COLORS["bg_card"], outline=color, width=2)
            self._legend_boxes.append((x - 2, y - 10, bbox[2] + 6, y + 10, s["name"]))
            x = bbox[2] + 20

    # ── interaction ──────────────────────────────────────────────────────────
    def _on_click(self, event) -> None:
        for bx0, by0, bx1, by1, name in self._legend_boxes:
            if bx0 <= event.x <= bx1 and by0 <= event.y <= by1:
                if name in self.hidden:
                    self.hidden.discard(name)
                else:
                    self.hidden.add(name)
                self.redraw()
                return

    def _on_motion(self, event) -> None:
        n = len(self.dates)
        if n == 0:
            return
        x0, y0, x1, y1 = self._plot_box()
        over_legend = any(bx0 <= event.x <= bx1 and by0 <= event.y <= by1
                          for bx0, by0, bx1, by1, _ in self._legend_boxes)
        wanted_cursor = "hand2" if over_legend else ""
        if wanted_cursor != self._cur_cursor:
            self.config(cursor=wanted_cursor)
            self._cur_cursor = wanted_cursor
        if not (x0 - 6 <= event.x <= x1 + 6 and y0 - 6 <= event.y <= y1 + 6):
            self._clear_hover()
            return
        idx = round((event.x - x0) / (x1 - x0) * (n - 1)) if n > 1 else 0
        idx = max(0, min(n - 1, idx))
        if idx != self._hover_idx:
            self._hover_idx = idx
            self._draw_hover(idx)

    def _on_leave(self, _event) -> None:
        self._clear_hover()
        if self._cur_cursor:
            self.config(cursor="")
            self._cur_cursor = ""

    def _clear_hover(self) -> None:
        if self._hover_idx is not None:
            self._hover_idx = None
            self.delete("hover")

    def _draw_hover(self, idx: int) -> None:
        self.delete("hover")
        x0, y0, x1, y1 = self._plot_box()
        x = self._x(idx)
        self.create_line(x, y0, x, y1, fill=COLORS["text_muted"], dash=(3, 3), tags="hover")
        rows = [(s["name"], s["color"], s["values"][idx]) for s in self.series if s["name"] not in self.hidden]
        for _, color, v in rows:
            y = self._y(v)
            self.create_oval(x - 5, y - 5, x + 5, y + 5, fill=color, outline=COLORS["bg_card"], width=2, tags="hover")
        if not rows:
            return
        line_h, pad = 16, 8
        w = max(130, 22 + 7 * max(len(f"{n}: {v:g}") for n, _, v in rows))
        h = pad * 2 + line_h * (len(rows) + 1)
        bx = x + 14 if x + 14 + w < self.winfo_width() - 4 else x - 14 - w
        by = max(y0, min(y1 - h, y0 + 6))
        self.create_rectangle(bx, by, bx + w, by + h, fill=COLORS["bg_dark"], outline=COLORS["border"], tags="hover")
        self.create_text(bx + pad, by + pad + 6, text=self.dates[idx], anchor="w", fill=COLORS["text_primary"],
                         font=FONTS["label_bold"], tags="hover")
        for r, (name, color, v) in enumerate(rows, start=1):
            yy = by + pad + 6 + r * line_h
            self.create_oval(bx + pad, yy - 3, bx + pad + 6, yy + 3, fill=color, outline="", tags="hover")
            self.create_text(bx + pad + 12, yy, text=f"{name}: {v:g}", anchor="w", fill=COLORS["text_secondary"],
                             font=FONTS["caption"], tags="hover")


def _blend(fg: str, bg: str, ratio: float) -> str:
    """Mix `fg` into `bg` (ratio=1 -> pure bg) for translucent-looking area fills."""
    try:
        f = [int(fg[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(bg[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(int(fc * (1 - ratio) + bc * ratio) for fc, bc in zip(f, b))
    except Exception:
        return bg


# ── Cards & KPI tiles ─────────────────────────────────────────────────────────

def chart_card(parent, title: str, subtitle: str, dates: List[str], series: List[Dict[str, Any]],
               height: int = 230) -> tk.Frame:
    card = tk.Frame(parent, bg=COLORS["bg_card"], highlightbackground=COLORS["border"], highlightthickness=1)
    head = tk.Frame(card, bg=COLORS["bg_card"], padx=14, pady=10)
    head.pack(fill="x")
    tk.Label(head, text=title, font=FONTS["label_bold"], fg=COLORS["text_primary"],
             bg=COLORS["bg_card"]).pack(side="left")
    tk.Label(head, text=subtitle, font=FONTS["caption"], fg=COLORS["text_muted"],
             bg=COLORS["bg_card"]).pack(side="left", padx=(10, 0))
    LineChart(card, dates, series, height=height).pack(fill="x", padx=8, pady=(0, 8))
    return card


def _kpi(parent, label: str, value: int, color: str, delta_pct: Optional[float], invert: bool = False) -> tk.Frame:
    card = tk.Frame(parent, bg=COLORS["bg_card"], highlightbackground=COLORS["border"], highlightthickness=1)
    tk.Frame(card, height=3, bg=color).pack(fill="x")
    inner = tk.Frame(card, bg=COLORS["bg_card"], padx=14, pady=10)
    inner.pack(fill="both", expand=True)
    tk.Label(inner, text=label, font=FONTS["caption"], fg=COLORS["text_secondary"],
             bg=COLORS["bg_card"]).pack(anchor="w")
    tk.Label(inner, text=f"{value:,}", font=FONTS["heading_lg"], fg=color, bg=COLORS["bg_card"]).pack(anchor="w")
    if delta_pct is None:
        txt, col = "no prior data", COLORS["text_muted"]
    else:
        up = delta_pct > 0
        good = (not up) if invert else up
        arrow = "▲" if up else ("▼" if delta_pct < 0 else "•")
        txt = f"{arrow} {abs(delta_pct):.0f}% vs prev"
        col = COLORS["text_muted"] if delta_pct == 0 else (COLORS["success"] if good else COLORS["danger"])
    tk.Label(inner, text=txt, font=FONTS["caption"], fg=col, bg=COLORS["bg_card"]).pack(anchor="w")
    return card


def _totals(ts_now: Dict, ts_prev: Dict, key: str):
    cur = sum(ts_now["series"][key])
    prev = sum(ts_prev["series"][key]) if ts_prev else 0
    pct = None if prev == 0 and cur == 0 else (100.0 if prev == 0 else (cur - prev) * 100.0 / prev)
    return cur, pct


def _split_periods(days: int):
    """Fetch 2*days of data and split into (current, previous) series dicts."""
    full = db.get_metrics_timeseries(days=days * 2)
    cur = {"dates": full["dates"][days:], "series": {k: v[days:] for k, v in full["series"].items()}}
    prev = {"dates": full["dates"][:days], "series": {k: v[:days] for k, v in full["series"].items()}}
    return cur, prev


def _section(parent, text: str, pady=(18, 8)) -> None:
    tk.Label(parent, text=text, font=FONTS["label_bold"], fg=COLORS["text_secondary"],
             bg=COLORS["bg_dark"]).pack(anchor="w", pady=pady)


def _kpi_row(parent, ts, prev) -> None:
    row = tk.Frame(parent, bg=COLORS["bg_dark"])
    row.pack(fill="x")
    specs = [
        ("Sessions", "sessions", C_BLUE, False),
        ("Commits", "commits", C_GREEN, False),
        ("Vulnerabilities", "vulnerabilities", C_ORANGE, True),
        ("Code errors", "errors", C_YELLOW, True),
        ("Commit failures", "commit_failures", C_RED, True),
        ("Push failures", "push_failures", C_PINK, True),
    ]
    for i, (label, key, color, invert) in enumerate(specs):
        total, pct = _totals(ts, prev, key)
        row.grid_columnconfigure(i, weight=1, uniform="kpi")
        _kpi(row, label, total, color, pct, invert).grid(row=0, column=i, sticky="nsew", padx=4, pady=4)


def _chart_grid(parent, ts, days: int, height: int = 230) -> None:
    s = ts["series"]
    d = ts["dates"]
    sub = f"last {days} days"
    grid = tk.Frame(parent, bg=COLORS["bg_dark"])
    grid.pack(fill="x")
    grid.grid_columnconfigure(0, weight=1, uniform="cg")
    grid.grid_columnconfigure(1, weight=1, uniform="cg")
    cards = [
        chart_card(grid, "Usage", sub, d, [
            {"name": "Sessions", "color": C_BLUE, "values": s["sessions"], "fill": True},
            {"name": "Active users", "color": C_PURPLE, "values": s["active_users"]},
            {"name": "AI generations", "color": C_TEAL, "values": s["ai_generations"]},
        ], height),
        chart_card(grid, "Commit activity", sub, d, [
            {"name": "Commits", "color": C_GREEN, "values": s["commits"], "fill": True},
            {"name": "Files committed", "color": C_YELLOW, "values": s["files_committed"]},
            {"name": "Pushes", "color": C_BLUE, "values": s["pushes"]},
        ], height),
        chart_card(grid, "Vulnerabilities & code issues detected", sub, d, [
            {"name": "Vulnerabilities", "color": C_ORANGE, "values": s["vulnerabilities"], "fill": True},
            {"name": "Errors", "color": C_RED, "values": s["errors"]},
            {"name": "Warnings", "color": C_YELLOW, "values": s["warnings"]},
            {"name": "Scans", "color": C_TEAL, "values": s["scans"]},
        ], height),
        chart_card(grid, "Failures", sub, d, [
            {"name": "Commit failures", "color": C_RED, "values": s["commit_failures"], "fill": True},
            {"name": "Push failures", "color": C_PINK, "values": s["push_failures"]},
        ], height),
    ]
    for i, c in enumerate(cards):
        c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=4, pady=4)


# ── Public builders ───────────────────────────────────────────────────────────

def build_admin_overview(parent, days: int = 14) -> None:
    """KPI tiles + the four line charts, for the admin dashboard page."""
    ts, prev = _split_periods(days)
    _section(parent, f"SYSTEM HEALTH — LAST {days} DAYS", (24, 8))
    _kpi_row(parent, ts, prev)
    _section(parent, "TRENDS", (14, 4))
    _chart_grid(parent, ts, days, height=210)


def build_admin_analytics(parent, days: int = 30) -> None:
    """Full analytics page with a range selector, KPIs, line charts, per-user lines and tables."""
    holder = tk.Frame(parent, bg=COLORS["bg_dark"])
    holder.pack(fill="x")

    def render(d: int) -> None:
        for w in holder.winfo_children():
            w.destroy()
        ctrl = tk.Frame(holder, bg=COLORS["bg_dark"])
        ctrl.pack(fill="x", pady=(0, 6))
        tk.Label(ctrl, text="Range", font=FONTS["label_bold"], fg=COLORS["text_secondary"],
                 bg=COLORS["bg_dark"]).pack(side="left", padx=(0, 8))
        for opt in (7, 14, 30, 90):
            active = opt == d
            b = tk.Button(ctrl, text=f"{opt}d", font=FONTS["caption"], relief="flat", bd=0, cursor="hand2",
                          padx=12, pady=4, fg="white" if active else COLORS["text_secondary"],
                          bg=COLORS["accent"] if active else COLORS["bg_medium"],
                          command=lambda o=opt: render(o))
            b.pack(side="left", padx=(0, 4))

        ts, prev = _split_periods(d)
        _kpi_row(holder, ts, prev)
        _section(holder, "TRENDS", (14, 4))
        _chart_grid(holder, ts, d)

        # per-user commits as lines
        users = db.get_user_commit_series(days=d, limit=6)
        _section(holder, "COMMITS BY USER (TOP 6)", (14, 4))
        chart_card(holder, "Commits per user", f"last {d} days", users["dates"],
                   [{"name": name, "color": USER_PALETTE[i % len(USER_PALETTE)], "values": vals}
                    for i, (name, vals) in enumerate(users["series"].items())], height=240).pack(fill="x", padx=4, pady=4)

        _security_table(holder)
        _daily_table(holder, ts)

    render(days)


def _table(parent, headers: List[tuple], rows: List[List[str]], empty: str) -> None:
    box = tk.Frame(parent, bg=COLORS["bg_card"], highlightbackground=COLORS["border"], highlightthickness=1)
    box.pack(fill="x", padx=4, pady=4)
    grid = tk.Frame(box, bg=COLORS["bg_card"])
    grid.pack(fill="x")
    for c, (_t, w) in enumerate(headers):
        grid.grid_columnconfigure(c, weight=w, uniform="tbl")
    for c, (text, _w) in enumerate(headers):
        tk.Label(grid, text=text, font=FONTS["label_bold"], fg=COLORS["text_secondary"], bg=COLORS["bg_medium"],
                 anchor="w", padx=8, pady=6).grid(row=0, column=c, sticky="ew")
    if not rows:
        tk.Label(box, text=empty, font=FONTS["body_sm"], fg=COLORS["text_muted"], bg=COLORS["bg_card"],
                 padx=10, pady=12).pack(anchor="w")
    for i, r in enumerate(rows, start=1):
        for c, val in enumerate(r):
            tk.Label(grid, text=val, font=FONTS["body_sm"], fg=COLORS["text_primary"], bg=COLORS["bg_card"],
                     anchor="w", padx=8, pady=6).grid(row=i, column=c, sticky="ew")
        for c in range(len(headers)):
            tk.Frame(grid, height=1, bg=COLORS["border"]).grid(row=i, column=c, sticky="sew")


def _security_table(parent) -> None:
    _section(parent, "RECENT SECURITY FINDINGS", (14, 4))
    events = db.get_recent_security_events(limit=8)
    rows = [[e["created_at"][:16], e.get("username") or "-", e.get("repo_name") or "-",
             str(e["files"]), str(e["security"]), str(e["errors"])] for e in events]
    _table(parent, [("When (UTC)", 18), ("User", 14), ("Repository", 22), ("Files", 8), ("Vulnerabilities", 15),
                    ("Errors", 8)], rows, "No vulnerabilities detected so far.")


def _daily_table(parent, ts) -> None:
    _section(parent, "DAILY BREAKDOWN — MOST RECENT 7 DAYS", (14, 4))
    s = ts["series"]
    rows = []
    for i in range(len(ts["dates"]) - 1, max(-1, len(ts["dates"]) - 8), -1):
        rows.append([ts["dates"][i], str(s["sessions"][i]), str(s["commits"][i]), str(s["pushes"][i]),
                     str(s["vulnerabilities"][i]), str(s["errors"][i]),
                     str(s["commit_failures"][i] + s["push_failures"][i])])
    _table(parent, [("Date", 14), ("Sessions", 10), ("Commits", 10), ("Pushes", 10),
                    ("Vulns", 10), ("Errors", 10), ("Failures", 10)], rows, "No data yet.")


def user_activity_chart(parent, user_id: int, days: int = 30, height: int = 200) -> tk.Frame:
    """Line chart of one user's own commits / sessions (used on the user overview page)."""
    ts = db.get_metrics_timeseries(days=days, user_id=user_id)
    s = ts["series"]
    return chart_card(parent, "Your activity", f"last {days} days", ts["dates"], [
        {"name": "Commits", "color": C_GREEN, "values": s["commits"], "fill": True},
        {"name": "Sessions", "color": C_BLUE, "values": s["sessions"]},
        {"name": "Vulnerabilities found", "color": C_ORANGE, "values": s["vulnerabilities"]},
        {"name": "Failures", "color": C_RED,
         "values": [a + b for a, b in zip(s["commit_failures"], s["push_failures"])]},
    ], height)
