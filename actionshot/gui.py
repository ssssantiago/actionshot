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

try:
    from .scope import WorkflowScope
except Exception:
    WorkflowScope = None


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
        self._current_scope = None

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
            ("setup", "Configurar Gravacao"),
            ("record", "Gravar"),
            ("review", "Revisar Passos"),
            ("review_post", "Revisao Pos-Gravacao"),
            ("builder", "Builder"),
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
        if page_id == "builder" and self._session_path:
            self._load_builder()
        if page_id == "send":
            self._update_send_summary()

    # ── Pages ─────────────────────────────────────────────────────────

    def _build_pages(self):
        self._pages = {}
        self._build_home_page()
        self._build_setup_page()
        self._build_record_page()
        self._build_review_page()
        self._build_review_post_page()
        self._build_builder_page()
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

    # ── SETUP PAGE ────────────────────────────────────────────────────

    def _build_setup_page(self):
        page = ctk.CTkFrame(self, fg_color=BG)
        self._pages["setup"] = page

        scroll = ctk.CTkScrollableFrame(page, fg_color=BG)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # Card container
        card = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=16)
        card.pack(fill="x", padx=30, pady=(30, 20))

        ctk.CTkLabel(card, text="Configurar Gravacao",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(24, 16))

        # Workflow name
        ctk.CTkLabel(card, text="Nome do Workflow",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(0, 4))
        self._setup_workflow_name = ctk.CTkEntry(
            card, placeholder_text="nome_do_workflow",
            font=ctk.CTkFont(size=13), height=36)
        self._setup_workflow_name.pack(fill="x", padx=24, pady=(0, 16))

        # Apps suportados
        ctk.CTkLabel(card, text="Apps suportados",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=24, pady=(0, 4))

        apps_card = ctk.CTkFrame(card, fg_color="#1e1e3a", corner_radius=10)
        apps_card.pack(fill="x", padx=24, pady=(0, 16))

        self._setup_app_vars = {}
        self._setup_conditional_frames = {}

        app_defs = [
            ("chrome", "Google Chrome (requer CDP)"),
            ("excel", "Microsoft Excel"),
            ("word", "Microsoft Word"),
            ("outlook", "Microsoft Outlook"),
            ("generic", "Outro aplicativo Windows (generico)"),
        ]

        for app_id, app_label in app_defs:
            var = ctk.BooleanVar(value=False)
            self._setup_app_vars[app_id] = var

            cb = ctk.CTkCheckBox(
                apps_card, text=app_label, variable=var,
                font=ctk.CTkFont(size=12),
                checkbox_width=20, checkbox_height=20,
                fg_color=ACCENT, hover_color=ACCENT_HOVER,
                command=lambda aid=app_id: self._setup_toggle_app(aid),
            )
            cb.pack(anchor="w", padx=16, pady=(10, 2))

            # Conditional fields frame (hidden by default)
            cond_frame = ctk.CTkFrame(apps_card, fg_color="transparent")
            self._setup_conditional_frames[app_id] = cond_frame
            # Don't pack yet — shown on toggle

        # Build conditional field widgets (but keep them hidden)
        self._setup_conditional_widgets = {}

        # Chrome: URL inicial
        chrome_frame = self._setup_conditional_frames["chrome"]
        ctk.CTkLabel(chrome_frame, text="URL inicial (opcional)",
                     font=ctk.CTkFont(size=11), text_color=DIM).pack(anchor="w", padx=32, pady=(4, 2))
        self._setup_chrome_url = ctk.CTkEntry(
            chrome_frame, placeholder_text="https://...",
            font=ctk.CTkFont(size=12), height=32)
        self._setup_chrome_url.pack(fill="x", padx=32, pady=(0, 8))

        # Excel: Arquivo inicial + file picker
        excel_frame = self._setup_conditional_frames["excel"]
        ctk.CTkLabel(excel_frame, text="Arquivo inicial (opcional)",
                     font=ctk.CTkFont(size=11), text_color=DIM).pack(anchor="w", padx=32, pady=(4, 2))
        excel_row = ctk.CTkFrame(excel_frame, fg_color="transparent")
        excel_row.pack(fill="x", padx=32, pady=(0, 8))
        self._setup_excel_file = ctk.CTkEntry(
            excel_row, placeholder_text="Caminho do arquivo .xlsx",
            font=ctk.CTkFont(size=12), height=32)
        self._setup_excel_file.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(excel_row, text="...", width=36, height=32,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(size=12),
                      command=lambda: self._setup_pick_file(self._setup_excel_file, "Excel", "*.xlsx *.xls *.csv")
                      ).pack(side="right")

        # Word: Arquivo inicial + file picker
        word_frame = self._setup_conditional_frames["word"]
        ctk.CTkLabel(word_frame, text="Arquivo inicial (opcional)",
                     font=ctk.CTkFont(size=11), text_color=DIM).pack(anchor="w", padx=32, pady=(4, 2))
        word_row = ctk.CTkFrame(word_frame, fg_color="transparent")
        word_row.pack(fill="x", padx=32, pady=(0, 8))
        self._setup_word_file = ctk.CTkEntry(
            word_row, placeholder_text="Caminho do arquivo .docx",
            font=ctk.CTkFont(size=12), height=32)
        self._setup_word_file.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(word_row, text="...", width=36, height=32,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(size=12),
                      command=lambda: self._setup_pick_file(self._setup_word_file, "Word", "*.docx *.doc")
                      ).pack(side="right")

        # Status / progress area
        self._setup_status_frame = ctk.CTkFrame(card, fg_color="transparent")
        self._setup_status_frame.pack(fill="x", padx=24, pady=(0, 8))
        self._setup_status_label = ctk.CTkLabel(
            self._setup_status_frame, text="", font=ctk.CTkFont(size=12),
            text_color=YELLOW)
        self._setup_status_label.pack(anchor="w")

        # Buttons
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24, pady=(0, 24))

        ctk.CTkButton(btn_frame, text="Cancelar", width=120, height=40,
                      fg_color=MUTED, hover_color="#64748b",
                      font=ctk.CTkFont(size=13), corner_radius=10,
                      command=lambda: self._show_page("home")).pack(side="left", padx=(0, 12))

        ctk.CTkButton(btn_frame, text="Preparar e Comecar", width=200, height=40,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      font=ctk.CTkFont(size=14, weight="bold"), corner_radius=10,
                      command=self._setup_prepare_and_start).pack(side="left")

    def _setup_toggle_app(self, app_id):
        """Show/hide conditional fields based on checkbox state."""
        frame = self._setup_conditional_frames.get(app_id)
        if not frame:
            return
        if self._setup_app_vars[app_id].get():
            frame.pack(fill="x", pady=(0, 4))
        else:
            frame.pack_forget()

    def _setup_pick_file(self, entry_widget, type_name, patterns):
        """Open file dialog and populate entry."""
        filetypes = [(type_name, patterns), ("Todos", "*.*")]
        path = filedialog.askopenfilename(title=f"Selecionar arquivo {type_name}",
                                          filetypes=filetypes)
        if path:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, path)

    def _setup_prepare_and_start(self):
        """Build WorkflowScope from form, prepare, then start recording."""
        # Gather form values
        workflow_name = self._setup_workflow_name.get().strip() or "workflow"
        selected_apps = [aid for aid, var in self._setup_app_vars.items() if var.get()]

        if not selected_apps:
            self._setup_status_label.configure(text="Selecione pelo menos um aplicativo.", text_color=RED)
            return

        # Build scope dict
        scope_data = {
            "workflow_name": workflow_name,
            "apps": selected_apps,
            "chrome_url": self._setup_chrome_url.get().strip() if "chrome" in selected_apps else "",
            "excel_file": self._setup_excel_file.get().strip() if "excel" in selected_apps else "",
            "word_file": self._setup_word_file.get().strip() if "word" in selected_apps else "",
        }

        # Try to create WorkflowScope
        if WorkflowScope is not None:
            try:
                self._current_scope = WorkflowScope(**scope_data)
            except Exception as e:
                self._current_scope = type("_Scope", (), scope_data)()
        else:
            # WorkflowScope not available — use a simple namespace
            self._current_scope = type("_Scope", (), scope_data)()

        self._setup_status_label.configure(text="", text_color=YELLOW)
        self._prepare_and_record()

    def _prepare_and_record(self):
        """Prepare scope (e.g. start Chrome CDP) then switch to record page and start."""
        scope = self._current_scope
        apps = getattr(scope, "apps", [])

        # Check if Chrome needs CDP preparation
        if "chrome" in apps:
            self._setup_status_label.configure(text="Preparando Chrome...", text_color=YELLOW)
            self.update_idletasks()

            # Check if Chrome is running without CDP
            try:
                from .cdp import check_cdp_available, is_chrome_running
                cdp_ok = check_cdp_available()
                chrome_running = is_chrome_running()

                if not cdp_ok and chrome_running:
                    # Need to restart Chrome — show dialog
                    self._show_chrome_restart_dialog()
                    return
                elif not cdp_ok and not chrome_running:
                    # Chrome not running — we can launch with CDP directly
                    self._setup_status_label.configure(
                        text="Chrome sera iniciado com modo de depuracao.", text_color=GREEN)
            except ImportError:
                # cdp module not available — proceed without preparation
                pass
            except Exception as e:
                self._setup_status_label.configure(
                    text=f"Aviso: nao foi possivel verificar Chrome: {e}", text_color=YELLOW)

        # Prepare other apps
        for app in apps:
            if app == "chrome":
                continue
            self._setup_status_label.configure(text=f"Preparando {app}...", text_color=YELLOW)
            self.update_idletasks()

        # Try scope preparation if available
        if hasattr(scope, "prepare") and callable(scope.prepare):
            def _do_prepare():
                try:
                    scope.prepare()
                    self.after(0, self._setup_prep_done)
                except Exception as e:
                    self.after(0, lambda: self._setup_prep_failed(str(e)))

            threading.Thread(target=_do_prepare, daemon=True).start()
            return

        # No special preparation needed — go straight to recording
        self._setup_prep_done()

    def _setup_prep_done(self):
        """Scope preparation succeeded — switch to record and start."""
        self._setup_status_label.configure(text="Pronto! Iniciando gravacao...", text_color=GREEN)
        self.update_idletasks()
        self._show_page("record")
        # Auto-start recording
        if not self.recording:
            self._toggle_recording()

    def _setup_prep_failed(self, error_msg):
        """Scope preparation failed — show error on setup page."""
        self._setup_status_label.configure(
            text=f"Erro na preparacao: {error_msg}", text_color=RED)

    # ── Chrome Restart Dialog ─────────────────────────────────────────

    def _show_chrome_restart_dialog(self):
        """Modal dialog when Chrome needs restart for CDP."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Preciso reiniciar o Chrome")
        dialog.geometry("500x280")
        dialog.configure(fg_color=BG)
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # Try dark title bar
        try:
            from ctypes import windll, byref, c_int
            dialog.update()
            hwnd = windll.user32.GetParent(dialog.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(c_int(2)), 4)
        except Exception:
            pass

        # Content
        ctk.CTkLabel(dialog, text="Preciso reiniciar o Chrome",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=TEXT).pack(padx=24, pady=(24, 8))

        ctk.CTkLabel(dialog,
                     text="Para gravar interacoes no Chrome, preciso abri-lo com modo de depuracao.\n"
                          "Salve seu trabalho antes de continuar.",
                     font=ctk.CTkFont(size=13), text_color=DIM,
                     wraplength=440, justify="center").pack(padx=24, pady=(0, 16))

        # Countdown label (hidden initially)
        self._chrome_countdown_label = ctk.CTkLabel(
            dialog, text="", font=ctk.CTkFont(size=13, weight="bold"),
            text_color=YELLOW)
        self._chrome_countdown_label.pack(padx=24, pady=(0, 8))

        # Buttons
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=24, pady=(0, 24))

        ctk.CTkButton(btn_frame, text="Cancelar", width=100, height=38,
                      fg_color=MUTED, hover_color="#64748b",
                      font=ctk.CTkFont(size=12), corner_radius=8,
                      command=lambda: self._chrome_dialog_cancel(dialog)
                      ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_frame, text="Salvar meu trabalho primeiro", width=200, height=38,
                      fg_color=BLUE, hover_color="#2563eb",
                      font=ctk.CTkFont(size=12), corner_radius=8,
                      command=lambda: self._chrome_dialog_wait(dialog)
                      ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_frame, text="Reiniciar Chrome agora", width=180, height=38,
                      fg_color=RED, hover_color="#dc2626",
                      font=ctk.CTkFont(size=12, weight="bold"), corner_radius=8,
                      command=lambda: self._chrome_dialog_restart_now(dialog)
                      ).pack(side="left")

        self._chrome_dialog_ref = dialog

    def _chrome_dialog_cancel(self, dialog):
        dialog.grab_release()
        dialog.destroy()
        self._setup_status_label.configure(text="Reinicio do Chrome cancelado.", text_color=MUTED)

    def _chrome_dialog_wait(self, dialog):
        """Start 15s countdown then restart Chrome."""
        self._chrome_countdown_remaining = 15
        self._chrome_dialog_tick(dialog)

    def _chrome_dialog_tick(self, dialog):
        remaining = self._chrome_countdown_remaining
        if remaining <= 0:
            self._chrome_dialog_restart_now(dialog)
            return
        self._chrome_countdown_label.configure(
            text=f"Reiniciando Chrome em {remaining}s...")
        self._chrome_countdown_remaining -= 1
        dialog.after(1000, lambda: self._chrome_dialog_tick(dialog))

    def _chrome_dialog_restart_now(self, dialog):
        """Restart Chrome with CDP and continue preparation."""
        dialog.grab_release()
        dialog.destroy()

        self._setup_status_label.configure(text="Reiniciando Chrome com CDP...", text_color=YELLOW)
        self.update_idletasks()

        def _do_restart():
            try:
                from .cdp import restart_chrome_with_cdp
                restart_chrome_with_cdp()
                self.after(0, self._setup_prep_done)
            except ImportError:
                self.after(0, lambda: self._setup_prep_failed(
                    "Modulo CDP nao disponivel"))
            except Exception as e:
                self.after(0, lambda: self._setup_prep_failed(str(e)))

        threading.Thread(target=_do_restart, daemon=True).start()

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

            # If we have a scope, go to post-recording review
            if self._current_scope is not None:
                self._populate_review_post()
                self._show_page("review_post")
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

    # ── REVIEW POST-RECORDING PAGE ──────────────────────────────────

    def _build_review_post_page(self):
        page = ctk.CTkFrame(self, fg_color=BG)
        self._pages["review_post"] = page

        scroll = ctk.CTkScrollableFrame(page, fg_color=BG)
        scroll.pack(fill="both", expand=True)

        # Header
        ctk.CTkLabel(scroll, text="Revisao Pos-Gravacao",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=30, pady=(24, 4))
        ctk.CTkLabel(scroll, text="Revise os aplicativos e dependencias detectados antes de salvar.",
                     font=ctk.CTkFont(size=12), text_color=DIM).pack(anchor="w", padx=30, pady=(0, 16))

        # Section 1 — Declared apps
        sec1 = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12)
        sec1.pack(fill="x", padx=30, pady=(0, 12))
        ctk.CTkLabel(sec1, text="Apps declarados",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 8))
        self._rp_declared_frame = ctk.CTkFrame(sec1, fg_color="transparent")
        self._rp_declared_frame.pack(fill="x", padx=20, pady=(0, 16))

        # Section 2 — Out-of-scope apps detected
        sec2 = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12)
        sec2.pack(fill="x", padx=30, pady=(0, 12))
        ctk.CTkLabel(sec2, text="Apps fora do escopo detectados",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=YELLOW).pack(anchor="w", padx=20, pady=(16, 8))
        ctk.CTkLabel(sec2, text="Esses aplicativos foram usados durante a gravacao mas nao estavam declarados.",
                     font=ctk.CTkFont(size=11), text_color=DIM,
                     wraplength=600).pack(anchor="w", padx=20, pady=(0, 4))
        self._rp_outofscope_frame = ctk.CTkFrame(sec2, fg_color="transparent")
        self._rp_outofscope_frame.pack(fill="x", padx=20, pady=(0, 16))

        # Section 3 — Dependencies detected
        sec3 = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12)
        sec3.pack(fill="x", padx=30, pady=(0, 12))
        ctk.CTkLabel(sec3, text="Dependencias detectadas",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=RED).pack(anchor="w", padx=20, pady=(16, 8))
        self._rp_deps_frame = ctk.CTkFrame(sec3, fg_color="transparent")
        self._rp_deps_frame.pack(fill="x", padx=20, pady=(0, 16))

        # Section 4 — Time gaps
        sec4 = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=12)
        sec4.pack(fill="x", padx=30, pady=(0, 12))
        ctk.CTkLabel(sec4, text="Intervalos de tempo",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=BLUE).pack(anchor="w", padx=20, pady=(16, 8))
        ctk.CTkLabel(sec4, text="Gaps maiores que 1 segundo entre passos consecutivos.",
                     font=ctk.CTkFont(size=11), text_color=DIM).pack(anchor="w", padx=20, pady=(0, 4))
        self._rp_gaps_frame = ctk.CTkFrame(sec4, fg_color="transparent")
        self._rp_gaps_frame.pack(fill="x", padx=20, pady=(0, 16))

        # Buttons
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", padx=30, pady=(8, 30))

        ctk.CTkButton(btn_frame, text="Descartar gravacao", width=180, height=44,
                      fg_color=RED, hover_color="#dc2626",
                      font=ctk.CTkFont(size=13), corner_radius=10,
                      command=self._rp_discard).pack(side="left", padx=(0, 12))

        ctk.CTkButton(btn_frame, text="Salvar workflow", width=180, height=44,
                      fg_color=GREEN, hover_color="#16a34a",
                      font=ctk.CTkFont(size=14, weight="bold"), corner_radius=10,
                      command=self._rp_save).pack(side="left")

        # State for checkboxes
        self._rp_declared_vars = {}
        self._rp_outofscope_vars = {}
        self._rp_dep_vars = {}

    def _populate_review_post(self):
        """Populate the review-post page with data from the recording session."""
        # Clear previous content
        for frame in (self._rp_declared_frame, self._rp_outofscope_frame,
                      self._rp_deps_frame, self._rp_gaps_frame):
            for w in frame.winfo_children():
                w.destroy()

        self._rp_declared_vars = {}
        self._rp_outofscope_vars = {}
        self._rp_dep_vars = {}

        scope = self._current_scope
        declared_apps = getattr(scope, "apps", []) if scope else []

        # Section 1 — Declared apps (checked by default)
        if declared_apps:
            app_labels = {
                "chrome": "Google Chrome",
                "excel": "Microsoft Excel",
                "word": "Microsoft Word",
                "outlook": "Microsoft Outlook",
                "generic": "Outro aplicativo Windows",
            }
            for app_id in declared_apps:
                var = ctk.BooleanVar(value=True)
                self._rp_declared_vars[app_id] = var
                label = app_labels.get(app_id, app_id)
                ctk.CTkCheckBox(
                    self._rp_declared_frame, text=f"\u2713 {label}",
                    variable=var, font=ctk.CTkFont(size=12),
                    checkbox_width=20, checkbox_height=20,
                    fg_color=GREEN, hover_color="#16a34a",
                ).pack(anchor="w", pady=2)
        else:
            ctk.CTkLabel(self._rp_declared_frame, text="Nenhum app declarado.",
                         text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w")

        # Analyze session for out-of-scope apps and time gaps
        detected_processes = set()
        step_timestamps = []

        if self._steps:
            for step in self._steps:
                step_num = step.get("step", 0)
                meta_path = os.path.join(self._session_path, f"{step_num:03d}_metadata.json")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        proc = meta.get("window", {}).get("process", "").lower()
                        if proc:
                            detected_processes.add(proc)
                        ts = meta.get("timestamp", "")
                        if ts:
                            step_timestamps.append((step_num, ts))
                    except Exception:
                        pass

        # Map declared apps to known process names
        declared_procs = set()
        proc_map = {
            "chrome": {"chrome", "chrome.exe"},
            "excel": {"excel", "excel.exe"},
            "word": {"winword", "winword.exe"},
            "outlook": {"outlook", "outlook.exe"},
        }
        for app_id in declared_apps:
            if app_id in proc_map:
                declared_procs.update(proc_map[app_id])

        # Section 2 — Out-of-scope processes
        out_of_scope = []
        for proc in sorted(detected_processes):
            proc_lower = proc.lower().replace(".exe", "")
            is_declared = False
            for app_id in declared_apps:
                if app_id in proc_map and proc_lower in {p.replace(".exe", "") for p in proc_map[app_id]}:
                    is_declared = True
                    break
                if app_id == "generic":
                    is_declared = True
                    break
            if not is_declared and proc_lower not in ("actionshot", "python", "pythonw", ""):
                out_of_scope.append(proc)

        if out_of_scope:
            for proc in out_of_scope:
                var = ctk.BooleanVar(value=False)
                self._rp_outofscope_vars[proc] = var
                ctk.CTkCheckBox(
                    self._rp_outofscope_frame,
                    text=f"  {proc}  (adicionar ao escopo)",
                    variable=var, font=ctk.CTkFont(size=12),
                    checkbox_width=20, checkbox_height=20,
                    fg_color=YELLOW, hover_color="#d97706",
                ).pack(anchor="w", pady=2)
        else:
            ctk.CTkLabel(self._rp_outofscope_frame,
                         text="Nenhum aplicativo fora do escopo detectado.",
                         text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w")

        # Section 3 — Dependencies / warnings
        deps = []
        if "chrome" in declared_apps:
            deps.append(("CDP ativo", "Chrome precisa estar em modo de depuracao (porta 9222)"))
        if "excel" in declared_apps:
            excel_file = getattr(scope, "excel_file", "")
            if excel_file:
                deps.append(("Arquivo Excel", f"Depende de: {os.path.basename(excel_file)}"))
        if "word" in declared_apps:
            word_file = getattr(scope, "word_file", "")
            if word_file:
                deps.append(("Arquivo Word", f"Depende de: {os.path.basename(word_file)}"))

        if deps:
            for dep_name, dep_desc in deps:
                var = ctk.BooleanVar(value=False)
                self._rp_dep_vars[dep_name] = var
                row = ctk.CTkFrame(self._rp_deps_frame, fg_color="transparent")
                row.pack(fill="x", pady=2)
                ctk.CTkCheckBox(
                    row, text="", variable=var,
                    checkbox_width=20, checkbox_height=20,
                    fg_color=RED, hover_color="#dc2626", width=24,
                ).pack(side="left")
                ctk.CTkLabel(row, text=f"\u26a0 {dep_name}: {dep_desc}",
                             font=ctk.CTkFont(size=12), text_color=YELLOW).pack(side="left", padx=(4, 0))
        else:
            ctk.CTkLabel(self._rp_deps_frame,
                         text="Nenhuma dependencia detectada.",
                         text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w")

        # Section 4 — Time gaps > 1s
        gaps = []
        from datetime import datetime as _dt
        sorted_ts = sorted(step_timestamps, key=lambda x: x[0])
        for i in range(1, len(sorted_ts)):
            prev_num, prev_ts = sorted_ts[i - 1]
            curr_num, curr_ts = sorted_ts[i]
            try:
                # Try parsing ISO timestamps
                t1 = _dt.fromisoformat(prev_ts)
                t2 = _dt.fromisoformat(curr_ts)
                gap = (t2 - t1).total_seconds()
                if gap > 1.0:
                    gaps.append((prev_num, curr_num, gap))
            except Exception:
                pass

        if gaps:
            for prev_num, curr_num, gap_sec in gaps:
                gap_text = f"Passo {prev_num:03d} -> {curr_num:03d}: {gap_sec:.1f}s"
                ctk.CTkLabel(self._rp_gaps_frame, text=f"  {gap_text}",
                             font=ctk.CTkFont(size=12), text_color=DIM).pack(anchor="w", pady=1)
        else:
            ctk.CTkLabel(self._rp_gaps_frame,
                         text="Nenhum intervalo significativo detectado.",
                         text_color=MUTED, font=ctk.CTkFont(size=11)).pack(anchor="w")

    def _rp_discard(self):
        """Discard the recording."""
        confirm = messagebox.askyesno(
            "Descartar gravacao",
            "Tem certeza que deseja descartar esta gravacao? Esta acao nao pode ser desfeita.")
        if confirm:
            if self._session_path and os.path.exists(self._session_path):
                try:
                    shutil.rmtree(self._session_path)
                except Exception:
                    pass
            self._session_path = None
            self._steps = []
            self._current_scope = None
            self._nav_status.configure(text="Nenhuma gravacao")
            self._refresh_recent()
            self._show_page("home")

    def _rp_save(self):
        """Save workflow with final scope (declared + user-added apps)."""
        # Build final apps list
        final_apps = []
        for app_id, var in self._rp_declared_vars.items():
            if var.get():
                final_apps.append(app_id)
        for proc, var in self._rp_outofscope_vars.items():
            if var.get():
                final_apps.append(proc)

        # Save scope info to session
        if self._session_path:
            scope_data = {
                "workflow_name": getattr(self._current_scope, "workflow_name", "workflow"),
                "final_apps": final_apps,
                "declared_apps": list(self._rp_declared_vars.keys()),
                "added_apps": [p for p, v in self._rp_outofscope_vars.items() if v.get()],
                "acknowledged_deps": [d for d, v in self._rp_dep_vars.items() if v.get()],
            }
            scope_path = os.path.join(self._session_path, "workflow_scope.json")
            try:
                with open(scope_path, "w", encoding="utf-8") as f:
                    json.dump(scope_data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass

            # Also export session if export module available
            try:
                from .export import export_session
                export_session(self._session_path, scope=scope_data)
            except Exception:
                pass

        messagebox.showinfo("Salvo", "Workflow salvo com sucesso!")
        self._show_page("review")

    # ── BUILDER PAGE (n8n-style visual workflow) ─────────────────────

    # Node colors by action type
    _NODE_COLORS = {
        "click": ("#ef4444", "#fca5a5"),
        "drag": ("#f97316", "#fdba74"),
        "scroll": ("#3b82f6", "#93c5fd"),
        "keypress": ("#eab308", "#fde047"),
        "fill_field": ("#8b5cf6", "#c4b5fd"),
        "select_option": ("#06b6d4", "#67e8f9"),
        "wait": ("#6b7280", "#d1d5db"),
        "condition": ("#10b981", "#6ee7b7"),
        "loop": ("#ec4899", "#f9a8d4"),
        "default": ("#7c3aed", "#c4b5fd"),
    }

    NODE_W = 200
    NODE_H = 70
    NODE_GAP_X = 80
    NODE_GAP_Y = 30
    CANVAS_PAD = 40

    def _build_builder_page(self):
        page = ctk.CTkFrame(self, fg_color=BG)
        self._pages["builder"] = page

        # Toolbar
        toolbar = ctk.CTkFrame(page, fg_color=CARD, height=50, corner_radius=0)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        ctk.CTkLabel(toolbar, text="  Workflow Builder",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=TEXT).pack(side="left", padx=16)

        # Add special nodes
        ctk.CTkButton(toolbar, text="+ Condicao", width=100, height=32,
                      fg_color="#10b981", hover_color="#059669",
                      font=ctk.CTkFont(size=11),
                      command=self._builder_add_condition).pack(side="right", padx=4, pady=8)
        ctk.CTkButton(toolbar, text="+ Loop", width=80, height=32,
                      fg_color="#ec4899", hover_color="#db2777",
                      font=ctk.CTkFont(size=11),
                      command=self._builder_add_loop).pack(side="right", padx=4, pady=8)
        ctk.CTkButton(toolbar, text="+ Espera", width=80, height=32,
                      fg_color="#6b7280", hover_color="#4b5563",
                      font=ctk.CTkFont(size=11),
                      command=self._builder_add_wait).pack(side="right", padx=4, pady=8)

        self._builder_delete_btn = ctk.CTkButton(
            toolbar, text="Excluir", width=80, height=32,
            fg_color=RED, hover_color="#dc2626",
            font=ctk.CTkFont(size=11),
            command=self._builder_delete_selected)
        self._builder_delete_btn.pack(side="right", padx=4, pady=8)

        ctk.CTkButton(toolbar, text="Zoom +", width=60, height=32,
                      fg_color=MUTED, hover_color="#64748b",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._builder_zoom(1.15)).pack(side="right", padx=2, pady=8)
        ctk.CTkButton(toolbar, text="Zoom -", width=60, height=32,
                      fg_color=MUTED, hover_color="#64748b",
                      font=ctk.CTkFont(size=11),
                      command=lambda: self._builder_zoom(0.87)).pack(side="right", padx=2, pady=8)

        # Canvas
        canvas_frame = ctk.CTkFrame(page, fg_color="#0a0a18", corner_radius=0)
        canvas_frame.pack(fill="both", expand=True)

        self._builder_canvas = tk.Canvas(
            canvas_frame, bg="#0a0a18", highlightthickness=0,
            scrollregion=(0, 0, 3000, 3000),
        )

        h_scroll = tk.Scrollbar(canvas_frame, orient="horizontal", command=self._builder_canvas.xview)
        v_scroll = tk.Scrollbar(canvas_frame, orient="vertical", command=self._builder_canvas.yview)
        self._builder_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        h_scroll.pack(side="bottom", fill="x")
        v_scroll.pack(side="right", fill="y")
        self._builder_canvas.pack(side="left", fill="both", expand=True)

        # Draw grid
        self._builder_draw_grid()

        # Drag state
        self._builder_nodes = []       # list of node dicts
        self._builder_connections = []  # list of (from_idx, to_idx)
        self._builder_selected = -1
        self._builder_drag_data = None
        self._builder_scale = 1.0

        # Binds
        self._builder_canvas.bind("<ButtonPress-1>", self._builder_on_press)
        self._builder_canvas.bind("<B1-Motion>", self._builder_on_drag)
        self._builder_canvas.bind("<ButtonRelease-1>", self._builder_on_release)
        self._builder_canvas.bind("<MouseWheel>", self._builder_on_wheel)
        self._builder_canvas.bind("<Double-Button-1>", self._builder_on_double_click)

        # Right panel: node properties
        self._builder_props = ctk.CTkFrame(page, fg_color=CARD, width=280, corner_radius=0)
        self._builder_props.pack(side="right", fill="y", before=canvas_frame)
        self._builder_props.pack_propagate(False)

        ctk.CTkLabel(self._builder_props, text="Propriedades",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=TEXT).pack(padx=12, pady=(12, 8), anchor="w")

        self._prop_frame = ctk.CTkScrollableFrame(self._builder_props, fg_color="transparent")
        self._prop_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._builder_prop_widgets = {}

    def _builder_draw_grid(self):
        c = self._builder_canvas
        c.delete("grid")
        for x in range(0, 3000, 40):
            c.create_line(x, 0, x, 3000, fill="#151530", tags="grid")
        for y in range(0, 3000, 40):
            c.create_line(0, y, 3000, y, fill="#151530", tags="grid")

    def _load_builder(self):
        """Populate builder canvas from session steps."""
        if not self._steps:
            return
        if self._builder_nodes:
            return  # already loaded

        self._builder_nodes = []
        self._builder_connections = []
        self._builder_selected = -1

        x = self.CANVAS_PAD
        y = self.CANVAS_PAD
        col = 0
        max_per_row = 4

        for i, step in enumerate(self._steps):
            num = step.get("step", i + 1)
            action = step.get("action", "unknown")
            desc = step.get("description", "")

            # Determine node type
            node_type = "default"
            for key in self._NODE_COLORS:
                if key in action:
                    node_type = key
                    break

            node = {
                "id": i,
                "step": num,
                "type": node_type,
                "action": action,
                "label": self._node_label(action, desc),
                "desc": desc,
                "x": x,
                "y": y,
                "w": self.NODE_W,
                "h": self.NODE_H,
                "extra": {},  # user-added data (condition text, loop count, etc.)
            }
            self._builder_nodes.append(node)

            # Connect to previous
            if i > 0:
                self._builder_connections.append((i - 1, i))

            col += 1
            if col >= max_per_row:
                col = 0
                x = self.CANVAS_PAD
                y += self.NODE_H + self.NODE_GAP_Y + 40
            else:
                x += self.NODE_W + self.NODE_GAP_X

        self._builder_redraw()

    def _node_label(self, action, desc):
        labels = {
            "left_click": "Clique",
            "right_click": "Clique Dir.",
            "keypress": "Digitar",
            "scroll": "Rolar",
            "condition": "Condicao",
            "loop": "Loop",
            "wait": "Espera",
        }
        for key, val in labels.items():
            if key in action:
                # Add short description
                short = desc[:25] + "..." if len(desc) > 25 else desc
                return f"{val}\n{short}"
        short = desc[:25] + "..." if len(desc) > 25 else desc
        return f"{action[:15]}\n{short}"

    def _builder_redraw(self):
        c = self._builder_canvas
        c.delete("node")
        c.delete("conn")
        c.delete("badge")
        c.delete("label")
        c.delete("port")

        s = self._builder_scale

        # Draw connections first (behind nodes)
        for from_idx, to_idx in self._builder_connections:
            if from_idx >= len(self._builder_nodes) or to_idx >= len(self._builder_nodes):
                continue
            n1 = self._builder_nodes[from_idx]
            n2 = self._builder_nodes[to_idx]

            x1 = (n1["x"] + n1["w"]) * s
            y1 = (n1["y"] + n1["h"] / 2) * s
            x2 = n2["x"] * s
            y2 = (n2["y"] + n2["h"] / 2) * s

            # Bezier-like curve
            mid_x = (x1 + x2) / 2
            c.create_line(
                x1, y1, mid_x, y1, mid_x, y2, x2, y2,
                fill="#4a4a7a", width=2, smooth=True, tags="conn",
            )

            # Arrow at end
            c.create_polygon(
                x2 - 8 * s, y2 - 5 * s,
                x2, y2,
                x2 - 8 * s, y2 + 5 * s,
                fill="#4a4a7a", outline="", tags="conn",
            )

        # Draw nodes
        for i, node in enumerate(self._builder_nodes):
            nx = node["x"] * s
            ny = node["y"] * s
            nw = node["w"] * s
            nh = node["h"] * s

            colors = self._NODE_COLORS.get(node["type"], self._NODE_COLORS["default"])
            bg_color = colors[0]
            is_selected = (i == self._builder_selected)

            # Shadow
            c.create_rectangle(
                nx + 3, ny + 3, nx + nw + 3, ny + nh + 3,
                fill="#05051a", outline="", tags="node",
            )

            # Node body
            outline = "#ffffff" if is_selected else "#2a2a5a"
            outline_w = 2 if is_selected else 1
            c.create_rectangle(
                nx, ny, nx + nw, ny + nh,
                fill="#1e1e3e", outline=outline, width=outline_w, tags="node",
            )

            # Left color stripe
            stripe_w = 6 * s
            c.create_rectangle(
                nx, ny, nx + stripe_w, ny + nh,
                fill=bg_color, outline="", tags="node",
            )

            # Step badge
            badge_size = 22 * s
            c.create_oval(
                nx + stripe_w + 6 * s, ny + 6 * s,
                nx + stripe_w + 6 * s + badge_size, ny + 6 * s + badge_size,
                fill=bg_color, outline="", tags="badge",
            )
            c.create_text(
                nx + stripe_w + 6 * s + badge_size / 2,
                ny + 6 * s + badge_size / 2,
                text=str(node["step"]), fill="white",
                font=("Consolas", max(int(9 * s), 7), "bold"), tags="badge",
            )

            # Label text
            label_x = nx + stripe_w + 6 * s + badge_size + 8 * s
            lines = node["label"].split("\n")
            for li, line in enumerate(lines):
                font_size = max(int(11 * s), 8) if li == 0 else max(int(9 * s), 7)
                color = TEXT if li == 0 else DIM
                weight = "bold" if li == 0 else "normal"
                c.create_text(
                    label_x, ny + 16 * s + li * 18 * s,
                    text=line, fill=color, anchor="w",
                    font=("Segoe UI", font_size, weight), tags="label",
                )

            # Variable indicator
            sv = self._step_vars.get(node["step"], {})
            if sv.get("is_variable"):
                c.create_text(
                    nx + nw - 10 * s, ny + 10 * s,
                    text="$", fill=YELLOW,
                    font=("Consolas", max(int(14 * s), 9), "bold"), tags="badge",
                )

            # Output port (right)
            port_r = 5 * s
            c.create_oval(
                nx + nw - port_r, ny + nh / 2 - port_r,
                nx + nw + port_r, ny + nh / 2 + port_r,
                fill=bg_color, outline="#2a2a5a", tags="port",
            )
            # Input port (left)
            c.create_oval(
                nx - port_r, ny + nh / 2 - port_r,
                nx + port_r, ny + nh / 2 + port_r,
                fill=bg_color, outline="#2a2a5a", tags="port",
            )

        # Update scroll region
        if self._builder_nodes:
            max_x = max(n["x"] + n["w"] for n in self._builder_nodes) + 200
            max_y = max(n["y"] + n["h"] for n in self._builder_nodes) + 200
            c.configure(scrollregion=(0, 0, max_x * s, max_y * s))

    # ── Builder events ────────────────────────────────────────────────

    def _builder_hit_test(self, cx, cy):
        """Return index of node at canvas coords, or -1."""
        s = self._builder_scale
        for i, node in enumerate(self._builder_nodes):
            nx, ny = node["x"] * s, node["y"] * s
            nw, nh = node["w"] * s, node["h"] * s
            if nx <= cx <= nx + nw and ny <= cy <= ny + nh:
                return i
        return -1

    def _builder_on_press(self, event):
        cx = self._builder_canvas.canvasx(event.x)
        cy = self._builder_canvas.canvasy(event.y)
        hit = self._builder_hit_test(cx, cy)

        self._builder_selected = hit
        if hit >= 0:
            node = self._builder_nodes[hit]
            self._builder_drag_data = {
                "idx": hit,
                "off_x": cx - node["x"] * self._builder_scale,
                "off_y": cy - node["y"] * self._builder_scale,
            }
            self._builder_show_props(hit)
        else:
            self._builder_drag_data = None
            self._builder_clear_props()

        self._builder_redraw()

    def _builder_on_drag(self, event):
        if not self._builder_drag_data:
            return
        cx = self._builder_canvas.canvasx(event.x)
        cy = self._builder_canvas.canvasy(event.y)
        s = self._builder_scale
        idx = self._builder_drag_data["idx"]
        node = self._builder_nodes[idx]
        node["x"] = max(0, (cx - self._builder_drag_data["off_x"]) / s)
        node["y"] = max(0, (cy - self._builder_drag_data["off_y"]) / s)
        self._builder_redraw()

    def _builder_on_release(self, event):
        self._builder_drag_data = None

    def _builder_on_wheel(self, event):
        if event.delta > 0:
            self._builder_zoom(1.08)
        else:
            self._builder_zoom(0.93)

    def _builder_on_double_click(self, event):
        cx = self._builder_canvas.canvasx(event.x)
        cy = self._builder_canvas.canvasy(event.y)
        hit = self._builder_hit_test(cx, cy)
        if hit >= 0:
            self._builder_selected = hit
            self._builder_show_props(hit)
            self._builder_redraw()

    def _builder_zoom(self, factor):
        self._builder_scale = max(0.3, min(3.0, self._builder_scale * factor))
        self._builder_redraw()

    # ── Builder: add special nodes ────────────────────────────────────

    def _builder_add_condition(self):
        self._builder_add_special("condition", "Condicao\nSe X entao...")

    def _builder_add_loop(self):
        self._builder_add_special("loop", "Loop\nRepetir N vezes")

    def _builder_add_wait(self):
        self._builder_add_special("wait", "Espera\nAguardar tela mudar")

    def _builder_add_special(self, node_type, label):
        # Place after last node
        if self._builder_nodes:
            last = self._builder_nodes[-1]
            x = last["x"] + last["w"] + self.NODE_GAP_X
            y = last["y"]
        else:
            x, y = self.CANVAS_PAD, self.CANVAS_PAD

        new_idx = len(self._builder_nodes)
        node = {
            "id": new_idx,
            "step": new_idx + 1,
            "type": node_type,
            "action": node_type,
            "label": label,
            "desc": "",
            "x": x, "y": y,
            "w": self.NODE_W, "h": self.NODE_H,
            "extra": {},
        }
        self._builder_nodes.append(node)

        # Connect from previous
        if new_idx > 0:
            self._builder_connections.append((new_idx - 1, new_idx))

        self._builder_selected = new_idx
        self._builder_show_props(new_idx)
        self._builder_redraw()

    def _builder_delete_selected(self):
        idx = self._builder_selected
        if idx < 0 or idx >= len(self._builder_nodes):
            return

        # Remove connections involving this node
        self._builder_connections = [
            (a, b) for a, b in self._builder_connections
            if a != idx and b != idx
        ]
        # Reindex connections
        self._builder_connections = [
            (a if a < idx else a - 1, b if b < idx else b - 1)
            for a, b in self._builder_connections
        ]

        # Reconnect neighbors
        prev = [a for a, b in self._builder_connections if b == idx - 1] if idx > 0 else []
        nxt = [b for a, b in self._builder_connections if a == idx] if idx < len(self._builder_nodes) - 1 else []

        self._builder_nodes.pop(idx)
        self._builder_selected = -1
        self._builder_clear_props()
        self._builder_redraw()

    # ── Builder: properties panel ─────────────────────────────────────

    def _builder_clear_props(self):
        for w in self._prop_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._prop_frame, text="Selecione um no",
                     text_color=MUTED, font=ctk.CTkFont(size=11)).pack(pady=20)

    def _builder_show_props(self, idx):
        for w in self._prop_frame.winfo_children():
            w.destroy()

        if idx < 0 or idx >= len(self._builder_nodes):
            self._builder_clear_props()
            return

        node = self._builder_nodes[idx]
        f = self._prop_frame

        # Node type badge
        colors = self._NODE_COLORS.get(node["type"], self._NODE_COLORS["default"])
        ctk.CTkLabel(f, text=f"  {node['type'].upper()}  ",
                     fg_color=colors[0], corner_radius=6,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color="white").pack(anchor="w", pady=(0, 8))

        # Step number
        ctk.CTkLabel(f, text=f"Passo #{node['step']}", text_color=TEXT,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(0, 4))

        # Description
        ctk.CTkLabel(f, text="Descricao:", text_color=DIM,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(8, 2))
        desc_entry = ctk.CTkTextbox(f, height=60, font=ctk.CTkFont(size=11),
                                     fg_color="#0a0a1a", corner_radius=6)
        desc_entry.pack(fill="x", pady=(0, 8))
        desc_entry.insert("0.0", node.get("desc", ""))
        desc_entry.bind("<FocusOut>", lambda e, i=idx, w=desc_entry: self._builder_update_desc(i, w))

        # Type-specific fields
        if node["type"] == "condition":
            ctk.CTkLabel(f, text="Condicao (se...):", text_color=DIM,
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(4, 2))
            cond_entry = ctk.CTkEntry(f, placeholder_text="Ex: valor > 5000",
                                       font=ctk.CTkFont(size=11))
            cond_entry.pack(fill="x", pady=(0, 4))
            if node["extra"].get("condition"):
                cond_entry.insert(0, node["extra"]["condition"])
            cond_entry.bind("<FocusOut>",
                            lambda e, i=idx, w=cond_entry: self._builder_set_extra(i, "condition", w.get()))

            ctk.CTkLabel(f, text="Senao:", text_color=DIM,
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(4, 2))
            else_entry = ctk.CTkEntry(f, placeholder_text="Ex: enviar para aprovacao",
                                       font=ctk.CTkFont(size=11))
            else_entry.pack(fill="x", pady=(0, 4))
            if node["extra"].get("else_action"):
                else_entry.insert(0, node["extra"]["else_action"])
            else_entry.bind("<FocusOut>",
                            lambda e, i=idx, w=else_entry: self._builder_set_extra(i, "else_action", w.get()))

        elif node["type"] == "loop":
            ctk.CTkLabel(f, text="Repetir:", text_color=DIM,
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(4, 2))
            loop_type = ctk.CTkComboBox(f, values=[
                "Para cada linha da planilha",
                "Ate condicao ser verdadeira",
                "N vezes",
            ], font=ctk.CTkFont(size=11), width=240)
            loop_type.pack(fill="x", pady=(0, 4))
            if node["extra"].get("loop_type"):
                loop_type.set(node["extra"]["loop_type"])
            loop_type.bind("<<ComboboxSelected>>",
                           lambda e, i=idx, w=loop_type: self._builder_set_extra(i, "loop_type", w.get()))

            ctk.CTkLabel(f, text="Quantidade / Condicao:", text_color=DIM,
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(4, 2))
            loop_val = ctk.CTkEntry(f, placeholder_text="Ex: 10 ou 'ate acabar linhas'",
                                     font=ctk.CTkFont(size=11))
            loop_val.pack(fill="x", pady=(0, 4))
            if node["extra"].get("loop_value"):
                loop_val.insert(0, node["extra"]["loop_value"])
            loop_val.bind("<FocusOut>",
                          lambda e, i=idx, w=loop_val: self._builder_set_extra(i, "loop_value", w.get()))

        elif node["type"] == "wait":
            ctk.CTkLabel(f, text="Esperar por:", text_color=DIM,
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(4, 2))
            wait_type = ctk.CTkComboBox(f, values=[
                "Tela mudar",
                "Elemento aparecer",
                "Tempo fixo (segundos)",
                "Pagina carregar",
            ], font=ctk.CTkFont(size=11), width=240)
            wait_type.pack(fill="x", pady=(0, 4))
            if node["extra"].get("wait_type"):
                wait_type.set(node["extra"]["wait_type"])

            ctk.CTkLabel(f, text="Timeout (seg):", text_color=DIM,
                         font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(4, 2))
            timeout_entry = ctk.CTkEntry(f, placeholder_text="10", font=ctk.CTkFont(size=11))
            timeout_entry.pack(fill="x", pady=(0, 4))
            if node["extra"].get("timeout"):
                timeout_entry.insert(0, str(node["extra"]["timeout"]))

        # Variable toggle
        ctk.CTkFrame(f, fg_color=MUTED, height=1).pack(fill="x", pady=12)

        sv = self._step_vars.get(node["step"], {})
        is_var = ctk.BooleanVar(value=sv.get("is_variable", False))
        ctk.CTkCheckBox(f, text="Marcar como Variavel",
                        variable=is_var, font=ctk.CTkFont(size=11),
                        fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        command=lambda i=idx, v=is_var: self._builder_toggle_var(i, v.get())
                        ).pack(anchor="w", pady=(0, 4))

        if sv.get("is_variable"):
            var_name_entry = ctk.CTkEntry(f, placeholder_text="Nome da variavel",
                                           font=ctk.CTkFont(size=11))
            var_name_entry.pack(fill="x", pady=(0, 4))
            if sv.get("var_name"):
                var_name_entry.insert(0, sv["var_name"])

        # Note
        ctk.CTkLabel(f, text="Nota para o dev:", text_color=DIM,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(8, 2))
        note_entry = ctk.CTkEntry(f, placeholder_text="Instrucoes especiais...",
                                   font=ctk.CTkFont(size=11))
        note_entry.pack(fill="x", pady=(0, 4))
        if sv.get("note"):
            note_entry.insert(0, sv["note"])

    def _builder_update_desc(self, idx, widget):
        if idx < len(self._builder_nodes):
            self._builder_nodes[idx]["desc"] = widget.get("0.0", "end").strip()

    def _builder_set_extra(self, idx, key, value):
        if idx < len(self._builder_nodes):
            self._builder_nodes[idx]["extra"][key] = value

    def _builder_toggle_var(self, idx, is_var):
        if idx < len(self._builder_nodes):
            step_num = self._builder_nodes[idx]["step"]
            if step_num not in self._step_vars:
                self._step_vars[step_num] = {}
            self._step_vars[step_num]["is_variable"] = is_var
            self._builder_show_props(idx)
            self._builder_redraw()

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
