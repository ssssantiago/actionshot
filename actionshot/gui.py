"""ActionShot — User-friendly desktop app for recording automation requests.

Flow for end users:
1. Open app → click "Gravar"
2. Do the workflow on their machine
3. Review steps, mark variables, add notes
4. Click "Enviar pro Dev" → packages everything for the developer
"""

import json
import os
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageTk

from .recorder import Recorder

# Optional imports — app works without them
try:
    from .patterns import PatternDetector
except Exception:
    PatternDetector = None

try:
    from .ir_compiler import IRCompiler
except Exception:
    IRCompiler = None


# ── Theme ─────────────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT = "#7c3aed"
ACCENT_HOVER = "#9b5de5"
RED = "#ef4444"
GREEN = "#22c55e"
BLUE = "#3b82f6"
YELLOW = "#f59e0b"
BG = "#0f0e17"
CARD = "#1a1a2e"
TEXT = "#fffffe"
DIM = "#94a3b8"
MUTED = "#475569"


# ── Main App ──────────────────────────────────────────────────────────

class ActionShotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ActionShot")
        self.geometry("1000x700")
        self.minsize(900, 650)
        self.configure(fg_color=BG)

        # Try dark title bar on Windows
        try:
            from ctypes import windll, byref, c_int
            self.update()
            hwnd = windll.user32.GetParent(self.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(2)), 4)
        except Exception:
            pass

        # State
        self.recorder = None
        self.recording = False
        self._session_path = None
        self._steps = []
        self._step_vars = {}       # step_num -> {"is_variable": bool, "var_name": str, "note": str}
        self._preview_refs = []    # keep PhotoImage refs
        self._timer_start = None
        self._timer_id = None
        self._current_page = "home"

        self._build_nav()
        self._build_pages()
        self._show_page("home")

    # ── Navigation ────────────────────────────────────────────────────

    def _build_nav(self):
        self._nav = ctk.CTkFrame(self, fg_color=CARD, width=200, corner_radius=0)
        self._nav.pack(side="left", fill="y")
        self._nav.pack_propagate(False)

        # Logo
        logo_frame = ctk.CTkFrame(self._nav, fg_color="transparent")
        logo_frame.pack(fill="x", padx=16, pady=(20, 8))
        ctk.CTkLabel(logo_frame, text="ActionShot", font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=ACCENT).pack(anchor="w")
        ctk.CTkLabel(logo_frame, text="Gravador de Automacoes", font=ctk.CTkFont(size=11),
                     text_color=MUTED).pack(anchor="w")

        # Separator
        ctk.CTkFrame(self._nav, fg_color=MUTED, height=1).pack(fill="x", padx=16, pady=12)

        # Nav buttons
        self._nav_btns = {}
        nav_items = [
            ("home", "Inicio"),
            ("record", "Gravar"),
            ("review", "Revisar Passos"),
            ("config", "Configurar"),
            ("send", "Enviar pro Dev"),
        ]

        for page_id, label in nav_items:
            btn = ctk.CTkButton(
                self._nav, text=f"  {label}", anchor="w",
                font=ctk.CTkFont(size=13), height=40,
                fg_color="transparent", hover_color=ACCENT,
                text_color=DIM, corner_radius=8,
                command=lambda p=page_id: self._show_page(p),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_btns[page_id] = btn

        # Bottom info
        self._nav_status = ctk.CTkLabel(
            self._nav, text="Nenhuma gravacao", font=ctk.CTkFont(size=10),
            text_color=MUTED,
        )
        self._nav_status.pack(side="bottom", padx=16, pady=16, anchor="w")

    def _show_page(self, page_id):
        self._current_page = page_id
        for pid, btn in self._nav_btns.items():
            if pid == page_id:
                btn.configure(fg_color=ACCENT, text_color=TEXT)
            else:
                btn.configure(fg_color="transparent", text_color=DIM)

        for pid, frame in self._pages.items():
            if pid == page_id:
                frame.pack(side="left", fill="both", expand=True)
            else:
                frame.pack_forget()

        if page_id == "review" and self._session_path:
            self._load_review()
        if page_id == "send":
            self._update_send_summary()

    # ── Pages ─────────────────────────────────────────────────────────

    def _build_pages(self):
        self._pages = {}
        self._build_home_page()
        self._build_record_page()
        self._build_review_page()
        self._build_config_page()
        self._build_send_page()

    # ── HOME PAGE ─────────────────────────────────────────────────────

    def _build_home_page(self):
        page = ctk.CTkFrame(self, fg_color=BG)
        self._pages["home"] = page

        # Hero
        hero = ctk.CTkFrame(page, fg_color=CARD, corner_radius=16)
        hero.pack(fill="x", padx=30, pady=(30, 20))

        ctk.CTkLabel(hero, text="Bem-vindo ao ActionShot",
                     font=ctk.CTkFont(size=26, weight="bold"),
                     text_color=TEXT).pack(padx=30, pady=(30, 8))
        ctk.CTkLabel(hero, text="Grave o que voce faz no computador e envie para o dev transformar em automacao.",
                     font=ctk.CTkFont(size=14), text_color=DIM,
                     wraplength=600).pack(padx=30, pady=(0, 20))

        ctk.CTkButton(hero, text="Comecar a Gravar", font=ctk.CTkFont(size=16, weight="bold"),
                      fg_color=ACCENT, hover_color=ACCENT_HOVER, height=50, corner_radius=12,
                      command=lambda: self._show_page("record")).pack(padx=30, pady=(0, 30))

        # Steps guide
        steps_frame = ctk.CTkFrame(page, fg_color="transparent")
        steps_frame.pack(fill="x", padx=30, pady=10)

        guide = [
            ("1", "Gravar", "Clique em Gravar e faca o workflow normalmente no seu computador."),
            ("2", "Revisar", "Veja os passos capturados. Marque o que muda toda vez (variaveis)."),
            ("3", "Configurar", "Adicione notas, descreva cenarios e excecoes."),
            ("4", "Enviar", "Empacote tudo e envie para o desenvolvedor criar o RPA."),
        ]

        for i, (num, title, desc) in enumerate(guide):
            card = ctk.CTkFrame(steps_frame, fg_color=CARD, corner_radius=12)
            card.grid(row=0, column=i, padx=8, pady=8, sticky="nsew")
            steps_frame.columnconfigure(i, weight=1)

            ctk.CTkLabel(card, text=num, font=ctk.CTkFont(size=28, weight="bold"),
                         text_color=ACCENT).pack(padx=16, pady=(16, 4))
            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=TEXT).pack(padx=16)
            ctk.CTkLabel(card, text=desc, font=ctk.CTkFont(size=11),
                         text_color=DIM, wraplength=180).pack(padx=16, pady=(4, 16))

        # Recent sessions
        recent_frame = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        recent_frame.pack(fill="both", expand=True, padx=30, pady=(10, 30))
        ctk.CTkLabel(recent_frame, text="Gravacoes Recentes",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 8))

        self._recent_list = ctk.CTkFrame(recent_frame, fg_color="transparent")
        self._recent_list.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        self._refresh_recent()

    def _refresh_recent(self):
        for w in self._recent_list.winfo_children():
            w.destroy()

        rec_dir = "recordings"
        if not os.path.exists(rec_dir):
            ctk.CTkLabel(self._recent_list, text="Nenhuma gravacao encontrada.",
                         text_color=MUTED).pack(pady=10)
            return

        sessions = []
        for name in os.listdir(rec_dir):
            path = os.path.join(rec_dir, name)
            summary = os.path.join(path, "session_summary.json")
            if os.path.isdir(path) and os.path.exists(summary):
                try:
                    with open(summary, "r") as f:
                        data = json.load(f)
                    sessions.append((name, path, data.get("total_steps", 0)))
                except Exception:
                    pass

        sessions.sort(reverse=True)

        if not sessions:
            ctk.CTkLabel(self._recent_list, text="Nenhuma gravacao encontrada.",
                         text_color=MUTED).pack(pady=10)
            return

        for name, path, steps in sessions[:6]:
            row = ctk.CTkFrame(self._recent_list, fg_color="#1e1e3a", corner_radius=8)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=name, font=ctk.CTkFont(size=12),
                         text_color=TEXT).pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(row, text=f"{steps} passos", font=ctk.CTkFont(size=11),
                         text_color=MUTED).pack(side="left", padx=8)
            ctk.CTkButton(row, text="Abrir", width=60, height=28, corner_radius=6,
                          fg_color=ACCENT, hover_color=ACCENT_HOVER,
                          font=ctk.CTkFont(size=11),
                          command=lambda p=path: self._open_session(p)
                          ).pack(side="right", padx=12, pady=6)

    def _open_session(self, path):
        self._session_path = path
        self._load_steps()
        self._nav_status.configure(text=f"{os.path.basename(path)}")
        self._show_page("review")

    # ── RECORD PAGE ───────────────────────────────────────────────────

    def _build_record_page(self):
        page = ctk.CTkFrame(self, fg_color=BG)
        self._pages["record"] = page

        center = ctk.CTkFrame(page, fg_color="transparent")
        center.place(relx=0.5, rely=0.45, anchor="center")

        # Big record button
        self._rec_btn = ctk.CTkButton(
            center, text="GRAVAR", width=200, height=200,
            corner_radius=100, font=ctk.CTkFont(size=24, weight="bold"),
            fg_color=RED, hover_color="#dc2626", text_color="white",
            command=self._toggle_recording,
        )
        self._rec_btn.pack()

        self._rec_label = ctk.CTkLabel(
            center, text="Clique para comecar a gravar.\nFaca seu workflow normalmente.\nPressione ESC para parar.",
            font=ctk.CTkFont(size=13), text_color=DIM, justify="center",
        )
        self._rec_label.pack(pady=(20, 0))

        # Timer + counter
        timer_frame = ctk.CTkFrame(center, fg_color="transparent")
        timer_frame.pack(pady=(16, 0))

        self._rec_timer_label = ctk.CTkLabel(
            timer_frame, text="", font=ctk.CTkFont(family="Consolas", size=32, weight="bold"),
            text_color=TEXT,
        )
        self._rec_timer_label.pack()

        self._rec_steps_label = ctk.CTkLabel(
            timer_frame, text="", font=ctk.CTkFont(size=14), text_color=MUTED,
        )
        self._rec_steps_label.pack()

        # Output dir
        dir_frame = ctk.CTkFrame(page, fg_color="transparent")
        dir_frame.pack(side="bottom", pady=20)
        ctk.CTkLabel(dir_frame, text="Salvar em:", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self._output_var = ctk.StringVar(value="recordings")
        ctk.CTkEntry(dir_frame, textvariable=self._output_var, width=200,
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=6)

    def _toggle_recording(self):
        if not self.recording:
            self.recording = True
            self._rec_btn.configure(text="PARAR", fg_color="#7f1d1d", hover_color="#991b1b")
            self._rec_label.configure(text="Gravando... Faca seu workflow agora.\nPressione ESC ou clique PARAR para encerrar.")

            output = self._output_var.get()
            self.recorder = Recorder(output_dir=output)

            def _run():
                self.recorder.start()
                self.after(0, self._on_recording_done)

            threading.Thread(target=_run, daemon=True).start()
            self._timer_start = time.monotonic()
            self._update_timer()
        else:
            if self.recorder:
                self.recorder.stop()

    def _update_timer(self):
        if not self.recording:
            return
        elapsed = time.monotonic() - self._timer_start
        m, s = divmod(int(elapsed), 60)
        self._rec_timer_label.configure(text=f"{m:02d}:{s:02d}")

        steps = 0
        if self.recorder and self.recorder.session:
            steps = self.recorder.session.step_count
        self._rec_steps_label.configure(text=f"{steps} passos capturados")

        self._timer_id = self.after(500, self._update_timer)

    def _on_recording_done(self):
        self.recording = False
        if self._timer_id:
            self.after_cancel(self._timer_id)

        self._rec_btn.configure(text="GRAVAR", fg_color=RED, hover_color="#dc2626")

        if self.recorder and self.recorder.session:
            self._session_path = self.recorder.session.path
            count = self.recorder.session.step_count
            self._rec_label.configure(
                text=f"Gravacao concluida! {count} passos capturados.\nVa para 'Revisar Passos' para configurar."
            )
            self._nav_status.configure(text=f"{self.recorder.session.name}")
            self._load_steps()
            self._refresh_recent()
        else:
            self._rec_label.configure(text="Clique para comecar a gravar.")
            self._rec_timer_label.configure(text="")
            self._rec_steps_label.configure(text="")

    # ── REVIEW PAGE ───────────────────────────────────────────────────

    def _build_review_page(self):
        page = ctk.CTkFrame(self, fg_color=BG)
        self._pages["review"] = page

        # Header
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 12))
        ctk.CTkLabel(header, text="Revisar Passos",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT).pack(side="left")

        self._review_info = ctk.CTkLabel(header, text="", text_color=MUTED,
                                          font=ctk.CTkFont(size=12))
        self._review_info.pack(side="right")

        # Help text
        ctk.CTkLabel(page, text="Marque os campos que mudam a cada execucao como 'Variavel'. Adicione notas para o dev.",
                     font=ctk.CTkFont(size=12), text_color=DIM,
                     wraplength=700, anchor="w").pack(fill="x", padx=24, pady=(0, 8))

        # Split: step list (left) + preview (right)
        content = ctk.CTkFrame(page, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        # Step list (scrollable)
        left = ctk.CTkFrame(content, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))

        self._step_scroll = ctk.CTkScrollableFrame(left, fg_color=CARD, corner_radius=12)
        self._step_scroll.pack(fill="both", expand=True)

        # Preview panel
        right = ctk.CTkFrame(content, fg_color=CARD, corner_radius=12, width=380)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        ctk.CTkLabel(right, text="Preview do Passo",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT).pack(padx=16, pady=(16, 8))

        self._preview_image = ctk.CTkLabel(right, text="Selecione um passo", text_color=MUTED)
        self._preview_image.pack(fill="both", expand=True, padx=8, pady=4)

        self._preview_meta = ctk.CTkTextbox(right, height=100, font=ctk.CTkFont(family="Consolas", size=10),
                                             fg_color="#0a0a1a", text_color=DIM, corner_radius=8)
        self._preview_meta.pack(fill="x", padx=8, pady=(4, 8))

    def _load_steps(self):
        if not self._session_path:
            return

        summary_path = os.path.join(self._session_path, "session_summary.json")
        if not os.path.exists(summary_path):
            return

        with open(summary_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self._steps = data.get("steps", [])

        # Init step vars for new steps
        for s in self._steps:
            num = s.get("step", 0)
            if num not in self._step_vars:
                self._step_vars[num] = {"is_variable": False, "var_name": "", "note": ""}

    def _load_review(self):
        # Clear existing
        for w in self._step_scroll.winfo_children():
            w.destroy()

        if not self._steps:
            ctk.CTkLabel(self._step_scroll, text="Nenhum passo. Grave primeiro.",
                         text_color=MUTED).pack(pady=20)
            return

        self._review_info.configure(text=f"{len(self._steps)} passos | {os.path.basename(self._session_path)}")

        for step in self._steps:
            self._create_step_card(step)

    def _create_step_card(self, step):
        num = step.get("step", 0)
        action = step.get("action", "")
        desc = step.get("description", "")
        sv = self._step_vars.get(num, {})

        # Color by action
        colors = {"click": RED, "drag": "#FF6600", "scroll": BLUE, "keypress": YELLOW}
        badge_color = MUTED
        for key, col in colors.items():
            if key in action:
                badge_color = col
                break

        card = ctk.CTkFrame(self._step_scroll, fg_color="#1e1e3a", corner_radius=10)
        card.pack(fill="x", padx=8, pady=4)

        # Top row: badge + description + preview button
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(top, text=f" {num:03d} ", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                     fg_color=badge_color, corner_radius=4, text_color="white",
                     width=40).pack(side="left")

        action_label = action.replace("_click", "").replace("left", "Clique").replace("right", "Clique dir.").replace("keypress", "Digitou").replace("scroll", "Rolou")
        ctk.CTkLabel(top, text=f"  {action_label}", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=badge_color).pack(side="left")

        ctk.CTkButton(top, text="Ver", width=50, height=26, corner_radius=6,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(size=10),
                      command=lambda n=num: self._preview_step(n)
                      ).pack(side="right")

        # Description
        desc_short = desc[:70] + "..." if len(desc) > 70 else desc
        ctk.CTkLabel(card, text=desc_short, font=ctk.CTkFont(size=11),
                     text_color=DIM, anchor="w").pack(fill="x", padx=12, pady=(0, 4))

        # Variable toggle + name
        var_frame = ctk.CTkFrame(card, fg_color="transparent")
        var_frame.pack(fill="x", padx=12, pady=(0, 4))

        is_var = ctk.BooleanVar(value=sv.get("is_variable", False))
        var_check = ctk.CTkCheckBox(
            var_frame, text="Variavel (muda toda vez)",
            variable=is_var, font=ctk.CTkFont(size=11),
            checkbox_width=18, checkbox_height=18,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda n=num, v=is_var: self._toggle_variable(n, v.get()),
        )
        var_check.pack(side="left")

        if sv.get("is_variable"):
            name_entry = ctk.CTkEntry(var_frame, width=150, height=26,
                                       placeholder_text="Nome da variavel",
                                       font=ctk.CTkFont(size=10))
            name_entry.pack(side="left", padx=(10, 0))
            if sv.get("var_name"):
                name_entry.insert(0, sv["var_name"])
            name_entry.bind("<FocusOut>", lambda e, n=num, en=name_entry: self._set_var_name(n, en.get()))

        # Note
        note_frame = ctk.CTkFrame(card, fg_color="transparent")
        note_frame.pack(fill="x", padx=12, pady=(0, 10))

        note_entry = ctk.CTkEntry(note_frame, height=26,
                                   placeholder_text="Nota para o dev (opcional)",
                                   font=ctk.CTkFont(size=10))
        note_entry.pack(fill="x")
        if sv.get("note"):
            note_entry.insert(0, sv["note"])
        note_entry.bind("<FocusOut>", lambda e, n=num, en=note_entry: self._set_note(n, en.get()))

    def _toggle_variable(self, step_num, is_var):
        if step_num not in self._step_vars:
            self._step_vars[step_num] = {}
        self._step_vars[step_num]["is_variable"] = is_var
        # Rebuild review to show/hide name entry
        self._load_review()

    def _set_var_name(self, step_num, name):
        if step_num not in self._step_vars:
            self._step_vars[step_num] = {}
        self._step_vars[step_num]["var_name"] = name

    def _set_note(self, step_num, note):
        if step_num not in self._step_vars:
            self._step_vars[step_num] = {}
        self._step_vars[step_num]["note"] = note

    def _preview_step(self, step_num):
        if not self._session_path:
            return

        meta_path = os.path.join(self._session_path, f"{step_num:03d}_metadata.json")
        if not os.path.exists(meta_path):
            return

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        # Show screenshot
        screenshot_name = meta.get("screenshot", "")
        screenshot_path = os.path.join(self._session_path, screenshot_name)

        if os.path.exists(screenshot_path):
            try:
                img = Image.open(screenshot_path)
                img.thumbnail((360, 300), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._preview_refs = [photo]
                self._preview_image.configure(image=photo, text="")
            except Exception:
                self._preview_image.configure(image=None, text="Erro ao carregar imagem")
        else:
            self._preview_image.configure(image=None, text="Screenshot nao encontrado")

        # Show metadata
        self._preview_meta.delete("0.0", "end")
        display = {
            "Acao": meta.get("action", ""),
            "Janela": meta.get("window", {}).get("title", ""),
            "Processo": meta.get("window", {}).get("process", ""),
            "Elemento": meta.get("element", {}).get("name", ""),
            "Tipo": meta.get("element", {}).get("control_type", ""),
        }
        if meta.get("position"):
            display["Posicao"] = f"({meta['position'].get('x', '?')}, {meta['position'].get('y', '?')})"
        if meta.get("text"):
            display["Texto"] = meta["text"][:100]
        if meta.get("ocr_nearby"):
            display["OCR"] = meta["ocr_nearby"][:100]

        for key, val in display.items():
            if val:
                self._preview_meta.insert("end", f"{key}: {val}\n")

    # ── CONFIG PAGE ───────────────────────────────────────────────────

    def _build_config_page(self):
        page = ctk.CTkFrame(self, fg_color=BG)
        self._pages["config"] = page

        # Header
        ctk.CTkLabel(page, text="Configurar Automacao",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(20, 12))

        ctk.CTkLabel(page, text="Descreva o que a automacao deve fazer, cenarios especiais e excecoes.",
                     font=ctk.CTkFont(size=12), text_color=DIM).pack(anchor="w", padx=24)

        # Workflow name
        name_card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        name_card.pack(fill="x", padx=24, pady=(16, 8))

        ctk.CTkLabel(name_card, text="Nome do Workflow",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(12, 4))
        self._workflow_name = ctk.CTkEntry(name_card, placeholder_text="Ex: cadastro_processo_pje",
                                            font=ctk.CTkFont(size=13), height=36)
        self._workflow_name.pack(fill="x", padx=16, pady=(0, 12))

        # Description
        desc_card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        desc_card.pack(fill="x", padx=24, pady=8)

        ctk.CTkLabel(desc_card, text="Descricao do Workflow",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(desc_card, text="O que esse workflow faz? Qual o objetivo final?",
                     font=ctk.CTkFont(size=11), text_color=MUTED).pack(anchor="w", padx=16)
        self._workflow_desc = ctk.CTkTextbox(desc_card, height=80,
                                              font=ctk.CTkFont(size=12),
                                              fg_color="#0a0a1a", corner_radius=8)
        self._workflow_desc.pack(fill="x", padx=16, pady=(4, 12))

        # Scenarios
        scenario_card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        scenario_card.pack(fill="x", padx=24, pady=8)

        ctk.CTkLabel(scenario_card, text="Cenarios e Excecoes",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(scenario_card, text="O que pode dar errado? Popups inesperados? Campos opcionais? Caminhos diferentes?",
                     font=ctk.CTkFont(size=11), text_color=MUTED, wraplength=600).pack(anchor="w", padx=16)
        self._scenarios = ctk.CTkTextbox(scenario_card, height=100,
                                          font=ctk.CTkFont(size=12),
                                          fg_color="#0a0a1a", corner_radius=8)
        self._scenarios.pack(fill="x", padx=16, pady=(4, 12))

        # Frequency
        freq_card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        freq_card.pack(fill="x", padx=24, pady=8)

        ctk.CTkLabel(freq_card, text="Frequencia de Execucao",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(12, 4))
        self._frequency = ctk.CTkComboBox(freq_card, values=[
            "Sob demanda (manual)",
            "Diariamente",
            "Semanalmente",
            "Varias vezes ao dia",
            "Outro (descrever nos cenarios)",
        ], font=ctk.CTkFont(size=12), width=300)
        self._frequency.pack(anchor="w", padx=16, pady=(0, 12))

        # Priority
        prio_card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        prio_card.pack(fill="x", padx=24, pady=(8, 20))

        ctk.CTkLabel(prio_card, text="Prioridade",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(12, 4))
        self._priority = ctk.CTkComboBox(prio_card, values=[
            "Baixa — quando puder",
            "Media — essa semana",
            "Alta — urgente",
        ], font=ctk.CTkFont(size=12), width=300)
        self._priority.pack(anchor="w", padx=16, pady=(0, 12))

    # ── SEND PAGE ─────────────────────────────────────────────────────

    def _build_send_page(self):
        page = ctk.CTkFrame(self, fg_color=BG)
        self._pages["send"] = page

        ctk.CTkLabel(page, text="Enviar pro Dev",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(20, 12))

        # Summary
        summary_card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        summary_card.pack(fill="x", padx=24, pady=8)

        ctk.CTkLabel(summary_card, text="Resumo do Pacote",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(16, 8))

        self._send_summary = ctk.CTkLabel(summary_card, text="Carregando...",
                                           font=ctk.CTkFont(size=12),
                                           text_color=DIM, justify="left", anchor="w")
        self._send_summary.pack(fill="x", padx=16, pady=(0, 16))

        # Variables summary
        var_card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        var_card.pack(fill="x", padx=24, pady=8)

        ctk.CTkLabel(var_card, text="Variaveis Marcadas",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(16, 8))

        self._var_summary = ctk.CTkLabel(var_card, text="Nenhuma",
                                          font=ctk.CTkFont(size=12),
                                          text_color=DIM, justify="left", anchor="w")
        self._var_summary.pack(fill="x", padx=16, pady=(0, 16))

        # Buttons
        btn_frame = ctk.CTkFrame(page, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24, pady=20)

        ctk.CTkButton(btn_frame, text="Salvar Pacote (.zip)",
                      font=ctk.CTkFont(size=14, weight="bold"), height=46,
                      fg_color=GREEN, hover_color="#16a34a", corner_radius=10,
                      command=self._export_package).pack(side="left", padx=(0, 12))

        ctk.CTkButton(btn_frame, text="Copiar Pasta",
                      font=ctk.CTkFont(size=14), height=46,
                      fg_color=BLUE, hover_color="#2563eb", corner_radius=10,
                      command=self._copy_folder).pack(side="left", padx=(0, 12))

        # Output log
        log_card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=12)
        log_card.pack(fill="both", expand=True, padx=24, pady=(0, 20))

        ctk.CTkLabel(log_card, text="Log", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=16, pady=(12, 4))
        self._send_log = ctk.CTkTextbox(log_card, font=ctk.CTkFont(family="Consolas", size=10),
                                         fg_color="#0a0a1a", corner_radius=8)
        self._send_log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _update_send_summary(self):
        if not self._session_path:
            self._send_summary.configure(text="Nenhuma gravacao selecionada. Grave primeiro.")
            self._var_summary.configure(text="—")
            return

        name = self._workflow_name.get() or os.path.basename(self._session_path)
        desc = self._workflow_desc.get("0.0", "end").strip()
        scenarios = self._scenarios.get("0.0", "end").strip()
        freq = self._frequency.get()
        prio = self._priority.get()

        vars_marked = [
            (num, sv) for num, sv in self._step_vars.items()
            if sv.get("is_variable")
        ]

        summary = f"Workflow: {name}\n"
        summary += f"Passos: {len(self._steps)}\n"
        summary += f"Variaveis: {len(vars_marked)}\n"
        summary += f"Frequencia: {freq}\n"
        summary += f"Prioridade: {prio}\n"
        if desc:
            summary += f"Descricao: {desc[:100]}{'...' if len(desc) > 100 else ''}\n"
        if scenarios:
            summary += f"Cenarios: {scenarios[:100]}{'...' if len(scenarios) > 100 else ''}"

        self._send_summary.configure(text=summary)

        if vars_marked:
            var_text = ""
            for num, sv in sorted(vars_marked):
                vname = sv.get("var_name", f"variavel_{num}")
                var_text += f"  Passo {num:03d}: ${vname}\n"
            self._var_summary.configure(text=var_text.strip())
        else:
            self._var_summary.configure(text="Nenhuma variavel marcada. Volte em 'Revisar Passos' para marcar.")

    def _export_package(self):
        if not self._session_path:
            messagebox.showwarning("Aviso", "Nenhuma gravacao para exportar.")
            return

        dest = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("ZIP", "*.zip")],
            initialfile=f"actionshot_{os.path.basename(self._session_path)}.zip",
        )
        if not dest:
            return

        self._send_log.delete("0.0", "end")
        self._log_send("Empacotando...")

        try:
            self._save_user_config()
            self._log_send("Configuracoes salvas.")

            # Curate if available
            if PatternDetector:
                try:
                    detector = PatternDetector(self._session_path)
                    detector.curate_session()
                    self._log_send("Sessao curada (pre-processamento aplicado).")
                except Exception as e:
                    self._log_send(f"Curacaoo ignorada: {e}")

            # Compile IR if available
            if IRCompiler:
                try:
                    compiler = IRCompiler(self._session_path)
                    compiler.compile_and_save()
                    self._log_send("IR compilada.")
                except Exception as e:
                    self._log_send(f"IR ignorada: {e}")

            # Create zip
            base = os.path.splitext(dest)[0]
            shutil.make_archive(base, "zip", self._session_path)
            self._log_send(f"Pacote salvo: {dest}")
            self._log_send("Pronto! Envie o .zip para o desenvolvedor.")

            messagebox.showinfo("Sucesso", f"Pacote salvo em:\n{dest}")

        except Exception as e:
            self._log_send(f"Erro: {e}")
            messagebox.showerror("Erro", str(e))

    def _copy_folder(self):
        if not self._session_path:
            messagebox.showwarning("Aviso", "Nenhuma gravacao.")
            return

        dest = filedialog.askdirectory(title="Escolha onde copiar a pasta")
        if not dest:
            return

        try:
            self._save_user_config()
            target = os.path.join(dest, os.path.basename(self._session_path))
            shutil.copytree(self._session_path, target)
            self._log_send(f"Copiado para: {target}")
            messagebox.showinfo("Sucesso", f"Pasta copiada para:\n{target}")
        except Exception as e:
            self._log_send(f"Erro: {e}")

    def _save_user_config(self):
        """Save user annotations (variables, notes, config) into the session folder."""
        config = {
            "workflow_name": self._workflow_name.get(),
            "description": self._workflow_desc.get("0.0", "end").strip(),
            "scenarios": self._scenarios.get("0.0", "end").strip(),
            "frequency": self._frequency.get(),
            "priority": self._priority.get(),
            "variables": {},
            "step_notes": {},
        }

        for num, sv in self._step_vars.items():
            if sv.get("is_variable"):
                config["variables"][str(num)] = sv.get("var_name", f"variavel_{num}")
            if sv.get("note"):
                config["step_notes"][str(num)] = sv["note"]

        path = os.path.join(self._session_path, "user_config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def _log_send(self, msg):
        ts = time.strftime("%H:%M:%S")
        self._send_log.insert("end", f"[{ts}] {msg}\n")
        self._send_log.see("end")


# ── Entry point ───────────────────────────────────────────────────────

class ActionShotGUI:
    """Compatibility wrapper for existing main.py calls."""
    def __init__(self):
        self._app = ActionShotApp()

    def run(self):
        self._app.mainloop()
