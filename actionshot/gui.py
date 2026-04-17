"""GUI - Simple tkinter interface for ActionShot."""

import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from .recorder import Recorder
from .replay import Replayer
from .generator import ScriptGenerator
from .ai_agent import AIAgent


class ActionShotGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ActionShot")
        self.root.geometry("500x520")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")

        self.recorder = None
        self.recording = False
        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#e94560", background="#1a1a2e")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#aaaaaa", background="#1a1a2e")
        style.configure("Status.TLabel", font=("Segoe UI", 10), foreground="#0f3460", background="#1a1a2e")
        style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=12)
        style.configure("Action.TButton", font=("Segoe UI", 10), padding=8)

        # Header
        header = tk.Frame(self.root, bg="#1a1a2e")
        header.pack(fill="x", pady=(20, 5))
        ttk.Label(header, text="⚡ ActionShot", style="Title.TLabel").pack()
        ttk.Label(header, text="Desktop Interaction Recorder for AI Automation", style="Sub.TLabel").pack()

        # Record section
        rec_frame = tk.LabelFrame(self.root, text="  Record  ", font=("Segoe UI", 10, "bold"),
                                  fg="#e94560", bg="#16213e", bd=1, relief="groove",
                                  labelanchor="n")
        rec_frame.pack(fill="x", padx=20, pady=10)

        btn_frame = tk.Frame(rec_frame, bg="#16213e")
        btn_frame.pack(pady=15)

        self.record_btn = ttk.Button(btn_frame, text="● Start Recording", style="Big.TButton",
                                     command=self._toggle_recording)
        self.record_btn.pack()

        self.status_label = ttk.Label(rec_frame, text="Ready", style="Status.TLabel")
        self.status_label.pack(pady=(0, 10))

        # Output directory
        dir_frame = tk.Frame(rec_frame, bg="#16213e")
        dir_frame.pack(fill="x", padx=15, pady=(0, 10))

        self.output_var = tk.StringVar(value="recordings")
        ttk.Label(dir_frame, text="Output:", font=("Segoe UI", 9),
                  foreground="#aaaaaa", background="#16213e").pack(side="left")
        ttk.Entry(dir_frame, textvariable=self.output_var, width=30).pack(side="left", padx=5)
        ttk.Button(dir_frame, text="Browse", command=self._browse_output).pack(side="left")

        # Tools section
        tools_frame = tk.LabelFrame(self.root, text="  Tools  ", font=("Segoe UI", 10, "bold"),
                                    fg="#e94560", bg="#16213e", bd=1, relief="groove",
                                    labelanchor="n")
        tools_frame.pack(fill="x", padx=20, pady=10)

        tools_inner = tk.Frame(tools_frame, bg="#16213e")
        tools_inner.pack(pady=15, padx=15)

        ttk.Button(tools_inner, text="▶ Replay Session", style="Action.TButton",
                   command=self._replay_session).grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(tools_inner, text="⚙ Generate Script", style="Action.TButton",
                   command=self._generate_script).grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(tools_inner, text="🤖 AI Prompt", style="Action.TButton",
                   command=self._generate_ai_prompt).grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(tools_inner, text="📦 Export for API", style="Action.TButton",
                   command=self._export_api).grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        tools_inner.columnconfigure(0, weight=1)
        tools_inner.columnconfigure(1, weight=1)

        # Log
        log_frame = tk.LabelFrame(self.root, text="  Log  ", font=("Segoe UI", 10, "bold"),
                                  fg="#e94560", bg="#16213e", bd=1, relief="groove",
                                  labelanchor="n")
        log_frame.pack(fill="both", expand=True, padx=20, pady=(10, 20))

        self.log_text = tk.Text(log_frame, height=5, bg="#0f0f23", fg="#00ff41",
                                font=("Consolas", 9), bd=0, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        self._log("ActionShot ready. Click 'Start Recording' to begin.")

    def _log(self, msg: str):
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")

    def _browse_output(self):
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self.output_var.set(path)

    def _select_session(self) -> str | None:
        path = filedialog.askdirectory(title="Select a recording session folder")
        if path and os.path.exists(os.path.join(path, "session_summary.json")):
            return path
        elif path:
            messagebox.showerror("Error", "No session_summary.json found in selected folder.")
        return None

    def _toggle_recording(self):
        if not self.recording:
            self.recording = True
            self.record_btn.configure(text="■ Stop Recording")
            self.status_label.configure(text="Recording... (ESC to stop)", foreground="#e94560")
            self._log("Recording started. Press ESC or click Stop to end.")

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
        self.record_btn.configure(text="● Start Recording")
        self.status_label.configure(text="Ready", foreground="#0f3460")
        if self.recorder and self.recorder.session:
            self._log(f"Session saved: {self.recorder.session.path}")
            self._log(f"Total steps: {self.recorder.session.step_count}")

    def _replay_session(self):
        session_path = self._select_session()
        if not session_path:
            return

        speed = 1.0
        self._log(f"Replaying: {session_path}")

        def _replay():
            try:
                replayer = Replayer(session_path, speed=speed)
                replayer.run()
                self.root.after(0, lambda: self._log("Replay complete."))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"Replay error: {e}"))

        threading.Thread(target=_replay, daemon=True).start()

    def _generate_script(self):
        session_path = self._select_session()
        if not session_path:
            return
        try:
            gen = ScriptGenerator(session_path)
            out = gen.generate()
            self._log(f"Script generated: {out}")
        except Exception as e:
            self._log(f"Error: {e}")

    def _generate_ai_prompt(self):
        session_path = self._select_session()
        if not session_path:
            return
        try:
            agent = AIAgent(session_path)
            out = agent.generate_ai_prompt()
            self._log(f"AI prompt generated: {out}")
        except Exception as e:
            self._log(f"Error: {e}")

    def _export_api(self):
        session_path = self._select_session()
        if not session_path:
            return

        include_imgs = messagebox.askyesno("Screenshots", "Include screenshots in API payload? (larger file)")
        try:
            agent = AIAgent(session_path)
            agent.export_for_api(include_screenshots=include_imgs)
            self._log("API payload exported.")
        except Exception as e:
            self._log(f"Error: {e}")

    def run(self):
        self.root.mainloop()
