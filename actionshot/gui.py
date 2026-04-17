"""GUI - Tkinter interface for ActionShot with session browser."""

import json
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk

from .recorder import Recorder
from .replay import Replayer
from .generator import ScriptGenerator
from .ai_agent import AIAgent


class ActionShotGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ActionShot")
        self.root.geometry("780x650")
        self.root.resizable(True, True)
        self.root.configure(bg="#1a1a2e")

        self.recorder = None
        self.recording = False
        self._preview_images = []  # prevent GC of PhotoImages
        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#e94560", background="#1a1a2e")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#aaaaaa", background="#1a1a2e")
        style.configure("Status.TLabel", font=("Segoe UI", 10), foreground="#0f3460", background="#1a1a2e")
        style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=12)
        style.configure("Action.TButton", font=("Segoe UI", 10), padding=8)
        style.configure("Small.TButton", font=("Segoe UI", 9), padding=4)

        # Main paned window
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        # ── Left panel: controls ──────────────────────────────────────
        left = tk.Frame(paned, bg="#1a1a2e", width=340)
        paned.add(left, weight=1)

        # Header
        header = tk.Frame(left, bg="#1a1a2e")
        header.pack(fill="x", pady=(10, 5))
        ttk.Label(header, text="ActionShot", style="Title.TLabel").pack()
        ttk.Label(header, text="Desktop Interaction Recorder", style="Sub.TLabel").pack()

        # Record section
        rec_frame = tk.LabelFrame(left, text="  Record  ", font=("Segoe UI", 10, "bold"),
                                  fg="#e94560", bg="#16213e", bd=1, relief="groove", labelanchor="n")
        rec_frame.pack(fill="x", padx=10, pady=8)

        btn_frame = tk.Frame(rec_frame, bg="#16213e")
        btn_frame.pack(pady=10)

        self.record_btn = ttk.Button(btn_frame, text="Start Recording", style="Big.TButton",
                                     command=self._toggle_recording)
        self.record_btn.pack()

        self.status_label = ttk.Label(rec_frame, text="Ready", style="Status.TLabel")
        self.status_label.pack(pady=(0, 5))

        dir_frame = tk.Frame(rec_frame, bg="#16213e")
        dir_frame.pack(fill="x", padx=10, pady=(0, 8))
        self.output_var = tk.StringVar(value="recordings")
        ttk.Label(dir_frame, text="Output:", font=("Segoe UI", 9),
                  foreground="#aaaaaa", background="#16213e").pack(side="left")
        ttk.Entry(dir_frame, textvariable=self.output_var, width=20).pack(side="left", padx=5)
        ttk.Button(dir_frame, text="...", width=3, command=self._browse_output).pack(side="left")

        # Tools section
        tools_frame = tk.LabelFrame(left, text="  Tools  ", font=("Segoe UI", 10, "bold"),
                                    fg="#e94560", bg="#16213e", bd=1, relief="groove", labelanchor="n")
        tools_frame.pack(fill="x", padx=10, pady=8)

        tools_inner = tk.Frame(tools_frame, bg="#16213e")
        tools_inner.pack(pady=10, padx=10, fill="x")

        ttk.Button(tools_inner, text="Replay", style="Action.TButton",
                   command=self._replay_session).grid(row=0, column=0, padx=3, pady=3, sticky="ew")
        ttk.Button(tools_inner, text="Generate Script", style="Action.TButton",
                   command=self._generate_script).grid(row=0, column=1, padx=3, pady=3, sticky="ew")
        ttk.Button(tools_inner, text="AI Prompt", style="Action.TButton",
                   command=self._generate_ai_prompt).grid(row=1, column=0, padx=3, pady=3, sticky="ew")
        ttk.Button(tools_inner, text="Export API", style="Action.TButton",
                   command=self._export_api).grid(row=1, column=1, padx=3, pady=3, sticky="ew")
        tools_inner.columnconfigure(0, weight=1)
        tools_inner.columnconfigure(1, weight=1)

        # Log
        log_frame = tk.LabelFrame(left, text="  Log  ", font=("Segoe UI", 10, "bold"),
                                  fg="#e94560", bg="#16213e", bd=1, relief="groove", labelanchor="n")
        log_frame.pack(fill="both", expand=True, padx=10, pady=(8, 10))

        self.log_text = tk.Text(log_frame, height=4, bg="#0f0f23", fg="#00ff41",
                                font=("Consolas", 9), bd=0, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self._log("Ready. Click 'Start Recording' to begin.")

        # ── Right panel: session browser ──────────────────────────────
        right = tk.Frame(paned, bg="#1a1a2e", width=400)
        paned.add(right, weight=1)

        browser_header = tk.Frame(right, bg="#1a1a2e")
        browser_header.pack(fill="x", pady=(10, 5), padx=10)
        ttk.Label(browser_header, text="Sessions", style="Title.TLabel",
                  font=("Segoe UI", 14, "bold")).pack(side="left")
        ttk.Button(browser_header, text="Refresh", style="Small.TButton",
                   command=self._refresh_sessions).pack(side="right")

        # Session list
        list_frame = tk.Frame(right, bg="#16213e")
        list_frame.pack(fill="x", padx=10, pady=5)

        self.session_listbox = tk.Listbox(list_frame, bg="#0f0f23", fg="#00ff41",
                                          font=("Consolas", 10), height=6,
                                          selectbackground="#e94560", selectforeground="white",
                                          bd=0, relief="flat")
        self.session_listbox.pack(fill="x", padx=5, pady=5)
        self.session_listbox.bind("<<ListboxSelect>>", self._on_session_select)

        # Step list
        step_frame = tk.LabelFrame(right, text="  Steps  ", font=("Segoe UI", 10, "bold"),
                                   fg="#e94560", bg="#16213e", bd=1, relief="groove", labelanchor="n")
        step_frame.pack(fill="x", padx=10, pady=5)

        self.step_listbox = tk.Listbox(step_frame, bg="#0f0f23", fg="#aaaaaa",
                                       font=("Consolas", 9), height=6,
                                       selectbackground="#0f3460", selectforeground="white",
                                       bd=0, relief="flat")
        self.step_listbox.pack(fill="x", padx=5, pady=5)
        self.step_listbox.bind("<<ListboxSelect>>", self._on_step_select)

        # Screenshot preview
        preview_frame = tk.LabelFrame(right, text="  Preview  ", font=("Segoe UI", 10, "bold"),
                                      fg="#e94560", bg="#16213e", bd=1, relief="groove", labelanchor="n")
        preview_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.preview_label = tk.Label(preview_frame, bg="#0f0f23", text="Select a step to preview",
                                      fg="#555555", font=("Segoe UI", 9))
        self.preview_label.pack(fill="both", expand=True, padx=5, pady=5)

        # State
        self._sessions = {}  # name -> path
        self._current_session_steps = []
        self._current_session_path = None

        # Load sessions
        self._refresh_sessions()

    def _log(self, msg: str):
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self.output_var.set(path)

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
                sessions.append((name, path))

        sessions.sort(reverse=True)  # newest first

        for name, path in sessions:
            # Load step count
            try:
                with open(os.path.join(path, "session_summary.json"), "r") as f:
                    data = json.load(f)
                step_count = data.get("total_steps", "?")
            except Exception:
                step_count = "?"

            display = f"{name} ({step_count} steps)"
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
        self.step_listbox.delete(0, "end")
        self._current_session_steps = []

        summary_path = os.path.join(session_path, "session_summary.json")
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        for step_info in data.get("steps", []):
            step_num = step_info.get("step", 0)
            desc = step_info.get("description", "")[:50]
            display = f"{step_num:03d}  {desc}"
            self.step_listbox.insert("end", display)
            self._current_session_steps.append(step_info)

    def _on_step_select(self, event=None):
        sel = self.step_listbox.curselection()
        if not sel or not self._current_session_path:
            return

        step_info = self._current_session_steps[sel[0]]
        step_num = step_info.get("step", 0)

        # Find the screenshot file
        meta_path = os.path.join(self._current_session_path, f"{step_num:03d}_metadata.json")
        if not os.path.exists(meta_path):
            return

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            return

        screenshot_name = meta.get("screenshot", "")
        screenshot_path = os.path.join(self._current_session_path, screenshot_name)

        if os.path.exists(screenshot_path):
            self._show_preview(screenshot_path)

    def _show_preview(self, image_path: str):
        try:
            img = Image.open(image_path)
            # Fit to preview area
            max_w = self.preview_label.winfo_width() - 10
            max_h = self.preview_label.winfo_height() - 10
            if max_w < 50:
                max_w = 380
            if max_h < 50:
                max_h = 200

            img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._preview_images = [photo]  # keep reference
            self.preview_label.configure(image=photo, text="")
        except Exception as e:
            self.preview_label.configure(image="", text=f"Error: {e}")

    # ── Session selection for tools ───────────────────────────────────

    def _get_selected_session(self) -> str | None:
        """Get session path from browser selection or file dialog."""
        if self._current_session_path:
            return self._current_session_path

        path = filedialog.askdirectory(title="Select a recording session folder")
        if path and os.path.exists(os.path.join(path, "session_summary.json")):
            return path
        elif path:
            messagebox.showerror("Error", "No session_summary.json found.")
        return None

    # ── Recording ─────────────────────────────────────────────────────

    def _toggle_recording(self):
        if not self.recording:
            self.recording = True
            self.record_btn.configure(text="Stop Recording")
            self.status_label.configure(text="Recording... (ESC to stop)", foreground="#e94560")
            self._log("Recording started.")

            output = self.output_var.get()
            self.recorder = Recorder(output_dir=output)

            def _record():
                self.recorder.start()
                self.root.after(0, self._on_recording_stopped)

            self._rec_thread = threading.Thread(target=_record, daemon=True)
            self._rec_thread.start()
        else:
            if self.recorder:
                self.recorder.stop()

    def _on_recording_stopped(self):
        self.recording = False
        self.record_btn.configure(text="Start Recording")
        self.status_label.configure(text="Ready", foreground="#0f3460")
        if self.recorder and self.recorder.session:
            self._log(f"Saved: {self.recorder.session.path} ({self.recorder.session.step_count} steps)")
        self._refresh_sessions()

    # ── Tool actions ──────────────────────────────────────────────────

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
            self._log(f"Script: {out}")
        except Exception as e:
            self._log(f"Error: {e}")

    def _generate_ai_prompt(self):
        session_path = self._get_selected_session()
        if not session_path:
            return
        try:
            agent = AIAgent(session_path)
            out = agent.generate_ai_prompt()
            self._log(f"AI prompt: {out}")
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
