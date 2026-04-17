"""GUI - Modern dark-themed interface for ActionShot."""

import json
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk, ImageDraw

from .recorder import Recorder
from .replay import Replayer
from .generator import ScriptGenerator
from .ai_agent import AIAgent


# ── Color palette ─────────────────────────────────────────────────────

C = {
    "bg":           "#0c0c1d",
    "bg_card":      "#141432",
    "bg_card_alt":  "#1a1a3e",
    "bg_input":     "#0a0a1a",
    "accent":       "#7c3aed",
    "accent_hover": "#9b5de5",
    "accent_dim":   "#5b21b6",
    "red":          "#ef4444",
    "red_glow":     "#dc2626",
    "green":        "#22c55e",
    "green_dim":    "#16a34a",
    "blue":         "#3b82f6",
    "yellow":       "#eab308",
    "text":         "#e2e8f0",
    "text_dim":     "#94a3b8",
    "text_muted":   "#475569",
    "border":       "#1e1e4a",
    "border_light": "#2d2d6b",
    "white":        "#ffffff",
}

FONT = "Segoe UI"
MONO = "Cascadia Code"

# Try Cascadia, fall back to Consolas
try:
    _test = tk.Tk()
    _test.withdraw()
    _f = tk.font.Font(family=MONO, size=10)
    if MONO.lower() not in _f.actual()["family"].lower():
        MONO = "Consolas"
    _test.destroy()
except Exception:
    MONO = "Consolas"


# ── Custom widgets ────────────────────────────────────────────────────

class GlowButton(tk.Canvas):
    """Custom button with hover glow effect."""

    def __init__(self, parent, text="", icon="", color=C["accent"],
                 hover_color=C["accent_hover"], text_color=C["white"],
                 command=None, width=160, height=42, font_size=11, **kw):
        super().__init__(parent, width=width, height=height,
                         bg=parent["bg"], highlightthickness=0, **kw)

        self._text = text
        self._icon = icon
        self._color = color
        self._hover_color = hover_color
        self._text_color = text_color
        self._command = command
        self._w = width
        self._h = height
        self._font_size = font_size
        self._hovered = False
        self._pressed = False

        self._draw()

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _draw(self):
        self.delete("all")
        c = self._hover_color if self._hovered else self._color
        r = 8  # corner radius

        # Shadow
        if self._hovered:
            self._round_rect(2, 3, self._w - 2, self._h - 1, r, fill="#00000044", outline="")

        # Button body
        self._round_rect(0, 0, self._w - 2, self._h - 3, r, fill=c, outline="")

        # Highlight line at top
        if self._hovered:
            self.create_line(r, 1, self._w - r - 2, 1, fill=self._hover_color, width=1)

        # Text
        label = f"{self._icon}  {self._text}" if self._icon else self._text
        y_off = 1 if self._pressed else 0
        self.create_text(
            self._w // 2, self._h // 2 - 1 + y_off,
            text=label, fill=self._text_color,
            font=(FONT, self._font_size, "bold"),
        )

    def _round_rect(self, x1, y1, x2, y2, r, **kw):
        points = [
            x1 + r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r,
            x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kw)

    def _on_enter(self, e):
        self._hovered = True
        self._draw()

    def _on_leave(self, e):
        self._hovered = False
        self._pressed = False
        self._draw()

    def _on_press(self, e):
        self._pressed = True
        self._draw()

    def _on_release(self, e):
        self._pressed = False
        self._draw()
        if self._command and self._hovered:
            self._command()

    def set_text(self, text):
        self._text = text
        self._draw()

    def set_color(self, color, hover_color=None):
        self._color = color
        self._hover_color = hover_color or color
        self._draw()


class PulsingDot(tk.Canvas):
    """Animated recording indicator."""

    def __init__(self, parent, size=14, **kw):
        super().__init__(parent, width=size, height=size,
                         bg=parent["bg"], highlightthickness=0, **kw)
        self._size = size
        self._alpha = 1.0
        self._growing = False
        self._active = False
        self._draw_idle()

    def _draw_idle(self):
        self.delete("all")
        r = self._size // 2 - 2
        cx, cy = self._size // 2, self._size // 2
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=C["text_muted"], outline="")

    def start(self):
        self._active = True
        self._pulse()

    def stop(self):
        self._active = False
        self._draw_idle()

    def _pulse(self):
        if not self._active:
            return
        self.delete("all")
        r = self._size // 2 - 2
        cx, cy = self._size // 2, self._size // 2

        # Outer glow
        gr = int(r + 3 * self._alpha)
        glow_colors = ["#dc26264d", "#dc262633", "#dc262619"]
        for i, gc in enumerate(glow_colors):
            er = gr + i * 2
            self.create_oval(cx - er, cy - er, cx + er, cy + er, fill="", outline=gc, width=1)

        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=C["red"], outline="")

        if self._growing:
            self._alpha += 0.08
            if self._alpha >= 1.0:
                self._growing = False
        else:
            self._alpha -= 0.08
            if self._alpha <= 0.2:
                self._growing = True

        self.after(50, self._pulse)


