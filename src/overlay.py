"""Demo overlay: an always-on-top, click-through panel showing what the
keyboard + mouse are doing to the virtual controller, live.

Runs Tk on its own thread (every Tk call stays on that thread) and polls a
`source()` callable ~60x/s for a telemetry dict, so the 500 Hz pad loop is
never blocked by drawing. Works over borderless/windowed games (Game Pass PC
titles default to borderless); exclusive fullscreen draws over it.

Telemetry dict keys:
    mode     "aim" | "menu" | "native"
    output   "xbox" | "ds4"
    lx ly rx ry lt rt   floats
    buttons  {name: bool}
    demand rate max_rate pending   deg/s, deg/s, deg/s, deg
    saturated  bool
    deadzone   game inner deadzone (0..1)
    hz         pad update rate
"""

import ctypes
import threading
import time
from collections import deque

BG, PANEL, FG, DIM = "#0f1216", "#1a1f26", "#e8edf2", "#5c6773"
GREEN, AMBER, RED, BLUE = "#3ddc84", "#ffb020", "#ff5a5f", "#4ea8ff"

MODE_STYLE = {
    "aim":    ("CONTROLLER  ·  MOUSE = RIGHT STICK", GREEN),
    "menu":   ("CONTROLLER  ·  MENU MOUSE", AMBER),
    "native": ("NATIVE KEYBOARD + MOUSE", DIM),
}
CHIPS = ("A", "B", "X", "Y", "LB", "RB", "LS", "RS", "BACK", "START",
         "DUP", "DDOWN", "DLEFT", "DRIGHT")
LABELS = {
    "xbox": {"BACK": "VIEW", "START": "MENU", "DUP": "↑", "DDOWN": "↓",
             "DLEFT": "←", "DRIGHT": "→"},
    "ds4": {"A": "✕", "B": "○", "X": "□", "Y": "△",
            "LB": "L1", "RB": "R1", "LS": "L3", "RS": "R3", "BACK": "SHR",
            "START": "OPT", "DUP": "↑", "DDOWN": "↓",
            "DLEFT": "←", "DRIGHT": "→"},
}
TRIGGER = {"xbox": ("LT", "RT"), "ds4": ("L2", "R2")}

W, H = 440, 250