class StepCard(tk.Frame):
    """A single step displayed as a card in the step list."""

    def __init__(self, parent, step_num, action, description, selected=False, on_click=None, **kw):
        bg = C["accent_dim"] if selected else C["bg_card"]
        super().__init__(parent, bg=bg, padx=10, pady=6, **kw)

        self._on_click = on_click
        self._selected = selected
        self._bg = bg

        top = tk.Frame(self, bg=bg)
        top.pack(fill="x")

        # Step number badge
        action_colors = {
            "click": C["red"], "drag": "#FF6600", "scroll": C["blue"],
            "keypress": C["yellow"],
        }
        badge_color = C["text_muted"]
        for key, col in action_colors.items():
            if key in action:
                badge_color = col
                break

        tk.Label(top, text=f" {step_num:03d} ", bg=badge_color, fg=C["white"],
                 font=(MONO, 8, "bold"), padx=4, pady=1).pack(side="left")

        action_short = action.replace("_click", "").replace("left", "L").replace("right", "R").replace("middle", "M")
        tk.Label(top, text=f"  {action_short}", bg=bg, fg=badge_color,
                 font=(MONO, 9, "bold")).pack(side="left")

        # Description
        desc_text = description[:55] + "..." if len(description) > 55 else description
        tk.Label(self, text=desc_text, bg=bg, fg=C["text_dim"] if not selected else C["text"],
                 font=(FONT, 9), anchor="w").pack(fill="x", pady=(2, 0))

        # Bind click on all children
        self.bind("<Button-1>", self._click)
        for child in self.winfo_children():
            child.bind("<Button-1>", self._click)
            for sub in child.winfo_children():
                sub.bind("<Button-1>", self._click)

    def _click(self, e=None):
        if self._on_click:
            self._on_click()


# ── Main GUI ──────────────────────────────────────────────────────────

class ActionShotGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ActionShot")
        self.root.geometry("960x700")
        self.root.minsize(800, 600)
        self.root.configure(bg=C["bg"])

        # Try to set dark title bar on Windows
        try:
            from ctypes import windll, byref, c_int
            self.root.update()
            hwnd = windll.user32.GetParent(self.root.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(2)), 4)
        except Exception:
            pass

        self.recorder = None
        self.recording = False
        self._preview_images = []
        self._step_cards = []
        self._selected_step_idx = -1
        self._recording_start_time = None
        self._timer_id = None

        self._build_ui()

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────
        topbar = tk.Frame(self.root, bg=C["bg_card"], height=56)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        # Logo
        logo_frame = tk.Frame(topbar, bg=C["bg_card"])
        logo_frame.pack(side="left", padx=20)

        tk.Label(logo_frame, text="ActionShot", bg=C["bg_card"], fg=C["accent"],
                 font=(FONT, 18, "bold")).pack(side="left")
        tk.Label(logo_frame, text="  v0.1", bg=C["bg_card"], fg=C["text_muted"],
                 font=(FONT, 10)).pack(side="left", pady=(4, 0))

        # Recording indicator in top bar
        rec_frame = tk.Frame(topbar, bg=C["bg_card"])
        rec_frame.pack(side="right", padx=20)

        self._rec_dot = PulsingDot(rec_frame)
        self._rec_dot.pack(side="left", padx=(0, 8))

        self._rec_status = tk.Label(rec_frame, text="Idle", bg=C["bg_card"],
                                    fg=C["text_muted"], font=(FONT, 10))
        self._rec_status.pack(side="left")

        self._rec_timer = tk.Label(rec_frame, text="", bg=C["bg_card"],
                                   fg=C["text_dim"], font=(MONO, 10))
        self._rec_timer.pack(side="left", padx=(10, 0))

        self._rec_steps = tk.Label(rec_frame, text="", bg=C["bg_card"],
                                   fg=C["text_dim"], font=(MONO, 10))
        self._rec_steps.pack(side="left", padx=(10, 0))

        # Separator
        tk.Frame(self.root, bg=C["border"], height=1).pack(fill="x")

        # ── Main content ─────────────────────────────────────────────
        main = tk.Frame(self.root, bg=C["bg"])
        main.pack(fill="both", expand=True, padx=16, pady=12)

        # Left column
        left = tk.Frame(main, bg=C["bg"])
        left.pack(side="left", fill="both", expand=True)

        # ── Record card ──────────────────────────────────────────────
        rec_card = tk.Frame(left, bg=C["bg_card"], padx=20, pady=16)
        rec_card.pack(fill="x", pady=(0, 10))

        rec_top = tk.Frame(rec_card, bg=C["bg_card"])
        rec_top.pack(fill="x")

        tk.Label(rec_top, text="Recording", bg=C["bg_card"], fg=C["text"],
                 font=(FONT, 13, "bold")).pack(side="left")

        # Output dir (compact)
        dir_f = tk.Frame(rec_top, bg=C["bg_card"])
        dir_f.pack(side="right")
        self.output_var = tk.StringVar(value="recordings")
        tk.Label(dir_f, text="Output:", bg=C["bg_card"], fg=C["text_muted"],
                 font=(FONT, 9)).pack(side="left")
        out_entry = tk.Entry(dir_f, textvariable=self.output_var, width=16,
                             bg=C["bg_input"], fg=C["text"], insertbackground=C["text"],
                             font=(MONO, 9), bd=0, relief="flat")
        out_entry.pack(side="left", padx=(5, 3), ipady=3)

        # Record button
        btn_row = tk.Frame(rec_card, bg=C["bg_card"])
        btn_row.pack(fill="x", pady=(12, 4))

        self.record_btn = GlowButton(
            btn_row, text="Start Recording", icon="\u23fa",
            color=C["accent"], hover_color=C["accent_hover"],
            command=self._toggle_recording, width=200, height=46, font_size=12,
        )
        self.record_btn.pack(side="left")

        # Options
        self._video_var = tk.BooleanVar(value=False)
        self._ocr_var = tk.BooleanVar(value=True)

        opt_f = tk.Frame(btn_row, bg=C["bg_card"])
        opt_f.pack(side="left", padx=(20, 0))
        tk.Checkbutton(opt_f, text="Video", variable=self._video_var,
                       bg=C["bg_card"], fg=C["text_dim"], selectcolor=C["bg_input"],
                       activebackground=C["bg_card"], activeforeground=C["text"],
                       font=(FONT, 9)).pack(anchor="w")
        tk.Checkbutton(opt_f, text="OCR", variable=self._ocr_var,
                       bg=C["bg_card"], fg=C["text_dim"], selectcolor=C["bg_input"],
                       activebackground=C["bg_card"], activeforeground=C["text"],
                       font=(FONT, 9)).pack(anchor="w")

        # Hotkey hint
        tk.Label(rec_card, text="Win+Shift+R  toggle    Win+Shift+P  pause    ESC  stop",
                 bg=C["bg_card"], fg=C["text_muted"], font=(MONO, 8)).pack(anchor="w", pady=(4, 0))

        # ── Tools card ───────────────────────────────────────────────
        tools_card = tk.Frame(left, bg=C["bg_card"], padx=20, pady=16)
        tools_card.pack(fill="x", pady=(0, 10))

        tk.Label(tools_card, text="Tools", bg=C["bg_card"], fg=C["text"],
                 font=(FONT, 13, "bold")).pack(anchor="w")

        tools_grid = tk.Frame(tools_card, bg=C["bg_card"])
        tools_grid.pack(fill="x", pady=(10, 0))

        tools = [
            ("\u25b6", "Replay", C["green"], C["green_dim"], self._replay_session),
            ("\u2699", "Generate Script", C["blue"], "#2563eb", self._generate_script),
            ("\u2728", "AI Prompt", C["accent"], C["accent_dim"], self._generate_ai_prompt),
            ("\u21e1", "Export API", C["yellow"], "#ca8a04", self._export_api),
        ]

        for i, (icon, text, color, hover, cmd) in enumerate(tools):
            btn = GlowButton(tools_grid, text=text, icon=icon,
                             color=color, hover_color=hover,
                             command=cmd, width=145, height=38, font_size=10)
            btn.grid(row=0, column=i, padx=(0, 8))

        # ── Log ──────────────────────────────────────────────────────
        log_card = tk.Frame(left, bg=C["bg_card"], padx=16, pady=12)
        log_card.pack(fill="both", expand=True)

        log_header = tk.Frame(log_card, bg=C["bg_card"])
        log_header.pack(fill="x", pady=(0, 6))
        tk.Label(log_header, text="Activity Log", bg=C["bg_card"], fg=C["text"],
                 font=(FONT, 11, "bold")).pack(side="left")

        self.log_text = tk.Text(log_card, bg=C["bg_input"], fg=C["green"],
                                font=(MONO, 9), bd=0, wrap="word",
                                insertbackground=C["green"], padx=10, pady=8,
                                height=6)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")
        self._log("ActionShot ready.")

        # ── Separator ────────────────────────────────────────────────
        tk.Frame(main, bg=C["border"], width=1).pack(side="left", fill="y", padx=12)

        # ── Right column: session browser ────────────────────────────
        right = tk.Frame(main, bg=C["bg"], width=360)
        right.pack(side="left", fill="both", expand=True)
        right.pack_propagate(True)

        # Session header
        sess_header = tk.Frame(right, bg=C["bg"])
        sess_header.pack(fill="x", pady=(0, 8))
        tk.Label(sess_header, text="Sessions", bg=C["bg"], fg=C["text"],
                 font=(FONT, 13, "bold")).pack(side="left")

        GlowButton(sess_header, text="Refresh", color=C["bg_card_alt"],
                   hover_color=C["border_light"], text_color=C["text_dim"],
                   command=self._refresh_sessions, width=80, height=30, font_size=9
                   ).pack(side="right")

        # Session list
        sess_list_frame = tk.Frame(right, bg=C["bg_card"])
        sess_list_frame.pack(fill="x")

        sess_scroll = tk.Frame(sess_list_frame, bg=C["bg_card"])
        sess_scroll.pack(fill="x", padx=2, pady=2)

        self.session_listbox = tk.Listbox(
            sess_scroll, bg=C["bg_input"], fg=C["text"],
            font=(MONO, 9), height=5, bd=0, relief="flat",
            selectbackground=C["accent_dim"], selectforeground=C["white"],
            activestyle="none", highlightthickness=0,
        )
        self.session_listbox.pack(fill="x", padx=4, pady=4)
        self.session_listbox.bind("<<ListboxSelect>>", self._on_session_select)

        # Steps header
        tk.Label(right, text="Steps", bg=C["bg"], fg=C["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w", pady=(12, 6))

        # Scrollable step list
        step_container = tk.Frame(right, bg=C["bg_card"])
        step_container.pack(fill="x")

        self._step_canvas = tk.Canvas(step_container, bg=C["bg_card"], highlightthickness=0, height=160)
        step_scrollbar = tk.Scrollbar(step_container, orient="vertical", command=self._step_canvas.yview)
        self._step_inner = tk.Frame(self._step_canvas, bg=C["bg_card"])

        self._step_inner.bind("<Configure>",
                              lambda e: self._step_canvas.configure(scrollregion=self._step_canvas.bbox("all")))
        self._step_canvas.create_window((0, 0), window=self._step_inner, anchor="nw",
                                        tags="inner")
        self._step_canvas.configure(yscrollcommand=step_scrollbar.set)

        # Bind mouse wheel
        self._step_canvas.bind("<Enter>",
                               lambda e: self._step_canvas.bind_all("<MouseWheel>", self._on_step_scroll))
        self._step_canvas.bind("<Leave>",
                               lambda e: self._step_canvas.unbind_all("<MouseWheel>"))

        self._step_canvas.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        step_scrollbar.pack(side="right", fill="y")

        # Resize inner frame width when canvas resizes
        self._step_canvas.bind("<Configure>", self._on_step_canvas_resize)

        # Preview
        tk.Label(right, text="Preview", bg=C["bg"], fg=C["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w", pady=(12, 6))

        preview_container = tk.Frame(right, bg=C["bg_card"])
        preview_container.pack(fill="both", expand=True)

        self.preview_label = tk.Label(preview_container, bg=C["bg_input"],
                                      text="Select a step", fg=C["text_muted"],
                                      font=(FONT, 10))
        self.preview_label.pack(fill="both", expand=True, padx=4, pady=4)

        # Click preview to open full size
        self.preview_label.bind("<Double-Button-1>", self._open_preview_full)
        self._current_preview_path = None

        # ── State ────────────────────────────────────────────────────
        self._sessions = {}
        self._current_session_steps = []
        self._current_session_path = None

        self._refresh_sessions()

    # ── Logging ───────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {msg}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ── Recording timer ───────────────────────────────────────────────

    def _start_timer(self):
        self._recording_start_time = time.monotonic()
        self._update_timer()

    def _update_timer(self):
        if not self.recording:
            return
        elapsed = time.monotonic() - self._recording_start_time
        m, s = divmod(int(elapsed), 60)
        h, m = divmod(m, 60)
        self._rec_timer.configure(text=f"{h:02d}:{m:02d}:{s:02d}")

        if self.recorder and self.recorder.session:
            count = self.recorder.session.step_count
            self._rec_steps.configure(text=f"{count} steps")

        self._timer_id = self.root.after(500, self._update_timer)

    def _stop_timer(self):
        if self._timer_id:
            self.root.after_cancel(self._timer_id)
            self._timer_id = None
        self._rec_timer.configure(text="")
        self._rec_steps.configure(text="")

    # ── Recording ─────────────────────────────────────────────────────

    def _toggle_recording(self):
        if not self.recording:
            self.recording = True
            self.record_btn.set_text("Stop Recording")
            self.record_btn.set_color(C["red"], C["red_glow"])
            self.record_btn._icon = "\u23f9"
            self._rec_status.configure(text="Recording", fg=C["red"])
            self._rec_dot.start()
            self._log("Recording started")

            output = self.output_var.get()
            self.recorder = Recorder(
                output_dir=output,
                enable_video=self._video_var.get(),
                enable_ocr=self._ocr_var.get(),
            )

            def _record():
                self.recorder.start()
                self.root.after(0, self._on_recording_stopped)

            threading.Thread(target=_record, daemon=True).start()
            self._start_timer()
        else:
            if self.recorder:
                self.recorder.stop()

    def _on_recording_stopped(self):
        self.recording = False
        self.record_btn.set_text("Start Recording")
        self.record_btn.set_color(C["accent"], C["accent_hover"])
        self.record_btn._icon = "\u23fa"
        self._rec_status.configure(text="Idle", fg=C["text_muted"])
        self._rec_dot.stop()
        self._stop_timer()

        if self.recorder and self.recorder.session:
            self._log(f"Saved: {self.recorder.session.name} ({self.recorder.session.step_count} steps)")
        self._refresh_sessions()

    # ── Session browser ───────────────────────────────────────────────

    def _refresh_sessions(self):
        self.session_listbox.delete(0, "end")
        self._sessions.clear()

        output_dir = self.output_var.get()
        if not os.path.exists(output_dir):
            return

        sessions = []
        for name in os.listdir(output_dir):
            path = os.path.join(output_dir, name)
            summary = os.path.join(path, "session_summary.json")
            if os.path.isdir(path) and os.path.exists(summary):
                try:
                    with open(summary, "r") as f:
                        data = json.load(f)
                    steps = data.get("total_steps", 0)
                except Exception:
                    steps = "?"
                sessions.append((name, path, steps))

        sessions.sort(reverse=True)

        for name, path, steps in sessions:
            display = f"  {name}  ({steps} steps)"
            self._sessions[display] = path
            self.session_listbox.insert("end", display)

    def _on_session_select(self, event=None):
        sel = self.session_listbox.curselection()
        if not sel:
            return

        display = self.session_listbox.get(sel[0])
        path = self._sessions.get(display)
        if not path:
            return

        self._current_session_path = path
        self._load_session_steps(path)

    def _load_session_steps(self, session_path: str):
        # Clear old cards
        for card in self._step_cards:
            card.destroy()
        self._step_cards.clear()
        self._current_session_steps = []
        self._selected_step_idx = -1

        summary_path = os.path.join(session_path, "session_summary.json")
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        steps = data.get("steps", [])
        self._current_session_steps = steps

        for i, step_info in enumerate(steps):
            step_num = step_info.get("step", 0)
            action = step_info.get("action", "")
            desc = step_info.get("description", "")

            card = StepCard(
                self._step_inner, step_num=step_num, action=action,
                description=desc, selected=False,
                on_click=lambda idx=i: self._select_step(idx),
            )
            card.pack(fill="x", pady=(0, 2))
            self._step_cards.append(card)

    def _select_step(self, idx):
        if idx == self._selected_step_idx:
            return

        self._selected_step_idx = idx

        # Rebuild cards with selection
        session_path = self._current_session_path
        for card in self._step_cards:
            card.destroy()
        self._step_cards.clear()

        for i, step_info in enumerate(self._current_session_steps):
            step_num = step_info.get("step", 0)
            action = step_info.get("action", "")
            desc = step_info.get("description", "")

            card = StepCard(
                self._step_inner, step_num=step_num, action=action,
                description=desc, selected=(i == idx),
                on_click=lambda idx2=i: self._select_step(idx2),
            )
            card.pack(fill="x", pady=(0, 2))
            self._step_cards.append(card)

        # Load screenshot preview
        step_info = self._current_session_steps[idx]
        step_num = step_info.get("step", 0)
        meta_path = os.path.join(session_path, f"{step_num:03d}_metadata.json")

        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                screenshot_name = meta.get("screenshot", "")
                screenshot_path = os.path.join(session_path, screenshot_name)
                if os.path.exists(screenshot_path):
                    self._show_preview(screenshot_path)
            except Exception:
                pass

    def _on_step_scroll(self, event):
        self._step_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_step_canvas_resize(self, event):
        self._step_canvas.itemconfig("inner", width=event.width)

    # ── Preview ───────────────────────────────────────────────────────

    def _show_preview(self, image_path: str):
        self._current_preview_path = image_path
        try:
            img = Image.open(image_path)
            max_w = max(self.preview_label.winfo_width() - 10, 300)
            max_h = max(self.preview_label.winfo_height() - 10, 150)
            img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._preview_images = [photo]
            self.preview_label.configure(image=photo, text="")
        except Exception as e:
            self.preview_label.configure(image="", text=f"Error: {e}")

    def _open_preview_full(self, event=None):
        """Open full-size screenshot in a new window."""
        if not self._current_preview_path or not os.path.exists(self._current_preview_path):
            return

        win = tk.Toplevel(self.root)
        win.title("ActionShot - Preview")
        win.configure(bg=C["bg"])

        try:
            from ctypes import windll, byref, c_int
            win.update()
            hwnd = windll.user32.GetParent(win.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(2)), 4)
        except Exception:
            pass

        img = Image.open(self._current_preview_path)

        # Fit to 80% of screen
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        max_w = int(screen_w * 0.8)
        max_h = int(screen_h * 0.8)
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

        photo = ImageTk.PhotoImage(img)
        self._preview_images.append(photo)

        lbl = tk.Label(win, image=photo, bg=C["bg"])
        lbl.pack(fill="both", expand=True)

        win.geometry(f"{img.width + 20}x{img.height + 20}")
        win.bind("<Escape>", lambda e: win.destroy())

    # ── Tool actions ──────────────────────────────────────────────────

    def _get_selected_session(self) -> str | None:
        if self._current_session_path:
            return self._current_session_path
        path = filedialog.askdirectory(title="Select session folder")
        if path and os.path.exists(os.path.join(path, "session_summary.json")):
            return path
        elif path:
            messagebox.showerror("Error", "No session_summary.json found.")
        return None

    def _replay_session(self):
        session_path = self._get_selected_session()
        if not session_path:
            return
        self._log(f"Replaying: {os.path.basename(session_path)}")

        def _replay():
            try:
                replayer = Replayer(session_path, speed=1.0)
                replayer.run()
                self.root.after(0, lambda: self._log("Replay complete."))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Replay error: {e}"))

        threading.Thread(target=_replay, daemon=True).start()

    def _generate_script(self):
        session_path = self._get_selected_session()
        if not session_path:
            return
        try:
            gen = ScriptGenerator(session_path)
            out = gen.generate()
            self._log(f"Script generated: {os.path.basename(out)}")
        except Exception as e:
            self._log(f"Error: {e}")

    def _generate_ai_prompt(self):
        session_path = self._get_selected_session()
        if not session_path:
            return
        try:
            agent = AIAgent(session_path)
            out = agent.generate_ai_prompt()
            self._log(f"AI prompt: {os.path.basename(out)}")
        except Exception as e:
            self._log(f"Error: {e}")

    def _export_api(self):
        session_path = self._get_selected_session()
        if not session_path:
            return
        include_imgs = messagebox.askyesno("Screenshots", "Include screenshots in payload?")
        try:
            agent = AIAgent(session_path)
            agent.export_for_api(include_screenshots=include_imgs)
            self._log("API payload exported.")
        except Exception as e:
            self._log(f"Error: {e}")

    def run(self):
        self.root.mainloop()