class Overlay:
    def __init__(self, source, position="top-left", scale=1.0, alpha=0.95):
        self.source = source
        self.position = position
        self.s = scale
        self.alpha = alpha
        self.visible = True
        self._trail = deque(maxlen=28)
        self._thread = None
        self.root = None

    def toggle(self):
        self.visible = not self.visible   # picked up by the Tk thread

    def start(self):
        self._thread = threading.Thread(target=self._run, name="overlay", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ tk
    def _run(self):
        import tkinter as tk
        s = self.s
        root = self.root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", self.alpha)
        root.configure(bg=BG)
        w, h = int(W * s), int(H * s)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        m = int(24 * s)
        x = m if "left" in self.position else sw - w - m
        y = m if "top" in self.position else sh - h - m
        root.geometry(f"{w}x{h}+{x}+{y}")
        self.cv = tk.Canvas(root, width=w, height=h, bg=BG, highlightthickness=0)
        self.cv.pack()
        root.update_idletasks()
        self._click_through(root)
        self._shown = True
        self._last_top = 0.0
        self._frame()
        root.mainloop()

    @staticmethod
    def _click_through(root):
        u = ctypes.windll.user32
        hwnd = u.GetParent(root.winfo_id()) or root.winfo_id()
        ex = u.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
        # LAYERED | TRANSPARENT (clicks pass through) | TOOLWINDOW | NOACTIVATE
        u.SetWindowLongW(hwnd, -20, ex | 0x80000 | 0x20 | 0x80 | 0x08000000)

    def _frame(self):
        try:
            if self.visible != self._shown:
                (self.root.deiconify if self.visible else self.root.withdraw)()
                self._shown = self.visible
                if self.visible:
                    self._click_through(self.root)
            now = time.monotonic()
            if now - self._last_top > 1.0:     # games like to steal topmost
                self.root.attributes("-topmost", True)
                self._last_top = now
            if self.visible:
                self.draw(self.source())
        finally:
            self.root.after(16, self._frame)

    # ---------------------------------------------------------------- draw
    def draw(self, t):
        cv, s = self.cv, self.s
        cv.delete("all")
        f = lambda size, bold=False: ("Segoe UI", int(size * s), "bold" if bold else "normal")
        P = lambda *v: [int(a * s) for a in v]

        cv.create_rectangle(*P(0, 0, W, H), fill=BG, outline="")
        title, color = MODE_STYLE.get(t["mode"], MODE_STYLE["native"])
        cv.create_rectangle(*P(12, 12, 20, 34), fill=color, outline="")
        cv.create_text(*P(28, 23), text=title, fill=color, anchor="w", font=f(11, True))
        cv.create_text(*P(W - 14, 23), anchor="e", fill=DIM, font=f(9),
                       text=f"{t['output'].upper()}  {t['hz']:.0f} Hz")

        live = t["mode"] != "native"
        # Sticks
        self._stick(P(70, 105), 46 * s, t["lx"], t["ly"], "WASD", live, 0.0, None)
        if t["mode"] == "aim":
            self._trail.append((t["rx"], t["ry"]))
        else:
            self._trail.clear()
        self._stick(P(190, 105), 46 * s, t["rx"], t["ry"], "MOUSE", live,
                    t["deadzone"], self._trail)

        # Turn rate: what the mouse asked for vs what a stick can deliver.
        bx0, by, bw = 262, 70, 160
        cv.create_text(*P(bx0, by - 14), text="TURN RATE", anchor="w", fill=DIM, font=f(8, True))
        cv.create_rectangle(*P(bx0, by, bx0 + bw, by + 14), fill=PANEL, outline="")
        mx = max(t["max_rate"], 1.0)
        frac = min(t["rate"] / mx, 1.0)
        bar_c = RED if t["saturated"] else BLUE
        if frac > 0:
            cv.create_rectangle(*P(bx0, by, bx0 + bw * frac, by + 14), fill=bar_c, outline="")
        if t["saturated"]:
            cv.create_text(*P(bx0 + bw - 4, by + 7), text="MAX", anchor="e", fill=FG, font=f(7, True))
        cv.create_text(*P(bx0, by + 26), anchor="w", fill=FG, font=f(9),
                       text=f"{t['demand']:.0f} asked → {t['rate']:.0f} / {mx:.0f}°/s")
        cv.create_text(*P(bx0, by + 44), anchor="w", fill=AMBER if t["pending"] > 1 else DIM,
                       font=f(9), text=f"carryover {t['pending']:.1f}°")

        # Triggers
        lt_name, rt_name = TRIGGER.get(t["output"], TRIGGER["xbox"])
        for i, (name, v) in enumerate(((lt_name, t["lt"]), (rt_name, t["rt"]))):
            x0 = bx0 + i * 82
            ty = 140
            cv.create_text(*P(x0, ty), text=name, anchor="w", fill=DIM, font=f(8, True))
            cv.create_rectangle(*P(x0 + 24, ty - 6, x0 + 74, ty + 6), fill=PANEL, outline="")
            if v > 0:
                cv.create_rectangle(*P(x0 + 24, ty - 6, x0 + 24 + 50 * v, ty + 6),
                                    fill=GREEN, outline="")

        # Buttons
        labels = LABELS.get(t["output"], LABELS["xbox"])
        x, y = 12, 200
        for b in CHIPS:
            text = labels.get(b, b)
            wch = 10 + 6 * len(text)
            if x + wch > W - 12:
                x, y = 12, y + 26
            on = t["buttons"].get(b)
            cv.create_rectangle(*P(x, y, x + wch, y + 22), outline="",
                                fill=GREEN if on else PANEL)
            cv.create_text(*P(x + wch / 2, y + 11), text=text, font=f(8, True),
                           fill=BG if on else DIM)
            x += wch + 4

    def _stick(self, c, r, x, y, label, live, deadzone, trail):
        cv, s = self.cv, self.s
        cx, cy = c
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=PANEL, outline="")
        if deadzone > 0:
            d = r * deadzone
            cv.create_oval(cx - d, cy - d, cx + d, cy + d, outline=DIM, dash=(2, 2))
        cv.create_line(cx - r, cy, cx + r, cy, fill="#252b33")
        cv.create_line(cx, cy - r, cx, cy + r, fill="#252b33")
        if trail:
            n = len(trail)
            for i, (tx, ty) in enumerate(trail):
                rr = max(1.0, 3.0 * s * (i + 1) / n)
                px, py = cx + tx * r, cy - ty * r
                cv.create_oval(px - rr, py - rr, px + rr, py + rr, fill="#2b5f8f", outline="")
        dot = 7 * s
        px, py = cx + x * r, cy - y * r
        cv.create_oval(px - dot, py - dot, px + dot, py + dot, outline="",
                       fill=(GREEN if (x or y) else FG) if live else DIM)
        cv.create_text(cx, cy + r + 12 * s, text=label, fill=DIM,
                       font=("Segoe UI", int(8 * s), "bold"))
