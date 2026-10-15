import os
import io
import re
import csv
import stat
import shutil
import webbrowser
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from datetime import datetime

# Spalten einer Fotoliste (WNK-Format), in dieser Reihenfolge für neue Listen
FOTOLISTE_FIELDS = ["Aktivitaet", "StellenNr", "PosNr", "Fotograf", "FotoDatum", "Kommentar"]


class PhotoRenamerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GRABUNGSTAUGLICH")
        self.root.geometry("780x650")
        self.root.minsize(600, 460)

        self.is_dark_mode = True
        self.set_theme_colors()
        self.root.configure(bg=self.bg_color)

        self.rename_history = {}
        self.created_directories = []
        self.last_update_actions = []
        self.undo_stack = []       # je Aktion eine Gruppe, siehe _begin_undo_group
        self._chosen_targets = {}  # Aktivität -> zuletzt gespeicherte Fotoliste

        self.additional_photographers_entries_einzel = []
        self.batch_blocks = []

        self.var_ignore_exif_einzel = tk.BooleanVar()
        self.var_ignore_exif_batch = tk.BooleanVar()

        self.create_widgets()
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        w = event.widget
        while w is not None:
            if isinstance(w, (scrolledtext.ScrolledText, tk.Text)):
                return
            if isinstance(w, tk.Canvas):
                try:
                    w.yview_scroll(-1 * (event.delta // 120), "units")
                except Exception:
                    pass
                return
            w = getattr(w, 'master', None)

    def set_theme_colors(self):
        if self.is_dark_mode:
            self.bg_color = "#000000"
            self.fg_color = "#FFFFFF"
            self.entry_bg = "#222222"
            self.btn_bg_highlight = "#444444"
            self.log_fg = "#00ff00"
        else:
            self.bg_color = "#F0F0F0"
            self.fg_color = "#000000"
            self.entry_bg = "#FFFFFF"
            self.btn_bg_highlight = "#D0D0D0"
            self.log_fg = "#006600"

    def apply_ttk_styles(self):
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook', background=self.bg_color, borderwidth=0)
        style.configure('TFrame', background=self.bg_color)
        tab_bg = "#555555" if self.is_dark_mode else "#FFFFFF"
        tab_fg = "#FFFFFF" if self.is_dark_mode else "#000000"
        style.configure('TNotebook.Tab',
                        background="#333333" if self.is_dark_mode else "#DDDDDD",
                        foreground=tab_fg, padding=[10, 4])
        style.map('TNotebook.Tab', background=[('selected', tab_bg)])

    def create_widgets(self):
        self.apply_ttk_styles()

        # --- HEADER ---
        frame_header = tk.Frame(self.root, bg=self.bg_color)
        frame_header.pack(fill="x", padx=8, pady=(4, 2))

        self.btn_help = tk.Button(
            frame_header, text="📖 Anleitung",
            bg="#ffff00", fg="#000000", font=('Helvetica', 8, 'bold'),
            padx=6, pady=2, command=self.show_readme_popup)
        self.btn_help._custom_color = True
        self.btn_help.pack(side="left", padx=(0, 3))

        self.btn_theme_toggle = tk.Button(
            frame_header,
            text="☀ Light Mode" if self.is_dark_mode else "☾ Dark Mode",
            bg="#333333" if self.is_dark_mode else "#DDDDDD",
            fg="#FFFFFF" if self.is_dark_mode else "#000000",
            font=('Helvetica', 8), bd=1, relief="ridge", padx=6, pady=2,
            command=self.toggle_theme)
        self.btn_theme_toggle._custom_color = True
        self.btn_theme_toggle.pack(side="left", padx=(0, 3))

        btn_paypal = tk.Button(
            frame_header, text="DU BEKOMMST ES NICHT WIEDER",
            bg="#0070ba", fg="white", font=('Helvetica', 8, 'bold'),
            relief="groove", padx=6, pady=2, command=self.open_paypal)
        btn_paypal._custom_color = True
        btn_paypal.pack(side="left", padx=(0, 3))

        self.btn_license = tk.Button(
            frame_header, text="© Lizenz / Impressum",
            font=('Helvetica', 8, 'underline'), bg=self.bg_color,
            fg="#aaaaaa" if self.is_dark_mode else "#555555",
            bd=0, cursor="hand2", command=self.show_license_popup)
        self.btn_license._custom_color = True
        self.btn_license.pack(side="left", padx=4)

        # --- NOTEBOOK ---
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(2, 4))

        self.tab_einzel = tk.Frame(self.notebook, bg=self.bg_color)
        self.tab_batch = tk.Frame(self.notebook, bg=self.bg_color)
        self.tab_protokoll = tk.Frame(self.notebook, bg=self.bg_color)

        self.notebook.add(self.tab_einzel, text="  Einzel-Modus  ")
        self.notebook.add(self.tab_batch, text="  Batch-Modus  ")
        self.notebook.add(self.tab_protokoll, text="  Protokoll  ")

        self.create_einzel_tab()
        self.create_batch_tab()
        self.create_protokoll_tab()

    def _create_frame(self, parent, text):
        return tk.LabelFrame(parent, text=text, bg=self.bg_color, fg=self.fg_color,
                             highlightbackground=self.fg_color, highlightthickness=1,
                             padx=6, pady=5)

    # =========================================================================
    # REITER 1: EINZEL-MODUS
    # =========================================================================
    def create_einzel_tab(self):
        container = tk.Canvas(self.tab_einzel, bg=self.bg_color, highlightthickness=0)
        scroll = tk.Scrollbar(self.tab_einzel, orient="vertical", command=container.yview)
        scrollable_frame = tk.Frame(container, bg=self.bg_color)
        scrollable_frame.bind(
            "<Configure>", lambda e: container.configure(scrollregion=container.bbox("all")))
        win_id = container.create_window((0, 0), window=scrollable_frame, anchor="nw")
        container.bind("<Configure>", lambda e: container.itemconfig(win_id, width=e.width))
        container.configure(yscrollcommand=scroll.set)
        container.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # 1. Basisdaten
        frame_top = self._create_frame(scrollable_frame, " 1. Basisdaten ")
        frame_top.pack(fill="x", padx=6, pady=3)
        frame_top.columnconfigure(1, weight=1)

        tk.Label(frame_top, text="Aktivität (z.B. OV 2021/1023):",
                 bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, sticky="w", pady=1)
        self.ent_activity_einzel = tk.Entry(
            frame_top, width=22, bg=self.entry_bg, fg=self.fg_color,
            insertbackground=self.fg_color)
        self.ent_activity_einzel.grid(row=0, column=1, padx=4, sticky="w", pady=1)

        tk.Label(frame_top, text="Quell-Ordner:",
                 bg=self.bg_color, fg=self.fg_color).grid(row=1, column=0, sticky="w", pady=1)
        self.ent_dir_einzel = tk.Entry(
            frame_top, width=36, bg=self.entry_bg, fg=self.fg_color,
            insertbackground=self.fg_color)
        self.ent_dir_einzel.grid(row=1, column=1, padx=4, sticky="ew", pady=1)
        tk.Button(frame_top, text="Durchsuchen…",
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  command=self.browse_dir_einzel).grid(row=1, column=2, padx=3, sticky="ew")

        # 2. Filter & Optionen
        frame_filter = self._create_frame(scrollable_frame, " 2. Filter & Optionen ")
        frame_filter.pack(fill="x", padx=6, pady=3)
        tk.Label(frame_filter,
                 text="Nur folgende Stellen berücksichtigen (kommagetrennt, leer = alle):",
                 bg=self.bg_color, fg=self.fg_color).pack(anchor="w")
        self.ent_filter_stellen_einzel = tk.Entry(
            frame_filter, width=55, bg=self.entry_bg, fg=self.fg_color,
            insertbackground=self.fg_color)
        self.ent_filter_stellen_einzel.pack(anchor="w", pady=2)
        tk.Checkbutton(
            frame_filter, text="Tolerieren: EXIF-Datum älter als Aktivitätsjahr",
            variable=self.var_ignore_exif_einzel, bg=self.bg_color, fg=self.fg_color,
            selectcolor=self.entry_bg, activebackground=self.bg_color,
            activeforeground=self.fg_color).pack(anchor="w", pady=1)

        # 3. Fotografen
        frame_photographers = self._create_frame(
            scrollable_frame, " 3. Fotograf*innen-Zuordnung (Optional) ")
        frame_photographers.pack(fill="x", padx=6, pady=3)
        tk.Label(frame_photographers, text="Hauptfotograf*in (Standard):",
                 font=('Helvetica', 9, 'bold'), bg=self.bg_color, fg=self.fg_color
                 ).grid(row=0, column=0, sticky="w", pady=1)
        self.ent_main_photo_einzel = tk.Entry(
            frame_photographers, width=22, bg=self.entry_bg, fg=self.fg_color,
            insertbackground=self.fg_color)
        self.ent_main_photo_einzel.grid(row=0, column=1, columnspan=2, sticky="w", padx=4, pady=1)
        tk.Button(frame_photographers, text="➕ Weitere*n Fotograf*in",
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  command=lambda: self.add_photo_row(
                      self.scroll_frame_photo_einzel,
                      self.canvas_photo_einzel,
                      self.additional_photographers_entries_einzel)
                  ).grid(row=1, column=0, columnspan=2, sticky="w", pady=3)

        canvas_f = tk.Frame(frame_photographers, bg=self.bg_color)
        canvas_f.grid(row=2, column=0, columnspan=4, sticky="ew")
        self.canvas_photo_einzel = tk.Canvas(
            canvas_f, height=80, bg=self.bg_color, highlightthickness=0)
        s_bar = tk.Scrollbar(canvas_f, orient="vertical",
                             command=self.canvas_photo_einzel.yview)
        self.scroll_frame_photo_einzel = tk.Frame(self.canvas_photo_einzel, bg=self.bg_color)
        self.scroll_frame_photo_einzel.bind(
            "<Configure>",
            lambda e: self.canvas_photo_einzel.configure(
                scrollregion=self.canvas_photo_einzel.bbox("all")))
        self.canvas_photo_einzel.create_window(
            (0, 0), window=self.scroll_frame_photo_einzel, anchor="nw")
        self.canvas_photo_einzel.configure(yscrollcommand=s_bar.set)
        self.canvas_photo_einzel.pack(side="left", fill="both", expand=True)
        s_bar.pack(side="right", fill="y")
        self.add_photo_row(self.scroll_frame_photo_einzel,
                           self.canvas_photo_einzel,
                           self.additional_photographers_entries_einzel)

        # 4. Aktionen
        self.create_action_frame(scrollable_frame)

    # =========================================================================
    # REITER 2: BATCH-MODUS
    # =========================================================================
    def create_batch_tab(self):
        # ── Bottom: global actions + UNDO (centred, not full-width) ──────────
        bottom_container = tk.Frame(self.tab_batch, bg=self.bg_color)
        bottom_container.pack(side="bottom", fill="x", padx=6, pady=4)
        centered_bottom = tk.Frame(bottom_container, bg=self.bg_color)
        centered_bottom.pack()  # no fill → centred

        # Global action buttons (run chosen action for ALL Maßnahmen at once)
        frame_global = self._create_frame(centered_bottom, " Alle Maßnahmen ausführen ")
        frame_global.pack(pady=(0, 4))
        inner_g = tk.Frame(frame_global, bg=self.bg_color)
        inner_g.pack(pady=2)
        _GW = 30  # character width for global buttons (slightly wider than per-block)

        btn_g1 = tk.Button(inner_g, text="1. Umbenennen+Abgabe+Liste", width=_GW,
                           bg="#00cc44", fg="#000000", font=('Helvetica', 9, 'bold'),
                           pady=2, command=lambda: self.action_full_process(batch=True))
        btn_g1._custom_color = True
        btn_g1.grid(row=0, column=0, padx=3, pady=1)

        tk.Button(inner_g, text="2. Nur umbenennen", width=_GW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 9), pady=2,
                  command=lambda: self.action_rename_only(batch=True)
                  ).grid(row=0, column=1, padx=3, pady=1)

        tk.Button(inner_g, text="3. Aufspüren + Liste", width=_GW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 9), pady=2,
                  command=lambda: self.action_gather_and_csv(batch=True)
                  ).grid(row=0, column=2, padx=3, pady=1)

        tk.Button(inner_g, text="4. Nur Fotoliste", width=_GW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 9), pady=2,
                  command=lambda: self.action_csv_only(batch=True)
                  ).grid(row=1, column=0, padx=3, pady=1)

        btn_g5 = tk.Button(inner_g, text="5. Fotoliste aktualisieren", width=_GW,
                           bg="#4287f5", fg="#ffffff", font=('Helvetica', 9, 'bold'),
                           pady=2, command=lambda: self.action_update_csv(batch=True))
        btn_g5._custom_color = True
        btn_g5.grid(row=1, column=1, padx=3, pady=1)

        # UNDO
        frame_undo_border = tk.Frame(centered_bottom, bg="#cc0000", padx=2, pady=2)
        frame_undo_border._custom_color = True
        frame_undo_border.pack(pady=(2, 0))
        btn_undo = tk.Button(
            frame_undo_border,
            text="↩ Letzte Aktion rückgängig machen (UNDO)",
            bg="#000000", fg="#ff4444", font=('Helvetica', 9, 'bold'),
            relief="flat", pady=2, width=42, command=self.undo_last_action)
        btn_undo._custom_color = True
        btn_undo.pack()

        # Top fixed sections
        frame_top = self._create_frame(self.tab_batch, " 1. Master-Ordner wählen ")
        frame_top.pack(side="top", fill="x", padx=6, pady=3)
        frame_top.columnconfigure(1, weight=1)
        tk.Label(frame_top, text="Übergeordneter Ordner:",
                 bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, sticky="w")
        self.ent_batch_master = tk.Entry(
            frame_top, width=38, bg=self.entry_bg, fg=self.fg_color,
            insertbackground=self.fg_color)
        self.ent_batch_master.grid(row=0, column=1, padx=4, sticky="ew")
        tk.Button(frame_top, text="Ordner scannen…",
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  command=self.browse_batch_master).grid(row=0, column=2, padx=4)

        frame_options = self._create_frame(self.tab_batch, " 2. Globale Batch-Optionen ")
        frame_options.pack(side="top", fill="x", padx=6, pady=3)
        tk.Label(frame_options, text="Stellen-Filter (kommagetrennt):",
                 bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, sticky="w")
        self.ent_filter_stellen_batch = tk.Entry(
            frame_options, width=24, bg=self.entry_bg, fg=self.fg_color,
            insertbackground=self.fg_color)
        self.ent_filter_stellen_batch.grid(row=0, column=1, padx=4, sticky="w")
        tk.Checkbutton(frame_options, text="EXIF-Datum tolerieren",
                       variable=self.var_ignore_exif_batch, bg=self.bg_color, fg=self.fg_color,
                       selectcolor=self.entry_bg, activebackground=self.bg_color,
                       activeforeground=self.fg_color).grid(row=0, column=2, padx=4, sticky="w")

        # Measures area fills remaining space
        frame_measures = self._create_frame(self.tab_batch, " 3. Gefundene Maßnahmen ")
        frame_measures.pack(side="top", fill="both", expand=True, padx=6, pady=3)

        self.canvas_batch_main = tk.Canvas(frame_measures, bg=self.bg_color, highlightthickness=0)
        scroll_main = tk.Scrollbar(frame_measures, orient="vertical",
                                   command=self.canvas_batch_main.yview)
        self.scroll_frame_batch = tk.Frame(self.canvas_batch_main, bg=self.bg_color)
        self.scroll_frame_batch.bind(
            "<Configure>",
            lambda e: self.canvas_batch_main.configure(
                scrollregion=self.canvas_batch_main.bbox("all")))
        win_id_b = self.canvas_batch_main.create_window(
            (0, 0), window=self.scroll_frame_batch, anchor="nw")
        self.canvas_batch_main.bind(
            "<Configure>",
            lambda e: self.canvas_batch_main.itemconfig(win_id_b, width=e.width))
        self.canvas_batch_main.configure(yscrollcommand=scroll_main.set)
        self.canvas_batch_main.pack(side="left", fill="both", expand=True)
        scroll_main.pack(side="right", fill="y")

    # =========================================================================
    # REITER 3: PROTOKOLL
    # =========================================================================
    def create_protokoll_tab(self):
        self.txt_log = scrolledtext.ScrolledText(
            self.tab_protokoll, bg=self.entry_bg, fg=self.log_fg,
            font=('Consolas', 9), insertbackground=self.fg_color)
        self.txt_log._custom_color = True
        self.txt_log.pack(fill="both", expand=True, padx=6, pady=6)

    # --- SHARED UI ---
    def create_action_frame(self, parent):
        frame_actions = self._create_frame(parent, " Aktionen ")
        frame_actions.pack(fill="x", padx=6, pady=4)
        frame_actions.columnconfigure(0, weight=1)
        frame_actions.columnconfigure(1, weight=1)

        # Row 0: Green main button (full width)
        btn_full = tk.Button(
            frame_actions,
            text="1. Umbenennen, Abgabeordner & Fotoliste erstellen",
            bg="#00cc44", fg="#000000", font=('Helvetica', 9, 'bold'),
            relief="raised", pady=3, command=lambda: self.action_full_process(batch=False))
        btn_full._custom_color = True
        btn_full.grid(row=0, column=0, columnspan=2, padx=2, pady=(2, 3), sticky="ew")

        # Rows 1-2: 2-column layout
        tk.Button(
            frame_actions, text="2. Nur umbenennen",
            bg=self.btn_bg_highlight, fg=self.fg_color, pady=2,
            command=lambda: self.action_rename_only(batch=False)
        ).grid(row=1, column=0, padx=2, pady=1, sticky="ew")

        tk.Button(
            frame_actions, text="3. Fotos aufspüren, verschieben & Liste",
            bg=self.btn_bg_highlight, fg=self.fg_color, pady=2,
            command=lambda: self.action_gather_and_csv(batch=False)
        ).grid(row=1, column=1, padx=2, pady=1, sticky="ew")

        tk.Button(
            frame_actions, text="4. Nur Fotoliste erstellen",
            bg=self.btn_bg_highlight, fg=self.fg_color, pady=2,
            command=lambda: self.action_csv_only(batch=False)
        ).grid(row=2, column=0, padx=2, pady=1, sticky="ew")

        btn_update = tk.Button(
            frame_actions, text="5. Fotoliste aktualisieren",
            bg="#4287f5", fg="#ffffff", font=('Helvetica', 9, 'bold'),
            pady=2, command=lambda: self.action_update_csv(batch=False))
        btn_update._custom_color = True
        btn_update.grid(row=2, column=1, padx=2, pady=1, sticky="ew")

        # Row 3: UNDO (full width, red border)
        frame_undo_border = tk.Frame(frame_actions, bg="#cc0000", padx=2, pady=2)
        frame_undo_border._custom_color = True
        frame_undo_border.grid(row=3, column=0, columnspan=2, padx=2, pady=(4, 1), sticky="ew")
        btn_undo = tk.Button(
            frame_undo_border,
            text="↩ Letzte Aktion rückgängig machen (UNDO)",
            bg="#000000", fg="#ff4444", font=('Helvetica', 9, 'bold'),
            relief="flat", pady=2, command=self.undo_last_action)
        btn_undo._custom_color = True
        btn_undo.pack(fill="both", expand=True)

    def add_photo_row(self, frame, canvas, list_ref):
        if len(list_ref) >= 40:
            return
        row_idx = len(list_ref)
        tk.Label(frame, text=f"Fotograf*in {row_idx + 1}:",
                 bg=self.bg_color, fg=self.fg_color).grid(
            row=row_idx, column=0, sticky="nw", pady=1, padx=2)
        ent_name = tk.Entry(frame, width=14, bg=self.entry_bg, fg=self.fg_color,
                            insertbackground=self.fg_color)
        ent_name.grid(row=row_idx, column=1, sticky="nw", padx=4, pady=1)
        tk.Label(frame, text="Fotos:", bg=self.bg_color, fg=self.fg_color).grid(
            row=row_idx, column=2, sticky="nw", pady=1, padx=2)
        ent_matches = tk.Text(frame, height=2, width=28, wrap="word",
                              font=('Helvetica', 9), bg=self.entry_bg, fg=self.fg_color,
                              insertbackground=self.fg_color)
        ent_matches.grid(row=row_idx, column=3, sticky="ew", padx=4, pady=1)
        list_ref.append((ent_name, ent_matches))
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.yview_moveto(1.0)

    # =========================================================================
    # THEME
    # =========================================================================
    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.set_theme_colors()
        self.apply_ttk_styles()
        if self.is_dark_mode:
            self.btn_theme_toggle.config(text="☀ Light Mode", bg="#333333", fg="#FFFFFF")
            self.btn_license.config(bg=self.bg_color, fg="#aaaaaa",
                                    activebackground=self.bg_color, activeforeground="#ffffff")
        else:
            self.btn_theme_toggle.config(text="☾ Dark Mode", bg="#DDDDDD", fg="#000000")
            self.btn_license.config(bg=self.bg_color, fg="#555555",
                                    activebackground=self.bg_color, activeforeground="#000000")
        self.root.configure(bg=self.bg_color)
        self.txt_log.config(bg=self.entry_bg, fg=self.log_fg, insertbackground=self.fg_color)
        self.apply_theme_recursive(self.root)

    def apply_theme_recursive(self, parent):
        for widget in parent.winfo_children():
            if not getattr(widget, "_custom_color", False):
                try:
                    if isinstance(widget, (tk.LabelFrame, tk.Label, tk.Canvas, tk.Frame)):
                        widget.configure(bg=self.bg_color)
                        if isinstance(widget, (tk.LabelFrame, tk.Label)):
                            widget.configure(fg=self.fg_color)
                        if isinstance(widget, tk.LabelFrame):
                            widget.configure(highlightbackground=self.fg_color)
                    elif isinstance(widget, tk.Checkbutton):
                        widget.configure(bg=self.bg_color, fg=self.fg_color,
                                         selectcolor=self.entry_bg,
                                         activebackground=self.bg_color,
                                         activeforeground=self.fg_color)
                    elif isinstance(widget, (tk.Entry, tk.Text)):
                        widget.configure(bg=self.entry_bg, fg=self.fg_color,
                                         insertbackground=self.fg_color)
                    elif isinstance(widget, tk.Button):
                        widget.configure(bg=self.btn_bg_highlight, fg=self.fg_color)
                except Exception:
                    pass
            self.apply_theme_recursive(widget)

    # =========================================================================
    # DATEN EXTRAKTION
    # =========================================================================
    def build_photo_mapping(self, main_photo_str, additional_entries_list):
        overrides = {}
        for ent_name, ent_matches in additional_entries_list:
            name = ent_name.get().strip()
            matches_raw = ent_matches.get("1.0", tk.END).strip()
            if name and matches_raw:
                for chunk in matches_raw.split(','):
                    nums = re.findall(r'[0-9]+', chunk)
                    if len(nums) == 2:
                        overrides[(int(nums[0]), int(nums[1]))] = name
        return overrides

    def get_einzel_data(self):
        # Pfad vereinheitlichen: ein abschließender Schrägstrich oder per
        # "Als Pfad kopieren" eingefügte Anführungszeichen würden sonst Abgabe-
        # ordner und Fotoliste an einem anderen Ort suchen bzw. anlegen.
        base_dir = self.ent_dir_einzel.get().strip().strip('"').strip()
        if base_dir:
            base_dir = os.path.normpath(base_dir)
        return [{
            'raw_act': self.ent_activity_einzel.get(),
            'base_dir': base_dir,
            'filter_raw': self.ent_filter_stellen_einzel.get(),
            'ignore_old_exif': self.var_ignore_exif_einzel.get(),
            'main_photo': self.ent_main_photo_einzel.get().strip(),
            'photo_mapping': self.build_photo_mapping(
                self.ent_main_photo_einzel.get(),
                self.additional_photographers_entries_einzel)
        }]

    @staticmethod
    def _block_extra_dirs(block):
        """Die angehakten zusammengeführten Ordner eines Batch-Blocks."""
        if 'extra_vars' in block:
            return [xd for xd, var in block['extra_vars'] if var.get()]
        return list(block.get('extra_dirs', []))

    @staticmethod
    def _block_skipped_dirs(block):
        """Die abgewählten zusammengeführten Ordner eines Batch-Blocks."""
        return [xd for xd, var in block.get('extra_vars', []) if not var.get()]

    def _skipped_notes(self, data_list):
        """Hinweis auf abgewählte Ordner für Protokoll und Abschlussmeldung –
        damit 'aktuell' nicht verschweigt, dass Fotos liegen geblieben sind."""
        notes = []
        for d in data_list:
            for xd in d.get('skipped_dirs', []):
                n = len(self.gather_all_photos(xd)) if os.path.isdir(xd) else 0
                notes.append(f"{(d.get('raw_act') or '').strip()}: Ordner "
                             f"'{os.path.basename(xd)}' nicht einbezogen (abgewählt, "
                             f"{self._n(n, 'Foto', 'Fotos')}).")
        for n in notes:
            self.log(n)
        return notes

    def get_batch_data(self):
        data_list = []
        for block in self.batch_blocks:
            data_list.append({
                'raw_act': block['ent_activity'].get(),
                'base_dir': block['base_dir'],
                'extra_dirs': self._block_extra_dirs(block),
                'skipped_dirs': self._block_skipped_dirs(block),
                'filter_raw': self.ent_filter_stellen_batch.get(),
                'ignore_old_exif': self.var_ignore_exif_batch.get(),
                'main_photo': block['ent_main_photo'].get().strip(),
                'photo_mapping': self.build_photo_mapping(
                    block['ent_main_photo'].get(),
                    block['additional_photos'])
            })
        return data_list

    def browse_dir_einzel(self):
        d = filedialog.askdirectory()
        if d:
            self.ent_dir_einzel.delete(0, tk.END)
            self.ent_dir_einzel.insert(0, d)
            act = self.auto_fill_activity(d)
            if act:
                self.ent_activity_einzel.delete(0, tk.END)
                self.ent_activity_einzel.insert(0, act)

    def browse_batch_master(self):
        d = filedialog.askdirectory()
        if d:
            self.ent_batch_master.delete(0, tk.END)
            self.ent_batch_master.insert(0, d)
            self.load_batch_folders(d)

    def load_batch_folders(self, master_dir):
        for widget in self.scroll_frame_batch.winfo_children():
            widget.destroy()
        self.batch_blocks.clear()
        found_count = 0
        try:
            basename = os.path.basename(os.path.normpath(master_dir))
            prefix, year, proj = self.search_activity_in_string(basename)

            # Decide: is master_dir the target itself, or just a container for subdirs?
            #
            # Rule: if master_dir's name contains an activity AND all activity-named
            # subdirs share that same activity → master_dir IS the single target (one block).
            #
            # Exception: if at least one subdir carries a DIFFERENT activity (e.g.
            # folder "OV_2026_0005" contains "OV_2026_0006_Abgabe") → master_dir is
            # just a container; scan its children instead.
            is_container = True  # default: scan subdirs
            if prefix:
                master_key = self._normalize_activity(f"{prefix}{year}{proj}")
                sub_acts = set()
                try:
                    for item in os.listdir(master_dir):
                        if not os.path.isdir(os.path.join(master_dir, item)):
                            continue
                        p2, y2, j2 = self.search_activity_in_string(item)
                        if p2:
                            sub_acts.add(self._normalize_activity(f"{p2}{y2}{j2}"))
                except Exception:
                    pass
                # All subdir-activities match (or no activity-named subdirs) → single block
                if not sub_acts or all(a == master_key for a in sub_acts):
                    is_container = False

            if not is_container:
                self.create_batch_block(master_dir, f"{prefix} {year}/{int(proj):04d}")
                found_count = 1
            else:
                # Collect all qualifying subdirs and group by normalized activity key.
                # Folders sharing the same activity (e.g. OV22_1057_Abgabe and
                # OV_2022_1057_BN-Castell_Spielplatz-Sickergruben) become ONE block.
                groups = {}  # key: norm_str → {'act': suggested_str, 'dirs': [...]}
                for item in sorted(os.listdir(master_dir)):
                    item_path = os.path.join(master_dir, item)
                    if not os.path.isdir(item_path):
                        continue
                    if item.lower().endswith('_fotos'):
                        src_name = item[:item.lower().rfind('_fotos')]
                        if src_name and os.path.isdir(os.path.join(master_dir, src_name)):
                            continue
                    p2, y2, j2 = self.search_activity_in_string(item)
                    if p2:
                        key = self._normalize_activity(f"{p2}{y2}{j2}")
                        if key not in groups:
                            groups[key] = {
                                'act': f"{p2} {y2}/{int(j2):04d}",
                                'dirs': []
                            }
                        groups[key]['dirs'].append(item_path)

                for g in groups.values():
                    dirs = g['dirs']
                    # Primary folder: prefer one ending in _Abgabe, else first
                    # alphabetically – but never a copy/backup if there is
                    # another candidate ('OV_..._alt' before 'OV_..._neu').
                    # Ein '<Aktivität>_Fotos'-Ordner (Ausgabe eines früheren
                    # Laufs) ist Ziel, nie Hauptordner – sonst wechselt der
                    # Hauptordner beim erneuten Scannen.
                    cands = [d for d in dirs if not self._looks_like_copy_dir(d, dirs)] or dirs
                    cands = [d for d in cands
                             if not os.path.basename(d).lower().endswith('_fotos')] or cands
                    primary = next(
                        (d for d in cands
                         if os.path.basename(d).lower().endswith('_abgabe')),
                        cands[0])
                    extra = [d for d in dirs if d != primary]
                    self.create_batch_block(primary, g['act'], extra_dirs=extra)
                    found_count += 1
        except Exception as e:
            self.log(f"Fehler beim Scannen: {e}")
        self.canvas_batch_main.configure(scrollregion=self.canvas_batch_main.bbox("all"))
        self.log(f"Batch-Scan: {found_count} Maßnahme(n) gefunden.")

    def create_batch_block(self, dir_path, suggested_act, extra_dirs=None):
        extra_dirs = list(extra_dirs or [])

        # LabelFrame title: primary folder name + count of merged extras
        base_label = os.path.basename(dir_path)
        if extra_dirs:
            n = len(extra_dirs)
            base_label += (f" (+{n} weiterer Ordner)" if n == 1
                           else f" (+{n} weitere Ordner)")
        b_frame = self._create_frame(self.scroll_frame_batch, base_label)
        b_frame.pack(fill="x", pady=3, padx=3)

        # Block dict — populated below, then appended
        block = {
            'base_dir': dir_path,
            'extra_dirs': extra_dirs,
            'ent_activity': None,
            'ent_main_photo': None,
            'additional_photos': [],
        }

        def remove_block():
            if block in self.batch_blocks:
                self.batch_blocks.remove(block)
            b_frame.destroy()
            self.canvas_batch_main.configure(
                scrollregion=self.canvas_batch_main.bbox("all"))

        def _block_data():
            return {
                'raw_act': block['ent_activity'].get(),
                'base_dir': dir_path,
                'extra_dirs': self._block_extra_dirs(block),
                'skipped_dirs': self._block_skipped_dirs(block),
                'filter_raw': self.ent_filter_stellen_batch.get(),
                'ignore_old_exif': self.var_ignore_exif_batch.get(),
                'main_photo': block['ent_main_photo'].get().strip(),
                'photo_mapping': self.build_photo_mapping(
                    block['ent_main_photo'].get(), block['additional_photos'])
            }

        # ── Row 1: activity / photographer / buttons ──────────────────────────
        top_inner = tk.Frame(b_frame, bg=self.bg_color)
        top_inner.pack(fill="x")
        top_inner.columnconfigure(3, weight=1)

        tk.Label(top_inner, text="Aktivität:",
                 bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, sticky="w")
        ent_act = tk.Entry(top_inner, width=18, bg=self.entry_bg, fg=self.fg_color,
                           insertbackground=self.fg_color)
        ent_act.insert(0, suggested_act)
        ent_act.grid(row=0, column=1, padx=4, sticky="w")

        tk.Label(top_inner, text="Hauptfotograf:",
                 bg=self.bg_color, fg=self.fg_color).grid(row=0, column=2, sticky="w")
        ent_main = tk.Entry(top_inner, width=14, bg=self.entry_bg, fg=self.fg_color,
                            insertbackground=self.fg_color)
        ent_main.grid(row=0, column=3, padx=4, sticky="ew")

        entries_list = []
        tk.Button(top_inner, text="+ Fotograf*in",
                  bg=self.btn_bg_highlight, fg=self.fg_color, pady=1,
                  command=lambda: self.add_photo_row(
                      frame_photo, canvas_photo, entries_list)
                  ).grid(row=0, column=4, padx=4)

        btn_del = tk.Button(top_inner, text="✕ Entfernen",
                            bg="#880000", fg="#ffffff", pady=1, font=('Helvetica', 8),
                            command=remove_block)
        btn_del._custom_color = True
        btn_del.grid(row=0, column=5, padx=(6, 2), sticky="e")

        # ── Row 1b: zusammengeführte weitere Ordner – sichtbar und abwählbar.
        # Ordner, die nach Kopie/Sicherung aussehen ('… - Kopie', '_alt'),
        # sind vorab abgewählt: ihre Fotos würden sonst als _A-Dubletten
        # umbenannt und doppelt aufgespürt.
        block['extra_vars'] = []
        p_, y_, n_ = self.parse_activity(suggested_act)
        t_key = (self._path_key(self.get_output_folder_path(dir_path, f"{p_}_{y_}_{n_}"))
                 if p_ else None)
        if extra_dirs:
            x_frame = tk.Frame(b_frame, bg=self.bg_color)
            x_frame.pack(fill="x")
            tk.Label(x_frame, text="Weitere Ordner dieser Maßnahme einbeziehen:",
                     bg=self.bg_color, fg=self.fg_color).pack(anchor="w")
            for xd in extra_dirs:
                if self._path_key(xd) == t_key:
                    # Das ist der Zielordner der fertigen Fotos – immer dabei.
                    tk.Label(x_frame, text=f"   {os.path.basename(xd)}   (Zielordner "
                                           "der fertigen Fotos – immer einbezogen)",
                             bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=(14, 0))
                    block['extra_vars'].append((xd, tk.BooleanVar(value=True)))
                    continue
                looks_copy = self._looks_like_copy_dir(xd, [dir_path] + extra_dirs)
                var = tk.BooleanVar(value=not looks_copy)
                tk.Checkbutton(
                    x_frame, variable=var,
                    text=os.path.basename(xd) + (
                        "   ⚠ sieht nach Kopie/Sicherung aus – vorsorglich abgewählt"
                        if looks_copy else ""),
                    bg=self.bg_color, fg=self.fg_color, selectcolor=self.entry_bg,
                    activebackground=self.bg_color, activeforeground=self.fg_color
                ).pack(anchor="w", padx=(14, 0))
                block['extra_vars'].append((xd, var))

        # ── Row 2: optional photographer canvas ───────────────────────────────
        c_frame = tk.Frame(b_frame, bg=self.bg_color)
        c_frame.pack(fill="x", pady=2)
        canvas_photo = tk.Canvas(c_frame, height=50, bg=self.bg_color, highlightthickness=0)
        s_bar = tk.Scrollbar(c_frame, orient="vertical", command=canvas_photo.yview)
        frame_photo = tk.Frame(canvas_photo, bg=self.bg_color)
        frame_photo.bind("<Configure>",
                         lambda e: canvas_photo.configure(
                             scrollregion=canvas_photo.bbox("all")))
        canvas_photo.create_window((0, 0), window=frame_photo, anchor="nw")
        canvas_photo.configure(yscrollcommand=s_bar.set)
        canvas_photo.pack(side="left", fill="x", expand=True)
        s_bar.pack(side="right", fill="y")

        # ── Row 3: per-block action buttons (uniform width, not stretched) ──────
        _BW = 26  # all per-block buttons the same character width
        btn_frame = tk.Frame(b_frame, bg=self.bg_color)
        btn_frame.pack(pady=(2, 1))  # centred, no fill='x'

        btn1 = tk.Button(btn_frame,
                         text="1. Umbenennen+Abgabe+Liste", width=_BW,
                         bg="#00cc44", fg="#000000", font=('Helvetica', 8, 'bold'), pady=1,
                         command=lambda: self.action_full_process([_block_data()], batch=True))
        btn1._custom_color = True
        btn1.grid(row=0, column=0, padx=2, pady=1)

        tk.Button(btn_frame, text="2. Nur umbenennen", width=_BW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 8), pady=1,
                  command=lambda: self.action_rename_only([_block_data()], batch=True)
                  ).grid(row=0, column=1, padx=2, pady=1)

        tk.Button(btn_frame, text="3. Aufspüren + Liste", width=_BW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 8), pady=1,
                  command=lambda: self.action_gather_and_csv([_block_data()], batch=True)
                  ).grid(row=0, column=2, padx=2, pady=1)

        tk.Button(btn_frame, text="4. Nur Fotoliste", width=_BW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 8), pady=1,
                  command=lambda: self.action_csv_only([_block_data()], batch=True)
                  ).grid(row=1, column=0, padx=2, pady=1)

        btn5 = tk.Button(btn_frame, text="5. Fotoliste aktualisieren", width=_BW,
                         bg="#4287f5", fg="#ffffff", font=('Helvetica', 8, 'bold'), pady=1,
                         command=lambda: self.action_update_csv([_block_data()], batch=True))
        btn5._custom_color = True
        btn5.grid(row=1, column=1, padx=2, pady=1)

        # ── Finalize ──────────────────────────────────────────────────────────
        block['ent_activity'] = ent_act
        block['ent_main_photo'] = ent_main
        block['additional_photos'] = entries_list
        self.batch_blocks.append(block)
        self.apply_theme_recursive(b_frame)

    # =========================================================================
    # CORE ROUTING
    # =========================================================================
    def _resolve_data(self, data_list, batch):
        """Daten und Modus einer Aktion. Die Knöpfe geben den Modus ausdrücklich
        mit; nur ohne Angabe wird der sichtbare Reiter herangezogen. Jede
        Aktion beginnt einen eigenen UNDO-Schritt."""
        if batch is None:
            batch = self.notebook.index(self.notebook.select()) == 1
        if data_list is None:
            data_list = self.get_batch_data() if batch else self.get_einzel_data()
        self._begin_undo_group()
        return data_list, batch

    @staticmethod
    def _notes_text(notes, limit=15):
        """Ergebniszeilen (Fotolisten, abgewählte Ordner) für die Abschlussmeldung."""
        if not notes:
            return ""
        text = "\n\nErgebnis:\n- " + "\n- ".join(notes[:limit])
        if len(notes) > limit:
            text += f"\n… und {len(notes) - limit} weitere (siehe Protokoll)"
        return text

    def action_full_process(self, data_list=None, batch=None):
        data_list, batch = self._resolve_data(data_list, batch)
        if not data_list:
            return messagebox.showwarning("Achtung", "Keine Daten vorhanden.")
        t_r, t_m = 0, 0
        for d in data_list:
            res = self._core_process_photos("rename_and_move", **d)
            if res:
                t_r += res[0]
                t_m += res[1]
        notes = self._skipped_notes(data_list) + self._csv_save_flow(data_list, batch)
        messagebox.showinfo("Aktion 1 beendet",
                            f"Vorgang für {len(data_list)} Ordner abgeschlossen.\n\n"
                            f"Neu umbenannt: {t_r}\nBereits fertige verschoben: {t_m}"
                            + self._notes_text(notes))

    def action_rename_only(self, data_list=None, batch=None):
        data_list, batch = self._resolve_data(data_list, batch)
        if not data_list:
            return
        t_r, notes = 0, self._skipped_notes(data_list)
        for d in data_list:
            res = self._core_process_photos("rename_only", **d)
            if res is None:
                notes.append(f"{(d.get('raw_act') or '').strip() or '?'}: "
                             "Aktivität oder Ordner ungültig – übersprungen.")
            else:
                t_r += res[0]
        messagebox.showinfo("Aktion 2 beendet",
                            f"Nur Umbenennen abgeschlossen!\n\nNeu umbenannt: {t_r} Fotos."
                            + self._notes_text(notes))

    def action_gather_and_csv(self, data_list=None, batch=None):
        data_list, batch = self._resolve_data(data_list, batch)
        if not data_list:
            return
        t_m = 0
        for d in data_list:
            m = self._core_move_to_existing(**d)
            if m is not None:
                t_m += m
        notes = self._skipped_notes(data_list) + self._csv_save_flow(data_list, batch)
        messagebox.showinfo("Aktion 3 beendet",
                            f"Aufspüren abgeschlossen!\n\n"
                            f"Fotos in Abgabeordner verschoben: {t_m}"
                            + self._notes_text(notes))

    def action_csv_only(self, data_list=None, batch=None):
        data_list, batch = self._resolve_data(data_list, batch)
        if not data_list:
            return messagebox.showwarning("Achtung", "Keine Daten vorhanden.")
        notes = self._skipped_notes(data_list) + self._csv_save_flow(data_list, batch)
        messagebox.showinfo("Aktion 4 beendet",
                            "Fotoliste erstellen abgeschlossen." + self._notes_text(notes))

    def action_update_csv(self, data_list=None, batch=None):
        data_list, batch = self._resolve_data(data_list, batch)
        if not data_list:
            return messagebox.showwarning("Achtung", "Keine Daten vorhanden.")
        if batch:
            # Batch: vorhandene Listen werden je Maßnahme gesucht; gespeichert
            # wird erst nach Bestätigung im Speichern-Dialog.
            notes = (self._skipped_notes(data_list)
                     + self._csv_save_flow(data_list, True, update=True))
            messagebox.showinfo("Fotolisten aktualisieren", "Batch-Aktualisierung "
                                "abgeschlossen." + self._notes_text(notes))
            return
        # Einzel: die zu aktualisierende Liste auswählen (Vorschlag: die
        # automatisch gefundene), danach Speicherort im Speichern-Dialog.
        d = data_list[0]
        p, y, pr = self.parse_activity(d.get('raw_act', ''))
        if not p or not os.path.isdir(d.get('base_dir', '')):
            return messagebox.showwarning(
                "Achtung", "Bitte zuerst eine gültige Aktivität und einen Quell-Ordner angeben.")
        # Vorschlag: in dieser Sitzung selbst gewählte Liste, sonst die gefundene
        pinned = self._chosen_targets.get(
            (self._activity_key(f"{p} {y}/{int(pr)}"), self._path_key(d['base_dir'])))
        guess = (pinned if pinned and os.path.isfile(pinned)
                 else self._find_existing_csv(d['base_dir'], f"{p}_{y}_{pr}",
                                              extra_dirs=d.get('extra_dirs', [])))
        fp = filedialog.askopenfilename(
            title="Vorhandene Fotoliste auswählen",
            initialdir=os.path.dirname(guess) if guess else d['base_dir'],
            initialfile=os.path.basename(guess) if guess else "",
            filetypes=[("CSV Dateien", "*.csv")])
        if not fp:
            return
        fp = os.path.normpath(fp)
        info = self._inspect_csv(fp)
        if not info or not info['compatible']:
            return messagebox.showerror(
                "Keine Fotoliste",
                f"'{os.path.basename(fp)}' lässt sich nicht als Fotoliste lesen\n"
                "(die Spalten StellenNr und PosNr fehlen).")
        notes = self._csv_save_flow([d], False, list_path=fp, update=True)
        messagebox.showinfo("Fotoliste aktualisieren",
                            "Aktualisieren abgeschlossen." + self._notes_text(notes))

    # =========================================================================
    # CORE LOGIK
    # =========================================================================
    def search_activity_in_string(self, text):
        match = re.search(
            r"^([A-Za-z]{2})[\s_/-]?([0-9]{4}|[0-9]{2})[\s_/-]?([0-9]{1,4})(?![0-9])",
            text, re.IGNORECASE)
        if match:
            y_r = match.group(2)
            y = 2000 + int(y_r) if len(y_r) == 2 else int(y_r)
            return match.group(1).upper(), y, f"{int(match.group(3)):04d}"
        return None, None, None

    def parse_activity(self, raw_input):
        cleaned = raw_input.strip()
        match = re.match(
            r"^([A-Za-z]{2})[\s_/-]?([0-9]{4}|[0-9]{2})[\s_/-]?([0-9]{1,4})$", cleaned)
        if not match:
            self.log(f"Fehler: Aktivitätseingabe '{raw_input}' entspricht nicht dem Muster.")
            return None, None, None
        y_r = match.group(2)
        y = 2000 + int(y_r) if len(y_r) == 2 else int(y_r)
        return match.group(1).upper(), y, f"{int(match.group(3)):04d}"

    def auto_fill_activity(self, directory):
        found = set()
        try:
            for file in os.listdir(directory):
                if file.lower().endswith(('.jpg', '.jpeg')):
                    match = re.match(
                        r"^([A-Za-z]{2})_([0-9]{4})_([0-9]{4})_[0-9]{4}_[0-9]{3}(_[A-Z]|[0-9]+)?\.jpe?g$",
                        file, re.IGNORECASE)
                    if match:
                        found.add(f"{match.group(1).upper()} "
                                  f"{match.group(2)}/{int(match.group(3)):04d}")
        except:
            pass
        if len(found) > 1:
            self.log("Auto-Erkennung abgebrochen: Verschiedene Aktivitäten gefunden.")
            return None
        if len(found) == 1:
            return found.pop()

        cands = [os.path.basename(directory)]
        p_dir = os.path.dirname(directory)
        if p_dir:
            cands.append(os.path.basename(p_dir))
            try:
                cands.extend(i for i in os.listdir(p_dir)
                             if os.path.isdir(os.path.join(p_dir, i)))
            except:
                pass

        pattern = r"(?:^|[^a-zA-Z])([A-Za-z]{2})[\s_/-]?([0-9]{4}|[0-9]{2})[\s_/-]?([0-9]{1,4})(?![0-9])"
        for c in cands:
            p, y, pr = self.search_activity_in_string(c)
            if p:
                return f"{p} {y}/{int(pr):04d}"
            match = re.search(pattern, c)
            if match:
                prefix = match.group(1).upper()
                year_raw = match.group(2)
                proj_num = int(match.group(3))
                y = 2000 + int(year_raw) if len(year_raw) == 2 else int(year_raw)
                return f"{prefix} {y}/{proj_num:04d}"
        return None

    def parse_photo_name(self, filename):
        name, ext = os.path.splitext(filename)
        if ext.lower() not in ['.jpg', '.jpeg']:
            return None
        name = re.sub(r'^[\s_\-]+|[\s_\-]+$', '', name.strip())
        parts = re.split(r'[\s_\-]+', name)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            if len(parts[0]) <= 4 and len(parts[1]) <= 3:
                return f"{int(parts[0]):04d}", f"{int(parts[1]):03d}"
        return None

    def get_exif_date_pure(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                data = f.read(65536)
                m = re.search(
                    br'\x90\x03\x00\x02.{0,20}([0-9]{4}:[0-9]{2}:[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})',
                    data, re.DOTALL)
                if not m:
                    m = re.search(
                        br'([0-9]{4}):([0-9]{2}):([0-9]{2}) ([0-9]{2}):([0-9]{2}):([0-9]{2})',
                        data)
                if m:
                    d_str = (m.group(1).decode('ascii', errors='ignore')
                             if len(m.groups()) == 1
                             else m.group(0).decode('ascii', errors='ignore'))
                    return datetime.strptime(d_str[:10], "%Y:%m:%d")
        except:
            pass
        return None

    def get_output_folder_path(self, base_dir, activity_str, exclude=None):
        # If a matching _Fotos subdirectory already exists INSIDE base_dir, use that.
        # This handles structures like OV_2026_1014_Abgabe/OV_2026_1014_Fotos/.
        inner = os.path.join(base_dir, f"{activity_str}_Fotos")
        if os.path.isdir(inner):
            return inner
        parent = os.path.dirname(base_dir)
        sibling = os.path.join(parent, f"{activity_str}_Fotos")
        if (not os.path.isdir(sibling)
                and not os.path.basename(base_dir).lower().endswith('_abgabe')):
            # Liegt daneben schon GENAU EIN Abgabeordner derselben Maßnahme mit
            # _Fotos (z.B. erst Batch, dann Einzel auf dem Rohfoto-Ordner), wird
            # der weiterverwendet statt ein zweiter angelegt. Sein Name muss mit
            # der Aktivität beginnen und darf keine Kopie/Sicherung und nicht im
            # Batch abgewählt sein; bei mehreren Kandidaten bleibt es beim
            # Ordner neben der Quelle. Ist die Quelle selbst ein Abgabeordner,
            # bekommt sie ihren eigenen _Fotos-Ordner.
            act_key = self._activity_key(activity_str)
            excluded = {self._path_key(x) for x in (exclude or [])}
            found = []
            try:
                for item in sorted(os.listdir(parent)):
                    cand = os.path.join(parent, item, f"{activity_str}_Fotos")
                    p, y, n = self.search_activity_in_string(item)
                    if (item.lower().endswith('_abgabe') and os.path.isdir(cand)
                            and p and self._activity_key(f"{p} {y}/{n}") == act_key
                            and not self._looks_like_copy_dir(item, [base_dir])
                            and self._path_key(os.path.join(parent, item))
                            not in excluded | {self._path_key(base_dir)}):
                        found.append(cand)
            except Exception:
                pass
            if len(found) == 1:
                return found[0]
        return sibling

    def get_unique_filename(self, target_dir, base_name, ext, source_filepath=None):
        c = 0
        s_let = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        cand = f"{base_name}{ext}"
        while os.path.exists(os.path.join(target_dir, cand)):
            t_path = os.path.join(target_dir, cand)
            if source_filepath and os.path.abspath(source_filepath) == os.path.abspath(t_path):
                return cand
            if source_filepath and os.path.getsize(source_filepath) == os.path.getsize(t_path):
                return None
            cand = f"{base_name}_{s_let[c]}{ext}" if c < len(s_let) else f"{base_name}_{c}{ext}"
            c += 1
        return cand

    def gather_all_photos(self, base_dir, skip_dir_names=None, flat_dirs=None):
        """Walk base_dir recursively, optionally skipping subdirs by name.
        flat_dirs: in diese Ordner (den Abgabe-Fotoordner) wird nur ihre
        oberste Ebene gelesen – Unterordner wie 'aussortiert' bleiben draußen."""
        skip_lower = {s.lower() for s in (skip_dir_names or [])}
        flat = {self._path_key(d) for d in (flat_dirs or [])}
        result = []
        for root, dirs, files in os.walk(base_dir):
            # Prune directories to skip (modifying dirs in-place stops os.walk from descending)
            dirs[:] = [d for d in dirs if d.lower() not in skip_lower]
            if self._path_key(root) in flat:
                dirs[:] = []
            for f in files:
                if f.lower().endswith(('.jpg', '.jpeg')):
                    result.append(os.path.join(root, f))
        return result

    def _get_default_csv_path(self, base_dir, act_norm, exclude=None):
        """Default path for a newly created Fotoliste.

        Abgabe-type structure (base_dir contains an inner _Fotos subfolder):
          → put CSV inside base_dir under an existing *Stellenkatalog*/*Listen* subdir,
            or create {act_norm}_Stellenkatalog_und_Listen/ if none exists yet.
        Simple structure or standalone _Fotos folder:
          → put CSV next to base_dir (sibling).
        """
        t_dir = self.get_output_folder_path(base_dir, act_norm, exclude=exclude)
        # Abgabe-type: t_dir lies inside an Abgabe folder (base_dir itself or a
        # sibling Abgabe folder of the same activity, see get_output_folder_path)
        abgabe = os.path.dirname(t_dir)
        if self._path_key(abgabe) != self._path_key(os.path.dirname(base_dir)):
            # Look for an existing *Stellenkatalog* or *Listen* subdirectory
            try:
                for item in sorted(os.listdir(abgabe)):
                    sub = os.path.join(abgabe, item)
                    if os.path.isdir(sub):
                        lc = item.lower()
                        if 'stellenkatalog' in lc or 'listen' in lc:
                            return os.path.join(sub, f"{act_norm}_Fotoliste.csv")
            except Exception:
                pass
            # None found — use standard name (will be created on save)
            return os.path.join(abgabe,
                                f"{act_norm}_Stellenkatalog_und_Listen",
                                f"{act_norm}_Fotoliste.csv")
        # Simple structure: sibling of base_dir
        return os.path.join(os.path.dirname(base_dir), f"{act_norm}_Fotoliste.csv")

    # Eindeutige Kopie-Merkmale, nur als ganzes Wort: '… - Kopie', 'Kopie von
    # …', 'Copy', 'Backup', 'NEU_…' aus älteren Programmfassungen. Nicht:
    # 'Fotos_kopiert', 'Hangsicherung'. _COPY_HINT zählt zusätzlich '_alt',
    # '_old', 'Sicherung' und '(2)' als Wort; es dient nur der Rangfolge bei der
    # Listensuche ('Morschenich-Alt' ist ein Ort, 'Fläche (2)' eine Teilfläche).
    _STRONG_COPY_HINT = re.compile(
        r"(?:^|[\s_\-])(?:kopie|copy|backup|sicherungskopie)(?=[\s_\-.(]|$)|^neu_",
        re.IGNORECASE)
    _COPY_HINT = re.compile(
        _STRONG_COPY_HINT.pattern
        + r"|(?:^|[\s_\-])(?:alt|old|sicherung|bak)(?=[\s_\-.]|$)|\(\d+\)",
        re.IGNORECASE)
    # Ordnername endet auf ein Kopie-Wort: 'OV_2022_1057_alt', '…_Abgabe_bak'
    # ('vorher' nicht – Vorher-/Nachher-Fotos sind übliche Dokumentation)
    _COPY_SUFFIX = re.compile(
        r"[\s_\-]+(?:alt|old|sicherung|backup|bak|kopie|copy)(?:\s*\(\d+\))?[\s_\-]*$",
        re.IGNORECASE)
    # Windows-Doppel 'Ordner (2)': Kopie nur, wenn 'Ordner' selbst danebenliegt
    _NUM_SUFFIX = re.compile(r"\s*\(\d+\)\s*$")
    # Listen anderer Art; 'sfm' auch mit 'Foto' im Namen (SfM-Fotoliste),
    # 'Fundfoto' aber nicht als Teil von 'Befundfoto'
    _OTHER_LIST_HINT = re.compile(
        r"sfm|fund|zeichn|skizz|vermess|probe|befund|nivell|stellenliste|stellenkatalog",
        re.IGNORECASE)
    _NEVER_FOTOLISTE = re.compile(r"sfm|(?<!be)fundfoto", re.IGNORECASE)

    def _looks_like_copy_dir(self, path, group):
        """Ist dieser Ordner wohl eine Kopie/Sicherung? Nur bei eindeutigen
        Merkmalen ('… - Kopie', 'Kopie von …', 'Backup') oder wenn der Name ein
        anderer Ordner der Gruppe bzw. nur die Aktivität (+ Abgabe/Fotos) mit
        angehängtem '_alt', '_Sicherung', '_bak', '(2)' … ist. Orte und Anlässe
        wie 'Morschenich-Alt', 'Hangsicherung', 'Sicherung_Stadtmauer',
        'Fläche (2)' oder 'Fotos_kopiert' gelten nicht als Kopie."""
        name = os.path.basename(os.path.normpath(path))
        if self._STRONG_COPY_HINT.search(name) or re.fullmatch(
                r"\s*(?:alt|old|sicherung(?:en)?|backups?|bak|kopien?|archiv)\s*",
                name, re.IGNORECASE):
            return True
        others = {os.path.basename(os.path.normpath(g)).lower()
                  for g in group if self._path_key(g) != self._path_key(path)}
        n = self._NUM_SUFFIX.search(name)
        if n:
            return name[:n.start()].lower() in others
        m = self._COPY_SUFFIX.search(name)
        if not m:
            return False
        stem = name[:m.start()]
        if stem.lower() in others:
            return True
        rest = re.sub(r"^[A-Za-z]{2}[\s_/-]?(?:[0-9]{4}|[0-9]{2})[\s_/-]?[0-9]{1,4}", "", stem)
        return rest.strip(" _-").lower() in ('', 'abgabe', 'fotos', 'foto', 'bilder',
                                             'grabung', 'doku', 'dokumentation')

    def _path_looks_like_copy(self, path, levels=3):
        """Liegt eine Datei in einem Kopie-/Sicherungsordner oder heißt so?
        Geprüft werden der Dateiname und die letzten Ordnerebenen."""
        parts, cur = [], path
        for _ in range(levels):
            parts.append(os.path.basename(cur))
            nxt = os.path.dirname(cur)
            if not nxt or nxt == cur:
                break
            cur = nxt
        if self._COPY_HINT.search(parts[0]):
            return True
        return any(self._looks_like_copy_dir(p, []) for p in parts[1:] if p)

    def _list_search_dirs(self, base_dir, act_key, extra_dirs, skip_dirs=None):
        """Ordner für die Listensuche als (Ordner, Tiefe, gehört_zur_Maßnahme,
        Suchwurzel). Wurzel der Maßnahme ist der höchste Ordner bis drei Ebenen
        über base_dir, dessen Name die Aktivität trägt; sie, die
        zusammengeführten Ordner und Nachbarordner mit derselben Aktivität im
        Namen (z.B. '…_Abgabe' neben dem Rohfoto-Ordner) werden bis drei Ebenen
        tief durchsucht (Abgabe/…_Stellenkatalog_und_Listen/), der Ordner
        darüber eine Ebene."""
        act_root, cur = base_dir, base_dir
        for _ in range(3):
            parent = os.path.dirname(cur)
            if not parent or parent == cur:
                break
            if self._activity_in_text(os.path.basename(parent)) == act_key:
                act_root = parent
            cur = parent
        out = []
        skip = {self._path_key(s) for s in (skip_dirs or [])}  # im Batch abgewählt
        seen = set(skip)

        def add(root, max_depth, own, rel_root):
            # rel_root: ab hier zählen Ordnernamen für Tiefe und Kopie-Erkennung
            if not root or not os.path.isdir(root) or self._path_key(root) in skip:
                return
            for cur_dir, dirs, _ in os.walk(root):
                # Unterordner einer ANDEREN Maßnahme (z.B. 'OV_2026_0006_Abgabe'
                # im Ordner von 0005) gehören nicht dazu
                dirs[:] = [x for x in dirs
                           if self._path_key(os.path.join(cur_dir, x)) not in skip
                           and self._activity_in_text(x) in (None, act_key)]
                rel = os.path.relpath(cur_dir, root)
                if (0 if rel == '.' else rel.count(os.sep) + 1) >= max_depth:
                    dirs[:] = []
                k = self._path_key(cur_dir)
                if k not in seen:
                    seen.add(k)
                    out.append((cur_dir, own, rel_root))

        add(act_root, 3, True, act_root)
        top = os.path.dirname(act_root)
        for x in extra_dirs or []:
            add(x, 3, True, os.path.dirname(x))
        try:
            for item in sorted(os.listdir(top)):
                sib = os.path.join(top, item)
                p, y, n = self.search_activity_in_string(item)  # Name BEGINNT mit Aktivität
                if (os.path.isdir(sib) and p
                        and self._activity_key(f"{p} {y}/{n}") == act_key
                        and not self._looks_like_copy_dir(sib, [act_root])):
                    add(sib, 3, True, top)
        except Exception:
            pass
        add(top, 1, False, top)
        return out

    def _find_existing_csv(self, base_dir, act_norm, extra_dirs=None, skip_dirs=None):
        """Sucht die vorhandene Fotoliste dieser Aktivität.

        Infrage kommen nur Listen mit den Spalten StellenNr und PosNr, die nach
        einer Fotoliste aussehen ('foto'/'bild' im Namen oder Spalte Fotograf/
        FotoDatum) – Fund-, SfM- (auch 'SfM-Fotoliste'), Zeichnungs- oder
        Stellenlisten scheiden aus. Listen mit Einträgen nur ANDERER
        Aktivitäten ebenso; eine Liste ohne Aktivitätsangabe nur, wenn ihr Name
        die Aktivität trägt oder sie im Ordner der Maßnahme selbst liegt (keine
        fremde Vorlage im Sammelordner). Rangfolge: Einträge genau dieser
        Aktivität, Standardort des Programms, keine Kopie/Sicherung, passender
        Name, Name nach Art 'Fotoliste'/'Digitalbildliste', möglichst weit oben."""
        act_key = self._activity_key(act_norm)
        default = self._path_key(self._get_default_csv_path(base_dir, act_norm,
                                                            exclude=skip_dirs))
        # Liegen die fertigen Fotos in einem Abgabeordner, gehört die Liste
        # bevorzugt dorthin (vor gleichwertigen Listen in Nachbarordnern)
        abg = os.path.dirname(self.get_output_folder_path(base_dir, act_norm,
                                                          exclude=skip_dirs))
        abg_key = (self._path_key(abg) + os.sep
                   if self._path_key(abg) != self._path_key(os.path.dirname(base_dir))
                   else None)
        best, best_score, order = None, None, 0
        for d, own, rel_root in self._list_search_dirs(base_dir, act_key, extra_dirs,
                                                       skip_dirs):
            try:
                files = sorted(os.listdir(d))
            except Exception:
                continue
            for f in files:
                if not f.lower().endswith('.csv'):
                    continue
                lname = f.lower()
                named_foto = 'foto' in lname or 'bild' in lname
                if self._NEVER_FOTOLISTE.search(f) or (
                        not named_foto and self._OTHER_LIST_HINT.search(f)):
                    continue
                fp = os.path.join(d, f)
                info = self._inspect_csv(fp)
                if not info or not info['compatible']:
                    continue
                if not (named_foto or info['fotocols']):
                    continue
                name_act = self._activity_in_text(f)
                acts = info['activities']
                own_rows = act_key in acts
                if acts and not own_rows:
                    # Liste einer anderen Maßnahme. Nur melden, wenn der Name
                    # das nicht ohnehin verrät.
                    if name_act is None or name_act == act_key:
                        self.log(f"⚠ CSV übersprungen (Einträge anderer Aktivität): {fp}")
                    continue
                if not acts and name_act != act_key and (name_act is not None or not own):
                    continue
                folders = os.path.relpath(d, rel_root).split(os.sep)
                folders = [] if folders == ['.'] else folders
                depth = len(folders)
                is_copy = bool(self._COPY_HINT.search(f)) or any(
                    self._looks_like_copy_dir(p, []) for p in folders)
                list_name = bool(re.search(r'(foto|digitalbild|bild)liste', lname))
                in_abgabe = bool(abg_key) and self._path_key(fp).startswith(abg_key)
                score = (own_rows, self._path_key(fp) == default, not is_copy, in_abgabe,
                         name_act == act_key, list_name, named_foto, info['fotocols'],
                         -depth, -order)
                order += 1
                if best_score is None or score > best_score:
                    best, best_score = fp, score
        return best

    @staticmethod
    def _normalize_activity(s):
        """Strip separators and uppercase for comparison.
        Leading zeros in numbers are intentionally preserved:
        'OV 2026/0014' and 'OV 2026/14' are NOT the same activity."""
        return re.sub(r'[\s_/\-]+', '', s).upper()

    def _core_process_photos(self, mode, raw_act, base_dir, filter_raw,
                             ignore_old_exif, main_photo, photo_mapping,
                             extra_dirs=None, **kwargs):
        p, y, pr = self.parse_activity(raw_act)
        if not p or not os.path.isdir(base_dir):
            return None
        act_norm = f"{p}_{y}_{pr}"
        self.log(f"\n=== PROZESS-START FÜR {act_norm} ===")

        allowed = ([f"{int(x.strip()):04d}" for x in filter_raw.split(",")
                    if x.strip().isdigit()] if filter_raw.strip() else None)
        out_dir = self.get_output_folder_path(base_dir, act_norm,
                                              exclude=kwargs.get('skipped_dirs'))
        out_key = self._path_key(out_dir)
        t_dir = out_dir if mode == "rename_and_move" else base_dir
        if mode == "rename_and_move" and not os.path.exists(t_dir):
            os.makedirs(t_dir)

        # Fotos aus Haupt- und zusammengeführten Ordnern. Aus dem Abgabe-
        # Fotoordner zählt nur seine oberste Ebene; Unterordner darin (z.B.
        # 'aussortiert') werden nie angefasst.
        fotos_folder = f"{act_norm}_Fotos"
        found = {}
        for d in [base_dir] + [x for x in (extra_dirs or []) if os.path.isdir(x)]:
            for f in self.gather_all_photos(d, skip_dir_names=[fotos_folder],
                                            flat_dirs=[out_dir]):
                found.setdefault(self._path_key(f), f)
        if mode == "rename_and_move" and os.path.isdir(out_dir):
            for f in self.gather_all_photos(out_dir, flat_dirs=[out_dir]):
                found.setdefault(self._path_key(f), f)
        all_f = sorted(found.values())
        r_c, m_c = 0, 0

        for fp in all_f:
            fn = os.path.basename(fp)
            parsed = self.parse_photo_name(fn)
            # Fertig benannte Fotos im Abgabe-Fotoordner bleiben, wo sie sind;
            # ein dort abgelegtes Rohfoto ('7-3.jpg') wird an Ort und Stelle
            # umbenannt.
            if (mode == "rename_and_move" and not parsed
                    and self._path_key(os.path.dirname(fp)) == out_key):
                continue

            if parsed:
                st, pos = parsed
                if allowed and st not in allowed:
                    continue
                ed = self.get_exif_date_pure(fp)
                if ed and ed.year < y and not ignore_old_exif:
                    self.log(f"   [X] Ignoriert: {fn} (Jahr vor Grabung).")
                    continue
                # 'Nur umbenennen' benennt vor Ort um (im Ordner des Fotos)
                dest = os.path.dirname(fp) if mode == "rename_only" else t_dir
                final_fn = self.get_unique_filename(
                    dest, f"{act_norm}_{st}_{pos}",
                    os.path.splitext(fn)[1].lower(), source_filepath=fp)
                if final_fn is None:
                    self.log(f"   [-] Übersprungen: '{fn}' identisch vorhanden.")
                    continue
                f_path = os.path.join(dest, final_fn)
                # Guard: don't move/rename a file to itself
                if os.path.abspath(fp) == os.path.abspath(f_path):
                    self.log(f"   [-] Bereits korrekt benannt: {fn}")
                    continue
                try:
                    (os.rename(fp, f_path) if mode == "rename_only"
                     else shutil.move(fp, f_path))
                    self.rename_history[f_path] = fp
                    r_c += 1
                    self.log(f"ERFOLG: {fn} -> {final_fn}")
                except Exception as e:
                    self.log(f"FEHLER: {str(e)}")

            elif mode == "rename_and_move":
                m = re.match(
                    rf"^{act_norm}_([0-9]{{4}})_([0-9]{{3}})(_[A-Z]|[0-9]+)?\.jpe?g$",
                    fn, re.IGNORECASE)
                if m:
                    if allowed and m.group(1) not in allowed:
                        continue
                    final_fn = self.get_unique_filename(
                        t_dir, os.path.splitext(fn)[0],
                        os.path.splitext(fn)[1].lower(), source_filepath=fp)
                    if final_fn is None:
                        continue
                    f_path = os.path.join(t_dir, final_fn)
                    # Guard: don't move a file to itself
                    if os.path.abspath(fp) == os.path.abspath(f_path):
                        continue
                    try:
                        shutil.move(fp, f_path)
                        self.rename_history[f_path] = fp
                        m_c += 1
                        self.log(f"VERSCHOBEN: {fn}")
                    except Exception as e:
                        self.log(f"FEHLER: {str(e)}")
        return r_c, m_c

    def _core_move_to_existing(self, raw_act, base_dir, filter_raw,
                               extra_dirs=None, **kwargs):
        p, y, pr = self.parse_activity(raw_act)
        if not p or not os.path.isdir(base_dir):
            return None
        act_norm = f"{p}_{y}_{pr}"
        t_dir = self.get_output_folder_path(base_dir, act_norm,
                                            exclude=kwargs.get('skipped_dirs'))
        if not os.path.exists(t_dir):
            os.makedirs(t_dir)
        allowed = ([f"{int(x.strip()):04d}" for x in filter_raw.split(",")
                    if x.strip().isdigit()] if filter_raw.strip() else None)
        fotos_folder = f"{act_norm}_Fotos"
        found = {}
        for d in [base_dir] + [x for x in (extra_dirs or []) if os.path.isdir(x)]:
            for f in self.gather_all_photos(d, skip_dir_names=[fotos_folder],
                                            flat_dirs=[t_dir]):
                found.setdefault(self._path_key(f), f)
        m_c = 0
        for fp in sorted(found.values()):
            if os.path.abspath(os.path.dirname(fp)) == os.path.abspath(t_dir):
                continue
            fn = os.path.basename(fp)
            if re.match(
                    rf"^{act_norm}_([0-9]{{4}})_([0-9]{{3}})(_[A-Z]|[0-9]+)?\.jpe?g$",
                    fn, re.IGNORECASE):
                if (allowed and
                        re.match(rf"^{act_norm}_([0-9]{{4}})_",
                                 fn, re.IGNORECASE).group(1) not in allowed):
                    continue
                final_fn = self.get_unique_filename(
                    t_dir, os.path.splitext(fn)[0],
                    os.path.splitext(fn)[1].lower(), source_filepath=fp)
                if final_fn is None:
                    continue
                f_path = os.path.join(t_dir, final_fn)
                try:
                    shutil.move(fp, f_path)
                    self.rename_history[f_path] = fp
                    m_c += 1
                except:
                    pass
        return m_c

    def _generate_fresh_rows(self, act_norm, act_wnk, y, allowed, ign_exif,
                             p_map, main_p, search_dirs, flat_dirs=None):
        # Jede Datei nur einmal, auch wenn sie über zwei Suchordner erreichbar
        # ist (z.B. _Fotos liegt im Quellordner) oder der Pfad einmal mit / und
        # einmal mit \ geschrieben ist. Aus dem Abgabe-Fotoordner (flat_dirs)
        # zählt nur die oberste Ebene, nicht z.B. 'aussortiert/'.
        unique = {}
        for d in search_dirs:
            if d and os.path.exists(d):
                for f in self.gather_all_photos(d, flat_dirs=flat_dirs):
                    unique.setdefault(self._path_key(f), f)
        all_f = sorted(unique.values())
        rows = []
        for fp in all_f:
            fn = os.path.basename(fp)
            st, pos = None, None
            m = re.match(
                rf"^{act_norm}_([0-9]{{4}})_([0-9]{{3}})(_[A-Z]|[0-9]+)?\.jpe?g$",
                fn, re.IGNORECASE)
            if m:
                st, pos = m.group(1), m.group(2)
            else:
                pp = self.parse_photo_name(fn)
                if pp:
                    st, pos = pp
            if st and pos:
                if allowed and st not in allowed:
                    continue
                ed = self.get_exif_date_pure(fp)
                d_str = ""
                if ed:
                    if ed.year < y and not ign_exif:
                        continue
                    else:
                        d_str = ed.strftime("%d.%m.%Y")
                s_int, p_int = int(st), int(pos)
                rows.append({
                    "Aktivitaet": act_wnk,
                    "StellenNr": str(s_int),
                    "PosNr": str(p_int),
                    "Fotograf": p_map.get((s_int, p_int), main_p),
                    "FotoDatum": d_str,
                    "Kommentar": "",
                    "_sort_stelle": s_int,
                    "_sort_pos": p_int,
                    "_src": fp,
                    "_date": ed if d_str else None,
                })
        return rows

    # =========================================================================
    # FOTOLISTE: LESEN, ZUSAMMENFÜHREN, SPEICHERN
    # =========================================================================
    # Grundregel: Jede Kombination aus Aktivität, Stelle und Position steht
    # höchstens EINMAL in einer Fotoliste. Vorhandene Einträge (samt
    # Kommentaren) bleiben erhalten; aus den Fotos kommt nur hinzu, was noch
    # fehlt. Geschrieben wird erst nach Bestätigung im Speichern-Dialog.

    @staticmethod
    def _path_key(path):
        """Vergleichsform eines Pfads: dieselbe Datei ergibt denselben Schlüssel,
        egal ob mit / oder \\ und in welcher Groß-/Kleinschreibung."""
        return os.path.normcase(os.path.abspath(path))

    @staticmethod
    def _to_int(value):
        """'5', ' 0005 ', '5.0' und '5,00' (Excel) -> 5; '1.000' (deutscher
        Tausenderpunkt) -> 1000; leere oder andere Werte -> None."""
        s = str(value or '').strip()
        if re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{3})+', s):
            return int(s.replace('.', ''))
        m = re.fullmatch(r'([0-9]+)(?:[.,]0{1,2})?', s)
        return int(m.group(1)) if m else None

    def _activity_key(self, text, strict=False):
        """Vergleichsform einer Aktivität: 'OV 2022/1068', 'OV_22_1068' und
        'OV_2022_1068' ergeben dasselbe ('OV', 2022, 1068). strict: anderer
        Text (z.B. '--- Tag 2 ---' oder 'dto.' in der Spalte Aktivitaet) gilt
        nicht als Aktivität (None)."""
        s = str(text or '').strip()
        if not s:
            return None
        m = re.fullmatch(
            r"([A-Za-z]{2})[\s_/-]*([0-9]{4}|[0-9]{2})[\s_/-]*([0-9]{1,5})", s)
        if not m:
            return None if strict else self._normalize_activity(s)
        year = int(m.group(2)) + (2000 if len(m.group(2)) == 2 else 0)
        return (m.group(1).upper(), year, int(m.group(3)))

    def _activity_in_text(self, text):
        """Aktivität irgendwo in einem Datei- oder Ordnernamen, sonst None."""
        m = re.search(r"(?:^|[^A-Za-z])([A-Za-z]{2})[\s_/-]?([0-9]{4}|[0-9]{2})"
                      r"[\s_/-]?([0-9]{1,4})(?![0-9])", text)
        return self._activity_key(f"{m.group(1)} {m.group(2)}/{m.group(3)}") if m else None

    @staticmethod
    def _activity_label(key):
        return f"{key[0]} {key[1]}/{key[2]}" if isinstance(key, tuple) else str(key)

    @staticmethod
    def _field_label(field):
        """Spaltenname, wie er in der Datei steht (siehe _read_csv_table)."""
        return field.split('\x00', 1)[0]

    def _read_csv_table(self, path):
        """Liest eine Liste vollständig und verlustfrei ein.
        - Kodierung: UTF-8 mit/ohne BOM oder cp1252; Trennzeichen ; Tab , oder
          aus einer Excel-Zeile 'sep=;'.
        - Kopfzeile = erste der ersten Zeilen mit StellenNr und PosNr; Zeilen
          darüber (z.B. 'sep=;' oder ein Titel) werden als Vorspann unverändert
          zurückgeschrieben.
        - Doppelte oder leere Spaltennamen bekommen intern eindeutige Namen
          ('Kommentar' + '\\x00' + Spaltennummer), damit keine Spalte eine
          andere überschreibt; geschrieben wird wieder der Originalname.
        - Mehr Felder als Spalten (z.B. ein ';' im Kommentar ohne Anführungs-
          zeichen): der Überhang wird ans letzte Feld wieder angehängt.
        Lesefehler werden weitergereicht – eine Liste darf nie halb gelesen
        überschrieben werden. Gibt (Spalten, Zeilen, Vorspann) zurück; ganz
        leere Zeilen entfallen."""
        with open(path, 'rb') as f:
            raw = f.read()
        if raw.startswith(b'\xef\xbb\xbf'):
            text = raw[3:].decode('utf-8', errors='replace')
        else:
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                text = raw.decode('cp1252', errors='replace')
        lines = text.splitlines(keepends=True)
        delim, start = None, 0
        first = lines[0].rstrip('\r\n') if lines else ''
        if re.fullmatch(r'sep=.', first, re.IGNORECASE):
            delim, start = first[4], 1
        head_idx = start
        for i in range(start, min(start + 5, len(lines))):
            if 'StellenNr' in lines[i] and 'PosNr' in lines[i]:
                head_idx = i
                break
        preamble = ''.join(lines[:head_idx])
        header = lines[head_idx] if head_idx < len(lines) else ''
        if delim is None:
            delim = max((';', '\t', ','), key=header.count)
            if not header.count(delim):
                delim = ';'
        reader = csv.reader(io.StringIO(''.join(lines[head_idx:]), newline=''),
                            delimiter=delim)
        head = next(reader, [])
        fields, seen = [], set()
        for i, name in enumerate(n.strip() for n in head):
            fields.append(name if name and name not in seen else f"{name}\x00{i}")
            seen.add(name)
        rows, n_head = [], len(fields)
        for vals in reader:
            while len(vals) > n_head and not vals[-1].strip():
                vals.pop()  # leere Felder hinter der letzten Spalte (';;' am Zeilenende)
            if n_head and len(vals) > n_head:
                if fields[n_head - 1] in ('Aktivitaet', 'StellenNr', 'PosNr',
                                          'Fotograf', 'FotoDatum'):
                    # Letzte Spalte ist ein Datenfeld: Überhang in eigene,
                    # unbenannte Zusatzspalten statt das Feld zu verfälschen.
                    while len(fields) < len(vals):
                        fields.append(f"\x00{len(fields)}")
                else:
                    # ';' im Kommentar ohne Anführungszeichen: wieder anhängen
                    vals = vals[:n_head - 1] + [delim.join(vals[n_head - 1:])]
            row = {f: (vals[i] if i < len(vals) else '') for i, f in enumerate(fields)}
            if any(v.strip() for v in row.values()):
                rows.append(row)
        return fields, rows, preamble

    def _inspect_csv(self, path):
        """Kurzprofil einer CSV (None, wenn sie sich nicht lesen lässt)."""
        try:
            fields, rows, preamble = self._read_csv_table(path)
        except Exception:
            return None
        fs = set(fields)
        acts = {self._activity_key(r.get('Aktivitaet', ''), strict=True) for r in rows}
        acts.discard(None)
        return {'fields': fields, 'rows': rows, 'preamble': preamble,
                'compatible': {'StellenNr', 'PosNr'} <= fs,
                'fotocols': bool({'Fotograf', 'FotoDatum'} & fs),
                'activities': acts}

    def _dedupe_fresh_rows(self, rows, act_norm):
        """Eine Zeile je Stelle/Position. Mehrere Fotos derselben Stelle/Position
        – z.B. ..._0005_010.jpg und ..._0005_010_A.jpg oder ein liegengebliebenes
        Rohfoto '5-10.jpg' neben der umbenannten Kopie – ergeben nur EINEN
        Eintrag. Vorrang hat das regulär benannte Foto, sonst das älteste.
        Gibt (eindeutige Zeilen, {(stelle, pos): [Dateien]}) zurück."""
        prefix = act_norm.lower() + '_'

        def rank(r, canon):
            stem = os.path.splitext(os.path.basename(r['_src']))[0].lower()
            return (0 if stem == canon else 1 if stem.startswith(prefix) else 2,
                    r['_date'] or datetime.max, r['_src'].lower())

        groups = {}
        for r in rows:
            groups.setdefault((r['_sort_stelle'], r['_sort_pos']), []).append(r)
        unique, dups = [], {}
        for (st, pos), grp in sorted(groups.items()):
            if len(grp) > 1:
                canon = f"{prefix}{st:04d}_{pos:03d}"
                grp.sort(key=lambda r: rank(r, canon))
                if not grp[0]['FotoDatum']:
                    dated = sorted((r for r in grp if r['_date']), key=lambda r: r['_date'])
                    if dated:
                        grp[0]['FotoDatum'] = dated[0]['FotoDatum']
                dups[(st, pos)] = [r['_src'] for r in grp]
            unique.append(grp[0])
        return unique, dups

    def _build_csv_plan(self, d, list_path=None):
        """Bereitet die Fotoliste einer Maßnahme vor, OHNE zu schreiben.
        list_path: vom Nutzer gewählte vorhandene Liste (Einzel, Aktion 5);
        sonst wird die vorhandene Liste gesucht. None bei ungültiger
        Aktivität oder fehlendem Ordner."""
        p, y, pr = self.parse_activity(d.get('raw_act', ''))
        base_dir = d.get('base_dir', '')
        if not p or not base_dir or not os.path.isdir(base_dir):
            return None
        act_norm, act_wnk = f"{p}_{y}_{pr}", f"{p} {y}/{int(pr)}"
        extra = [x for x in (d.get('extra_dirs') or []) if os.path.isdir(x)]
        skipped = d.get('skipped_dirs') or []
        t_dir = self.get_output_folder_path(base_dir, act_norm, exclude=skipped)
        filter_raw = d.get('filter_raw', '') or ''
        allowed = ([f"{int(x.strip()):04d}" for x in filter_raw.split(",")
                    if x.strip().isdigit()] if filter_raw.strip() else None)
        rows = self._generate_fresh_rows(
            act_norm, act_wnk, y, allowed, d.get('ignore_old_exif', False),
            d.get('photo_mapping') or {}, d.get('main_photo', ''),
            [base_dir, t_dir] + extra, flat_dirs=[t_dir])
        fresh, photo_dups = self._dedupe_fresh_rows(rows, act_norm)
        if photo_dups:
            self.log(f"{act_wnk}: {len(photo_dups)}× mehrere Fotos derselben "
                     f"Stelle/Position – je nur EIN Eintrag in der Fotoliste:")
            for (st, pos), files in list(photo_dups.items())[:30]:
                self.log(f"   [=] {st}-{pos}: "
                         + ", ".join(os.path.basename(f) for f in files))
            if len(photo_dups) > 30:
                self.log(f"   … und {len(photo_dups) - 30} weitere")
        act_key = self._activity_key(act_wnk)
        pin_key = (act_key, self._path_key(base_dir))
        if list_path is None:
            # In dieser Sitzung für DIESEN Quellordner über »Speicherort
            # ändern…« woanders gespeichert (z.B. auf einen Stick)? Dann diese
            # Liste weiterführen, statt am Standardort eine zweite anzulegen.
            chosen = self._chosen_targets.get(pin_key)
            info = self._inspect_csv(chosen) if chosen and os.path.isfile(chosen) else None
            if info and info['compatible'] and (not info['activities']
                                                or act_key in info['activities']):
                list_path = chosen
        if list_path is None:
            list_path = self._find_existing_csv(base_dir, act_norm, extra_dirs=extra,
                                                skip_dirs=skipped)
        return {
            'label': act_wnk,
            'act_key': act_key,
            'pin_key': pin_key,
            'user_target': False,  # True, sobald »Speicherort ändern…« benutzt wurde
            'source': list_path,
            'target': list_path or self._get_default_csv_path(base_dir, act_norm,
                                                              exclude=skipped),
            'fresh': fresh,
            'photo_dups': photo_dups,
            'selected': True,
        }

    def _compose_csv(self, plan, merge_dups=True):
        """Berechnet, was nach plan['target'] geschrieben würde – schreibt aber
        nichts. Grundlage sind die Zieldatei (falls vorhanden) und die bisherige
        Liste plan['source']; aus den Fotos kommt nur hinzu, was dort nach
        Aktivität + Stelle + Position noch fehlt. Mit merge_dups werden schon
        vorhandene Doppel-Einträge verlustfrei zusammengeführt (leere Felder
        werden aufgefüllt); widersprechen sich ihre Angaben, bleiben sie stehen
        und werden gemeldet."""
        target, source, own = plan['target'], plan['source'], plan['act_key']
        res = {'error': None, 'foreign': False, 'other_acts': set(), 'looks_foto': True,
               'target_exists': os.path.isfile(target),
               'target_is_source': bool(source) and
               self._path_key(source) == self._path_key(target),
               'looks_copy': self._path_looks_like_copy(target),
               'n_base': 0, 'n_carried': 0, 'n_new': 0, 'n_known': 0, 'n_filled': 0,
               'n_foreign_left': 0, 'n_act_fixed': 0,
               'dup_lossless': [], 'dup_conflicts': [], 'src_conflicts': [],
               'bad_chars': set(), 'merge_dups': merge_dups, 'preamble': '',
               'changed': False, 'fields': list(FOTOLISTE_FIELDS), 'rows': []}

        tables = []  # (Profil, ist_Zieldatei) – Zieldatei zuerst, sie hat Vorrang
        if res['target_exists']:
            info = self._inspect_csv(target)
            if info is None:
                res['error'] = f"Zieldatei lässt sich nicht lesen: {target}"
                return res
            if info['compatible']:
                tables.append((info, True))
                lname = os.path.basename(target).lower()
                res['looks_foto'] = info['fotocols'] or 'foto' in lname or 'bild' in lname
                res['other_acts'] = {a for a in info['activities'] if a != own}
            else:
                res['foreign'] = True  # keine Fotoliste – würde nach Rückfrage ersetzt
        if source and not res['target_is_source']:
            info = self._inspect_csv(source) if os.path.isfile(source) else None
            if info is None or not info['compatible']:
                res['error'] = f"Bisherige Fotoliste lässt sich nicht lesen: {source}"
                return res
            tables.append((info, False))

        fields = list(tables[0][0]['fields']) if tables else []
        for info, _ in tables[1:]:
            fields += [f for f in info['fields'] if f not in fields]
        fields += [f for f in FOTOLISTE_FIELDS if f not in fields]
        res['preamble'] = tables[0][0]['preamble'] if tables else ''
        key_fields = ('Aktivitaet', 'StellenNr', 'PosNr')

        def key_of(r, act):
            s, p = self._to_int(r.get('StellenNr')), self._to_int(r.get('PosNr'))
            if s is None or p is None:
                return None  # nicht auswertbar: Zeile bleibt unverändert stehen
            return (act, s, p)

        out, out_keys, out_ti, where, loose = [], [], [], {}, {}
        for ti, (info, is_target) in enumerate(tables):
            # Leere Aktivität erbt die der Zeile darüber (Sammellisten, in denen
            # die Aktivität nur in der ersten Zeile eines Blocks steht); vor der
            # ersten Angabe gilt die eigene Aktivität. Nur echte Aktivitäts-
            # angaben zählen – '--- Tag 2 ---' oder 'dto.' in der Spalte nicht.
            last_act = own
            for r in info['rows']:
                act = self._activity_key(r.get('Aktivitaet', ''), strict=True)
                last_act = act or last_act
                k = key_of(r, last_act)
                if not is_target and last_act != own:
                    # Aus einer Sammelliste nur die eigene Maßnahme in eine
                    # ANDERE Datei übernehmen; der Rest bleibt, wo er ist.
                    if k is not None:
                        res['n_foreign_left'] += 1
                    continue
                if k is None:
                    sig = tuple((r.get(f) or '').strip() for f in fields)
                    if ti > 0 and loose.get(sig, 0) > 0:
                        loose[sig] -= 1  # gleiche Zeile steht schon in der Zieldatei
                        continue
                    if ti == 0:
                        loose[sig] = loose.get(sig, 0) + 1
                else:
                    if ti > 0 and any(t < ti for _, t in where.get(k, [])):
                        # Steht schon in der Zieldatei: deren Angaben haben
                        # Vorrang; leere Felder dort aus der bisherigen Liste
                        # auffüllen, Widersprüche melden.
                        tgt, diff = out[where[k][0][0]], []
                        for f in fields:
                            sv = (r.get(f) or '').strip()
                            if not sv or f in key_fields:
                                continue
                            tv = (tgt.get(f) or '').strip()
                            if not tv:
                                tgt[f] = r[f]
                                res['n_filled'] += 1
                            elif tv != sv:
                                diff.append(f)
                        if diff:
                            res['src_conflicts'].append((k, diff))
                        continue
                    where.setdefault(k, []).append((len(out), ti))
                out.append(dict(r))
                out_keys.append(k)
                out_ti.append(ti)
                res['n_base' if is_target else 'n_carried'] += 1

        # Schon vorhandene Doppel-Einträge (z.B. aus früheren Läufen)
        drop = set()
        for k, places in where.items():
            if len(places) < 2:
                continue
            group = [out[i] for i, _ in places]
            conflict = [f for f in fields if f not in key_fields
                        and len({(r.get(f) or '').strip() for r in group} - {''}) > 1]
            if conflict:
                res['dup_conflicts'].append((k, len(group), conflict))
                continue
            res['dup_lossless'].append((k, len(group)))
            if merge_dups:
                keep = group[0]
                for r in group[1:]:
                    for f in fields:
                        if not (keep.get(f) or '').strip() and (r.get(f) or '').strip():
                            keep[f] = r[f]
                drop.update(i for i, _ in places[1:])
        if drop:
            out = [r for i, r in enumerate(out) if i not in drop]
            out_keys = [k for i, k in enumerate(out_keys) if i not in drop]
            out_ti = [t for i, t in enumerate(out_ti) if i not in drop]

        # Reihenfolge der vorhandenen Zeilen: nach Aktivität (in der Reihenfolge
        # ihres ersten Auftretens), Stelle und Position. Zeilen ohne Nummer
        # (Überschriften, Trennzeilen wie '--- Tag 2 ---') bleiben direkt VOR
        # der Zeile, vor der sie standen, am Ende stehende bleiben am Ende.
        ranks, keyed = {}, []
        for k in out_keys:
            keyed.append(None if k is None else
                         (ranks.setdefault(k[0], len(ranks)), k[1], k[2]))
        order_keys, nxt = [None] * len(out), (float('inf'), 0, 0)
        for i in range(len(out) - 1, -1, -1):
            if keyed[i] is not None:
                nxt = keyed[i]
            order_keys[i] = nxt + (i,)
        own_rank = ranks.setdefault(own, len(ranks))
        # Eine nicht nach Stelle/Position geordnete Liste (z.B. chronologisch)
        # wird NICHT umsortiert: neue Einträge kommen hinter die letzte Zeile
        # mit Nummer (vor abschließende Notizzeilen). Maßgeblich ist die
        # Ordnung der Grundliste selbst, nicht angehängte Zeilen einer zweiten.
        present = [k for k, t in zip(keyed, out_ti) if k is not None and t == 0]
        keep_order = any(a > b for a, b in zip(present, present[1:]))
        if keep_order:
            last = max((i for i, k in enumerate(keyed) if k is not None), default=-1)
            order_keys = [(0, i) if i <= last else (2, i) for i in range(len(out))]

        # Neue Einträge aus den Fotos – nur, was noch fehlt
        keys = set(where)
        for fr in plan['fresh']:
            k = (own, fr['_sort_stelle'], fr['_sort_pos'])
            if k in keys:
                res['n_known'] += 1
                continue
            keys.add(k)
            row = {f: '' for f in fields}
            row.update({f: fr[f] for f in FOTOLISTE_FIELDS})
            order_keys.append((1, k[1], k[2]) if keep_order
                              else (own_rank, k[1], k[2], len(order_keys)))
            out.append(row)
            out_keys.append(k)
            res['n_new'] += 1
        ordered = sorted(zip(order_keys, out, out_keys), key=lambda t: t[0])
        out = [r for _, r, _ in ordered]

        # Jede Zeile muss beim nächsten Lesen dieselbe Aktivität ergeben wie
        # jetzt. Ist eine Blockkopf-Zeile weggefallen (zusammengeführt) oder
        # steht eine Zeile jetzt unter einer anderen Maßnahme, wird ihre
        # Aktivität ausdrücklich eingetragen.
        cur = own
        for r, (_, _, k) in zip(out, ordered):
            a = self._activity_key(r.get('Aktivitaet', ''), strict=True)
            if a is not None:
                cur = a
            elif k is not None and k[0] != cur:
                r['Aktivitaet'] = self._activity_label(k[0])
                cur = k[0]
                res['n_act_fixed'] += 1

        # Zeichen, die die Windows-Kodierung der Liste (cp1252) nicht kennt –
        # in Zeilen, Spaltennamen und Vorspann (Titelzeile)
        texts = [v for r in out for v in r.values()] + [res['preamble']] + [
            self._field_label(f) for f in fields]
        for v in texts:
            try:
                (v or '').encode('cp1252')
            except UnicodeEncodeError:
                res['bad_chars'].update(ch for ch in v if not self._cp1252_ok(ch))

        base_fields = tables[0][0]['fields'] if tables and tables[0][1] else None
        res['changed'] = bool(not res['target_exists'] or res['foreign']
                              or res['n_new'] or res['n_carried'] or res['n_filled']
                              or res['n_act_fixed'] or drop or fields != base_fields)
        res['fields'], res['rows'] = fields, out
        return res

    @staticmethod
    def _cp1252_ok(ch):
        try:
            ch.encode('cp1252')
            return True
        except UnicodeEncodeError:
            return False

    @staticmethod
    def _n(n, one, many):
        return f"{n} {one if n == 1 else many}"

    def _describe_comp(self, plan, comp):
        """Texte für den Speichern-Dialog: (Hinweise, Warnungen, ist_Fehler)."""
        if comp['error']:
            return "", "✖ " + comp['error'], True
        info, warn = [], []
        src = plan['source']
        if comp['foreign']:
            warn.append("⚠ Die gewählte Datei ist keine Fotoliste (Spalten StellenNr/PosNr "
                        "fehlen) – sie würde ERSETZT (Sicherung .bak).")
        elif comp['target_exists']:
            info.append(f"Ziel: vorhandene Liste mit {self._n(comp['n_base'], 'Eintrag', 'Einträgen')}"
                        " – wird ergänzt (Sicherung .bak).")
        elif src:
            info.append("Ziel: neue Datei.")
        else:
            info.append("Ziel: neue Datei (keine vorhandene Fotoliste gefunden"
                        + (" – zum Anlegen anhaken)." if not plan['selected'] else ")."))
        if src and not comp['target_is_source']:
            info.append(f"Bisherige Liste: {src}\n   → "
                        f"{self._n(comp['n_carried'], 'Eintrag wird', 'Einträge werden')} "
                        "daraus übernommen"
                        + (f", {self._n(comp['n_filled'], 'leeres Feld', 'leere Felder')} "
                           "der Zieldatei daraus ergänzt" if comp['n_filled'] else "")
                        + "; sie selbst bleibt unverändert.")
        if comp['n_foreign_left']:
            info.append(f"{self._n(comp['n_foreign_left'], 'Eintrag', 'Einträge')} anderer "
                        "Maßnahmen aus der bisherigen Liste bleiben dort und werden nicht "
                        "übernommen.")
        if comp['src_conflicts']:
            keys = ", ".join(f"{k[1]}-{k[2]}" for k, _ in comp['src_conflicts'][:8])
            more = " …" if len(comp['src_conflicts']) > 8 else ""
            warn.append(f"⚠ Bei {self._n(len(comp['src_conflicts']), 'Eintrag', 'Einträgen')} "
                        "weicht die bisherige Liste von der Zieldatei ab; es gelten die "
                        f"Angaben der Zieldatei (Stelle-Position): {keys}{more}")
        if comp['looks_copy']:
            warn.append("⚠ Die Zieldatei sieht nach einer Kopie/Sicherung aus – "
                        "ist das wirklich die gültige Fotoliste?")
        if comp['bad_chars']:
            warn.append("⚠ Diese Zeichen kennt die Fotoliste (Windows-Kodierung) nicht, "
                        "sie werden zu '?': " + " ".join(sorted(comp['bad_chars']))[:60])
        info.append(f"Aus den Fotos neu: {self._n(comp['n_new'], 'Eintrag', 'Einträge')}"
                    + (f" ({self._n(comp['n_known'], 'Stelle/Position steht', 'Stellen/Positionen stehen')}"
                       " schon in der Liste)" if comp['n_known'] else "") + ".")
        if plan['photo_dups']:
            info.append(f"{self._n(len(plan['photo_dups']), 'Stelle/Position', 'Stellen/Positionen')}"
                        " mit mehreren Fotos (z.B. _A-Varianten) – je nur ein Eintrag "
                        "(Dateien siehe Protokoll).")
        if comp['dup_lossless']:
            n = self._n(len(comp['dup_lossless']), 'doppelter Eintrag', 'doppelte Einträge')
            if comp['merge_dups']:
                info.append(f"{n} der vorhandenen Liste: wird verlustfrei zusammengeführt.")
            else:
                warn.append(f"⚠ {n} der vorhandenen Liste: bleibt stehen.")
        if comp['dup_conflicts']:
            keys = ", ".join(f"{k[1]}-{k[2]}" for k, _, _ in comp['dup_conflicts'][:8])
            more = " …" if len(comp['dup_conflicts']) > 8 else ""
            warn.append(f"⚠ {self._n(len(comp['dup_conflicts']), 'doppelter Eintrag', 'doppelte Einträge')}"
                        f" mit abweichenden Angaben bleibt stehen – bitte von Hand prüfen "
                        f"(Stelle-Position): {keys}{more}")
        if comp['other_acts']:
            warn.append("⚠ Die Zieldatei enthält Einträge anderer Aktivität(en): "
                        + ", ".join(sorted(self._activity_label(a)
                                           for a in comp['other_acts'])))
        if comp['target_exists'] and not comp['foreign'] and not comp['looks_foto']:
            warn.append("⚠ Die Zieldatei sieht nicht wie eine Fotoliste aus "
                        "(keine Spalte Fotograf/FotoDatum).")
        if not comp['changed']:
            info.append("Die Liste ist aktuell – es gibt nichts zu speichern.")
        return "\n".join(info), "\n".join(warn), False

    def _ask_csv_save(self, plans, batch):
        """Speichern-Dialog für eine (Einzel) oder mehrere (Batch) Fotolisten.
        Zeigt je Liste Ziel, neue Einträge und Dopplungen; der Speicherort ist
        über »Speicherort ändern…« frei wählbar. Passt plans[i]['target'] und
        ['selected'] an und gibt merge_dups zurück – oder None bei Abbruch."""
        # Ein Dialog zu einem minimierten Hauptfenster bliebe unsichtbar (z.B.
        # wenn man während eines langen Batch-Laufs minimiert hat) – das
        # Programm wartet aber auf eine Antwort, also Hauptfenster hervorholen.
        if self.root.state() == 'iconic':
            self.root.deiconify()
        dlg = tk.Toplevel(self.root)
        dlg.title("Fotolisten speichern" if batch else "Fotoliste speichern")
        dlg.configure(bg=self.bg_color)
        dlg.transient(self.root)
        width = min(880, self.root.winfo_screenwidth() - 40)
        height = min(700, 250 + 180 * len(plans)) if batch else 400
        height = min(height, self.root.winfo_screenheight() - 120)  # Knöpfe sichtbar
        x = max(0, min(self.root.winfo_rootx() + 30, self.root.winfo_screenwidth() - width - 20))
        y = max(0, min(self.root.winfo_rooty() + 30,
                       self.root.winfo_screenheight() - height - 80))
        dlg.geometry(f"{width}x{height}+{x}+{y}")
        dlg.minsize(560, 300)
        merge_var = tk.BooleanVar(master=dlg, value=True)
        result = {'merge': None}
        lab = dict(bg=self.bg_color, fg=self.fg_color)
        chk = dict(bg=self.bg_color, fg=self.fg_color, selectcolor=self.entry_bg,
                   activebackground=self.bg_color, activeforeground=self.fg_color)
        colors = {0: self.fg_color,
                  1: "#ffaa33" if self.is_dark_mode else "#a04f00",
                  2: "#ff5555" if self.is_dark_mode else "#b00000"}

        intro = ("Folgende Fotolisten würden geschrieben – gespeichert werden nur die "
                 "angehakten." if batch else
                 "Bitte Speicherort prüfen – über »Speicherort ändern…« frei wählbar.")
        intro += ("\nJede Kombination aus Stelle und Position steht höchstens einmal in "
                  "der Liste. Vorhandene Einträge und Kommentare bleiben erhalten.")
        tk.Label(dlg, text=intro, justify="left", anchor="w", wraplength=width - 40,
                 **lab).pack(fill="x", padx=10, pady=(10, 4))

        bottom = tk.Frame(dlg, bg=self.bg_color)
        bottom.pack(side="bottom", fill="x", padx=10, pady=(4, 10))

        area = tk.Frame(dlg, bg=self.bg_color)
        area.pack(fill="both", expand=True, padx=10)
        canvas = tk.Canvas(area, bg=self.bg_color, highlightthickness=0)
        sbar = tk.Scrollbar(area, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=self.bg_color)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.configure(yscrollcommand=sbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        sbar.pack(side="right", fill="y")

        widgets = []

        def refresh_all():
            merge = merge_var.get()
            uses = {}
            for i, plan in enumerate(plans):
                plan['selected'] = widgets[i]['sel'].get() if batch else True
                if plan['selected']:
                    k = self._path_key(plan['target'])
                    uses[k] = uses.get(k, 0) + 1
            for i, plan in enumerate(plans):
                comp = self._compose_csv(plan, merge)
                plan['_comp'] = comp
                info, warn, is_error = self._describe_comp(plan, comp)
                if plan['selected'] and uses.get(self._path_key(plan['target']), 0) > 1:
                    warn = (warn + "\n" if warn else "") + (
                        "⚠ Eine andere angehakte Maßnahme schreibt in DIESELBE Datei – "
                        "bitte Speicherort ändern oder abwählen.")
                w = widgets[i]
                w['path'].set(plan['target'])
                w['entry'].xview_moveto(1.0)  # Dateiname sichtbar, nicht nur der Pfadanfang
                w['status'].config(text=info)
                w['warn'].config(text=warn, fg=colors[2 if is_error else 1])
                if warn:
                    w['warn'].grid()
                else:
                    w['warn'].grid_remove()

        def change(i):
            plan = plans[i]
            start = os.path.dirname(plan['target'])
            while start and not os.path.isdir(start) and os.path.dirname(start) != start:
                start = os.path.dirname(start)  # Vorschlagsordner existiert evtl. noch nicht
            fp = filedialog.asksaveasfilename(
                parent=dlg, title=f"Fotoliste {plan['label']} speichern unter",
                initialdir=start if start and os.path.isdir(start) else None,
                initialfile=os.path.basename(plan['target']),
                defaultextension=".csv", filetypes=[("CSV Dateien", "*.csv")],
                confirmoverwrite=False)  # vorhandene Liste wird ergänzt, nicht ersetzt
            if fp:
                plan['target'] = os.path.normpath(fp)
                plan['user_target'] = True
                if batch:
                    widgets[i]['sel'].set(True)  # neuer Ort gewählt = speichern gewollt
                refresh_all()

        def set_all(value):
            for w in widgets:
                w['sel'].set(value)
            refresh_all()

        def on_save():
            refresh_all()
            chosen = [p for p in plans if p['selected']]
            if not chosen:
                messagebox.showinfo("Nichts ausgewählt",
                                    "Es ist keine Fotoliste angehakt.", parent=dlg)
                return
            bad = [p for p in chosen if p['_comp']['error']]
            if bad:
                messagebox.showerror("Speichern nicht möglich", "\n".join(
                    f"{p['label']}: {p['_comp']['error']}" for p in bad), parent=dlg)
                return
            seen = {}
            for p in chosen:
                k = self._path_key(p['target'])
                if k in seen:
                    messagebox.showerror(
                        "Gleiche Zieldatei",
                        f"{seen[k]['label']} und {p['label']} würden in dieselbe Datei "
                        f"schreiben:\n{p['target']}\n\nBitte für eine davon einen anderen "
                        "Speicherort wählen oder sie abwählen.", parent=dlg)
                    return
                seen[k] = p
            for p in chosen:
                c, name = p['_comp'], os.path.basename(p['target'])
                if c['foreign'] and not messagebox.askyesno(
                        "Datei ersetzen?",
                        f"'{name}' ist keine Fotoliste (die Spalten StellenNr und PosNr "
                        f"fehlen).\n\nTrotzdem durch die Fotoliste {p['label']} ERSETZEN?\n"
                        f"(Eine Sicherung '{name}.bak' wird angelegt.)",
                        icon="warning", parent=dlg):
                    return
                if c['other_acts'] and not messagebox.askyesno(
                        "Andere Aktivität",
                        f"'{name}' enthält Einträge anderer Aktivität(en): "
                        + ", ".join(sorted(self._activity_label(a) for a in c['other_acts']))
                        + f"\n\nTrotzdem die Einträge von {p['label']} dort ergänzen?",
                        icon="warning", parent=dlg):
                    return
                if (c['target_exists'] and not c['foreign'] and not c['looks_foto']
                        and not messagebox.askyesno(
                            "Wirklich in diese Liste?",
                            f"'{name}' sieht nicht wie eine Fotoliste aus (keine Spalte "
                            f"Fotograf/FotoDatum).\n\nTrotzdem die Fotos von {p['label']} "
                            "dort eintragen?", icon="warning", parent=dlg)):
                    return
            result['merge'] = merge_var.get()
            dlg.destroy()

        for i, plan in enumerate(plans):
            fr = self._create_frame(inner, f" {plan['label']} ")
            fr.pack(fill="x", pady=3, padx=2)
            fr.columnconfigure(1, weight=1)
            sel = tk.BooleanVar(master=dlg, value=plan['selected'])
            if batch:
                tk.Checkbutton(fr, text="speichern", variable=sel, command=refresh_all,
                               **chk).grid(row=0, column=0, sticky="nw", padx=(0, 6))
            status = tk.Label(fr, justify="left", anchor="w", wraplength=width - 190, **lab)
            status.grid(row=0, column=1, columnspan=2, sticky="w")
            warn = tk.Label(fr, justify="left", anchor="w", wraplength=width - 190,
                            bg=self.bg_color, fg=colors[1])
            warn.grid(row=1, column=1, columnspan=2, sticky="w")
            path_var = tk.StringVar(master=dlg, value=plan['target'])
            entry = tk.Entry(fr, textvariable=path_var, state="readonly",
                             readonlybackground=self.entry_bg, fg=self.fg_color)
            entry.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(3, 1))
            tk.Button(fr, text="Speicherort ändern…", bg=self.btn_bg_highlight,
                      fg=self.fg_color, command=lambda i=i: change(i)
                      ).grid(row=2, column=2, padx=(6, 0), pady=(3, 1))
            widgets.append({'sel': sel, 'path': path_var, 'status': status, 'warn': warn,
                            'entry': entry})

        tk.Checkbutton(bottom, variable=merge_var, command=refresh_all,
                       text="Schon vorhandene doppelte Einträge verlustfrei zusammenführen "
                            "(nur wenn sich ihre Angaben nicht widersprechen)",
                       **chk).pack(anchor="w")
        btns = tk.Frame(bottom, bg=self.bg_color)
        btns.pack(fill="x", pady=(6, 0))
        if batch:
            tk.Button(btns, text="Alle anhaken", bg=self.btn_bg_highlight, fg=self.fg_color,
                      command=lambda: set_all(True)).pack(side="left")
            tk.Button(btns, text="Alle abwählen", bg=self.btn_bg_highlight, fg=self.fg_color,
                      command=lambda: set_all(False)).pack(side="left", padx=4)
        tk.Button(btns, text="Abbrechen", bg=self.btn_bg_highlight, fg=self.fg_color,
                  width=12, command=dlg.destroy).pack(side="right")
        save_btn = tk.Button(btns, text="Ausgewählte speichern" if batch else "Speichern",
                             bg="#00cc44", fg="#000000", font=('Helvetica', 9, 'bold'),
                             width=20, default="active", command=on_save)
        save_btn.pack(side="right", padx=6)

        refresh_all()
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        # Enter löst den Knopf mit dem Fokus aus (Abbrechen, Speicherort
        # ändern…, Haken); nur sonst gilt Enter als »Speichern«.
        dlg.bind("<Return>", lambda e: e.widget.invoke()
                 if isinstance(e.widget, (tk.Button, tk.Checkbutton)) else on_save())
        try:
            dlg.grab_set()
        except tk.TclError:
            pass
        save_btn.focus_set()
        self.root.wait_window(dlg)
        return result['merge']

    def _log_comp(self, plan, comp):
        """Dopplungen einer gespeicherten Liste ins Protokoll schreiben."""
        lab = plan['label']
        if comp['dup_lossless']:
            how = ("verlustfrei zusammengeführt" if comp['merge_dups']
                   else "NICHT zusammengeführt (abgewählt)")
            self.log(f"{lab}: {len(comp['dup_lossless'])} doppelte Einträge {how}: "
                     + ", ".join(f"{k[1]}-{k[2]}" for k, _ in comp['dup_lossless'][:40])
                     + (" …" if len(comp['dup_lossless']) > 40 else ""))
        for k, n, fields in comp['dup_conflicts'][:40]:
            self.log(f"   ⚠ {lab} Stelle {k[1]} / Pos. {k[2]}: {n}× mit abweichenden "
                     f"Angaben ({', '.join(self._field_label(f) for f in fields)}) – "
                     "bitte von Hand prüfen.")
        if len(comp['dup_conflicts']) > 40:
            self.log(f"   … und {len(comp['dup_conflicts']) - 40} weitere")
        for k, fields in comp['src_conflicts'][:40]:
            self.log(f"   ⚠ {lab} Stelle {k[1]} / Pos. {k[2]}: bisherige Liste weicht von "
                     f"der Zieldatei ab ({', '.join(self._field_label(f) for f in fields)}); "
                     "Angaben der Zieldatei behalten.")

    def _write_csv(self, plan, comp):
        """Schreibt die Fotoliste (cp1252, ';'). Vor JEDEM Überschreiben wird
        der bisherige Inhalt gesichert: als '.bak' neben der Liste und im
        Speicher für UNDO (so führt UNDO genau auf den Stand vor diesem
        Speichern zurück, samt zwischenzeitlicher Excel-Nachträge). Geschrieben
        wird über eine Zwischendatei: ein Fehler hinterlässt nie eine halbe
        Liste. Gibt (ok, Fehlertext) zurück."""
        out_path = plan['target']
        buf = io.StringIO(newline='')
        # Eine Excel-Zeile 'sep=,' oder 'sep=<Tab>' muss zum Trennzeichen
        # passen, mit dem jetzt geschrieben wird (';').
        buf.write(re.sub(r'^sep=.(?=\r?\n|\r|$)', 'sep=;', comp.get('preamble', ''),
                         flags=re.IGNORECASE))
        w = csv.writer(buf, delimiter=';', lineterminator='\r\n')
        w.writerow([self._field_label(f) for f in comp['fields']])
        for r in comp['rows']:
            w.writerow([r.get(f, '') for f in comp['fields']])
        data = buf.getvalue().encode('cp1252', errors='replace')

        mode, b_path, prev = 'new', None, None
        if os.path.exists(out_path):
            if not os.access(out_path, os.W_OK):
                self.log(f"Schreibgeschützt, nichts gespeichert: {out_path}")
                return False, (f"'{os.path.basename(out_path)}' ist schreibgeschützt "
                               "(Dateieigenschaften) – bitte Schreibschutz aufheben.")
            mode, b_path = 'overwrite', out_path + '.bak'
            try:
                with open(out_path, 'rb') as f:
                    prev = f.read()
                # Eine schreibgeschützte alte .bak darf das Sichern nicht blockieren;
                # copyfile übernimmt den Schreibschutz der Liste nicht mit.
                if os.path.exists(b_path) and not os.access(b_path, os.W_OK):
                    os.chmod(b_path, stat.S_IWRITE | stat.S_IREAD)
                shutil.copyfile(out_path, b_path)
            except Exception as e:
                self.log(f"Sicherung fehlgeschlagen, nichts gespeichert: {e}")
                if isinstance(e, PermissionError):
                    return False, (f"Sicherung '{os.path.basename(b_path)}' oder Liste "
                                   "gesperrt – vermutlich in Excel geöffnet. Bitte schließen "
                                   "und erneut versuchen.")
                return False, f"Sicherung fehlgeschlagen ({e})"
        tmp = out_path + '.tmp'
        try:
            os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, out_path)
        except Exception as e:
            try:
                os.remove(tmp)
            except Exception:
                pass
            self.log(f"Fehler beim Speichern von {out_path}: {e}")
            if isinstance(e, PermissionError):
                return False, ("Datei ist gesperrt – vermutlich in Excel geöffnet. "
                               "Bitte schließen und erneut versuchen.")
            return False, str(e)
        action = {'mode': mode, 'target': out_path, 'backup': b_path,
                  'prev': prev, 'written': data}
        self._remember_target(plan, action)
        self.last_update_actions.append(action)
        self.log(f"Gespeichert: {out_path}")
        return True, None

    def _csv_save_flow(self, data_list, batch, list_path=None, update=False):
        """Fotoliste(n) vorbereiten, im Speichern-Dialog bestätigen lassen und
        erst dann schreiben. Einzel: Der Dialog erscheint immer, der
        Speicherort ist wählbar. Batch: EIN Dialog für alle Maßnahmen; gibt es
        nirgends etwas zu ergänzen, entfällt er. update=True (Aktion 5): Ohne
        vorhandene Liste wird eine neue nur nach ausdrücklichem Haken angelegt.
        Gibt Ergebniszeilen für die Abschlussmeldung zurück."""
        notes, plans = [], []
        for d in data_list:
            plan = self._build_csv_plan(d, list_path=list_path)
            if plan is None:
                notes.append(f"{(d.get('raw_act') or '').strip() or '?'}: "
                             "Aktivität oder Ordner ungültig – übersprungen.")
                continue
            if not plan['fresh']:
                notes.append(f"{plan['label']}: keine passenden Fotos gefunden – "
                             "keine Liste geschrieben.")
                continue
            if update and not plan['source']:
                plan['selected'] = False
            plans.append(plan)

        def up_to_date_note(plan, comp):
            note = (f"{plan['label']}: Fotoliste ist aktuell – nichts zu ergänzen "
                    f"({os.path.basename(plan['target'])})")
            if comp['dup_conflicts']:
                note += (f", aber {self._n(len(comp['dup_conflicts']), 'widersprüchlicher Doppel-Eintrag', 'widersprüchliche Doppel-Einträge')}"
                         " – bitte von Hand prüfen (siehe Protokoll)")
            return note + "."

        if plans and batch:
            for plan in plans:
                plan['_comp'] = self._compose_csv(plan, True)
                if not plan['_comp']['changed']:
                    plan['selected'] = False
            if not any(p['_comp']['changed'] or p['_comp']['error'] for p in plans):
                for p in plans:
                    self._log_comp(p, p['_comp'])
                    notes.append(up_to_date_note(p, p['_comp']))
                plans = []

        if plans:
            merge = self._ask_csv_save(plans, batch)
            if merge is None:
                notes.append("Speichern abgebrochen – keine Fotoliste geschrieben.")
                plans = []
            for plan in plans:
                lab = plan['label']
                comp = self._compose_csv(plan, merge)
                name = os.path.basename(plan['target'])
                if comp['error']:
                    notes.append(f"{lab}: NICHT gespeichert – {comp['error']}")
                    continue
                if not comp['changed']:
                    self._log_comp(plan, comp)
                    self._remember_target(plan)  # selbst gewählte, aktuelle Liste merken
                    notes.append(up_to_date_note(plan, comp))
                    continue
                if not plan['selected']:
                    notes.append(f"{lab}: nicht gespeichert (nicht angehakt).")
                    continue
                self._log_comp(plan, comp)
                ok, err = self._write_csv(plan, comp)
                if not ok:
                    notes.append(f"{lab}: NICHT gespeichert – {err}")
                    continue
                extra = ""
                if comp['n_carried']:
                    extra += f", {self._n(comp['n_carried'], 'Eintrag', 'Einträge')} übernommen"
                if merge and comp['dup_lossless']:
                    extra += f", {len(comp['dup_lossless'])} Doppel-Einträge zusammengeführt"
                if comp['dup_conflicts']:
                    extra += (f", {len(comp['dup_conflicts'])} widersprüchliche "
                              "Doppel-Einträge bitte prüfen")
                notes.append(f"{lab}: {self._n(comp['n_new'], 'neuer Eintrag', 'neue Einträge')}"
                             f"{extra} → {name}")
        for n in notes:
            self.log(f"Fotoliste – {n}")
        return notes

    # --- UNDO, LOG & EXTRA ---
    def _remember_target(self, plan, action=None):
        """Über »Speicherort ändern…« gewählte Liste für diesen Quellordner
        merken (auch wenn sie schon aktuell war). UNDO stellt den vorigen
        Merk-Zustand wieder her; ohne Speichervorgang gibt es dafür einen
        eigenen UNDO-Eintrag."""
        if not plan.get('user_target'):
            return
        key = plan['pin_key']
        pin = (key, self._chosen_targets.get(key))
        self._chosen_targets[key] = plan['target']
        if action is not None:
            action['pin'] = pin
        else:
            self.last_update_actions.append({'mode': 'pin', 'target': plan['target'],
                                             'pin': pin})

    def _begin_undo_group(self):
        """Jede Aktion (1–5) ist ein UNDO-Schritt: Umbenennungen und
        gespeicherte Listen dieser Aktion landen in einer eigenen Gruppe."""
        grp = {'renames': {}, 'lists': []}
        self.undo_stack.append(grp)
        self.rename_history = grp['renames']
        self.last_update_actions = grp['lists']

    def undo_last_action(self):
        """Nimmt die LETZTE Aktion zurück (erneut drücken = die davor).
        Listen bekommen den Stand unmittelbar vor diesem Speichern zurück; wurde
        eine Liste seitdem verändert (z.B. in Excel), wird der jetzige Stand
        vorher als '<Datei>.vor-undo' gesichert. Gesperrte Dateien (in Excel
        geöffnet) werden gemeldet und bleiben für einen neuen Versuch vorgemerkt."""
        while self.undo_stack and not (self.undo_stack[-1]['renames']
                                       or self.undo_stack[-1]['lists']):
            self.undo_stack.pop()
        if not self.undo_stack:
            messagebox.showinfo("Undo", "Nichts zum Rückgängig machen.")
            return
        grp = self.undo_stack[-1]
        u_msg, fails = [], []

        def free_name(path, tag):
            """Freier Name neben path ('…tag', '…tag-2', …) – nie überschreiben."""
            stem, ext = os.path.splitext(path) if tag.startswith(' ') else (path, '')
            cand, n = f"{stem}{tag}{ext}", 2
            while os.path.exists(cand):
                cand, n = f"{stem}{tag}-{n}{ext}", n + 1
            return cand

        def restore_pin(a):
            if a.get('pin'):
                key, before = a['pin']
                if before is None:
                    self._chosen_targets.pop(key, None)
                else:
                    self._chosen_targets[key] = before

        for a in reversed(list(grp['lists'])):
            name = os.path.basename(a['target'])
            if a['mode'] == 'pin':  # nur ein gemerkter Speicherort
                restore_pin(a)
                grp['lists'].remove(a)
                u_msg.append(f"Gemerkter Speicherort '{name}' vergessen.")
                continue
            tmp = a['target'] + '.tmp'
            keep_tmp = None
            try:
                cur = None
                if os.path.exists(a['target']):
                    with open(a['target'], 'rb') as f:
                        cur = f.read()
                if cur is not None and cur != a['written']:
                    # Fremdänderung erst vorläufig sichern; endgültig erst, wenn
                    # das Zurücksetzen geklappt hat (sonst bei jedem Versuch eine
                    # weitere Kopie)
                    keep_tmp = free_name(a['target'], '.vor-undo.tmp')
                    with open(keep_tmp, 'wb') as f:
                        f.write(cur)
                if a['mode'] == 'new':
                    if cur is not None:
                        os.remove(a['target'])
                    done = f"Erstellte Datei '{name}' gelöscht."
                else:
                    with open(tmp, 'wb') as f:
                        f.write(a['prev'])
                    os.replace(tmp, a['target'])
                    done = f"'{name}' auf den Stand vor dem Speichern zurückgesetzt."
                if keep_tmp:
                    keep = free_name(a['target'], '.vor-undo')
                    os.replace(keep_tmp, keep)
                    keep_tmp = None
                    u_msg.append(f"'{name}' wurde nach dem Speichern verändert – dieser "
                                 f"Stand ist gesichert als '{os.path.basename(keep)}'.")
                u_msg.append(done)
                restore_pin(a)
                grp['lists'].remove(a)
            except OSError as e:
                fails.append(f"'{name}': {e}" + (
                    " – vermutlich in Excel geöffnet; bitte schließen und UNDO erneut drücken."
                    if isinstance(e, PermissionError) else ""))
            finally:
                for leftover in (tmp, keep_tmp):
                    if leftover and os.path.exists(leftover):
                        try:
                            os.remove(leftover)
                        except OSError:
                            pass

        u_c, missing = 0, 0
        for t, s in reversed(list(grp['renames'].items())):
            try:
                if not os.path.exists(t):
                    missing += 1  # inzwischen verschoben/gelöscht – nichts zurückzusetzen
                else:
                    os.makedirs(os.path.dirname(s), exist_ok=True)
                    dest = s
                    if os.path.exists(s):
                        # Unter dem alten Namen liegt inzwischen eine ANDERE Datei
                        # (z.B. ein neues Foto '5-10.jpg') – nie überschreiben.
                        dest = free_name(s, ' (UNDO)')
                        u_msg.append(f"'{os.path.basename(s)}' war schon wieder belegt – "
                                     f"zurückgelegt als '{os.path.basename(dest)}'.")
                    shutil.move(t, dest)
                    u_c += 1
                del grp['renames'][t]
            except OSError as e:
                fails.append(f"'{os.path.basename(t)}': {e}")
        if u_c > 0:
            u_msg.append(f"{u_c} Dateien in Ursprungszustand versetzt.")
        if missing:
            u_msg.append(f"{self._n(missing, 'Foto war', 'Fotos waren')} nicht mehr am "
                         "erwarteten Ort (inzwischen verschoben oder gelöscht) – "
                         "nicht zurückgesetzt.")
        if not grp['lists'] and not grp['renames']:
            self.undo_stack.pop()

        if u_msg:
            msg = "Undo ausgeführt:\n- " + "\n- ".join(u_msg)
        elif fails:
            msg = "Undo NICHT ausgeführt."
        else:
            msg = "Undo: Es gab nichts mehr zurückzusetzen."
        if fails:
            msg += "\n\nNicht möglich:\n- " + "\n- ".join(fails)
        self.log(msg)
        (messagebox.showwarning if fails else messagebox.showinfo)("Undo", msg)

    def log(self, m):
        self.txt_log.insert(tk.END, m + "\n")
        self.txt_log.see(tk.END)
        self.root.update_idletasks()

    def open_paypal(self):
        webbrowser.open("https://paypal.me/PeMeurer")

    def show_readme_popup(self):
        p = tk.Toplevel(self.root)
        p.title("Anleitung")
        p.geometry("720x580")
        p.configure(bg=self.bg_color)
        t = scrolledtext.ScrolledText(p, wrap="word", font=('Courier New', 10),
                                      bg=self.entry_bg, fg=self.fg_color,
                                      insertbackground=self.fg_color)
        t.pack(fill="both", expand=True, padx=10, pady=10)
        t.insert(tk.END, README_TEXT)
        t.config(state="disabled")

    def show_license_popup(self):
        p = tk.Toplevel(self.root)
        p.title("Lizenz")
        p.geometry("580x400")
        p.configure(bg=self.bg_color)
        t = scrolledtext.ScrolledText(p, wrap="word", font=('Helvetica', 10),
                                      bg=self.entry_bg, fg=self.fg_color,
                                      insertbackground=self.fg_color)
        t.pack(fill="both", expand=True, padx=15, pady=15)
        t.insert(tk.END, LICENSE_TEXT)
        t.config(state="disabled")


# --- LIZENZTEXT ---
LICENSE_TEXT = """© 2026 Peter Meurer

OpenSource Software (GNU GPL v3)
Keine Gewährleistung – Nutzung auf eigene Verantwortung.
Dieses Programm ist freie Software: Sie können es unter den Bedingungen der GNU General Public License Version 3 (GPLv3) weitergeben und/oder verändern.

Dieses Programm wird in der Hoffnung bereitgestellt, dass es nützlich ist, aber OHNE JEDE GEWÄHRLEISTUNG, sogar ohne die implizite Gewährleistung der MARKTREIFE oder EIGNUNG FÜR EINEN BESTIMMTEN ZWECK.

Die Nutzung erfolgt auf eigene Verantwortung. Der Autor übernimmt keine Haftung für Schäden, Datenverluste oder Fehlinterpretationen der Ergebnisse.

Unterstützung und Weiterentwicklung sind willkommen."""

# --- DOKUMENTATIONSTEXT ---
README_TEXT = """===================================================================
                  GRABUNGSTAUGLICH - DOKUMENTATION & HILFE
===================================================================

Dieses Tool automatisiert das zeitaufwendige Umbenennen, Organisieren
und Katalogisieren von Grabungsfotos nach den üblichen
Dokumentationsvorgaben (WNK-Format / Dokuprüfer).

-------------------------------------------------------------------
0. Kurzanleitung (Einzel- & Batch-Modus)
-------------------------------------------------------------------
1. Projektordner: Benenne die Rohfotos nach Stelle-Position (z.B. 67-3, 67_3).
   Das Tool ist dabei extrem fehlertolerant: Auch wenn versehentlich mehrere
   Leerzeichen, Bindestriche oder Unterstriche zwischen die Zahlen rutschen
   (z.B. "3     15", "4__20" oder "6------3"), wird dies automatisch korrigiert.
2. Einzel-Modus: Wähle den Quell-Ordner. Aktivität wird autovervollständigt.
3. Batch-Modus: Wähle einen Master-Ordner. Das Programm findet automatisch
   alle Maßnahmen (Ordner mit z.B. OV_2022_1023... im Namen). Für jeden Ordner
   können individuelle Fotografen vergeben werden.
4. Zielordner: Alle fertigen Bilder landen einheitlich in 'Aktivität_Fotos'
   (z.B. OV_2021_1034_Fotos).
5. Aktionen: Wähle die passende Aktion. Bevor eine Fotoliste gespeichert wird,
   erscheint immer der Speichern-Dialog: im Einzel-Modus mit frei wählbarem
   Speicherort, im Batch-Modus als Übersicht aller Maßnahmen zum Abhaken.
   Jede Kombination aus Stelle und Position steht nur EINMAL in der Liste,
   auch wenn man denselben Ordner mehrfach bearbeitet.

Viel Erfolg! --Peter

Es folgt die detaillierte Anleitung:

-------------------------------------------------------------------
1. VORBEREITUNG DER FOTOS (Eigene Vorarbeit)
-------------------------------------------------------------------
Das Tool filtert standardmäßige Kameranamen (wie 'IMG_0412.jpg') aus.
Damit das Programm greift, musst du die relevanten Rohfotos vorab
lediglich in "Stelle-Position" umbenennen. Erlaubte Trenner sind
Leerzeichen, Bindestriche oder Unterstriche.

Zulässige Formate für Rohfotos:
  '4-5.jpg' -> Wird zu: 'AKTIVITÄT_0004_005.jpg'
  '120_2.jpg' -> Wird zu: 'AKTIVITÄT_0120_002.jpg'
  '3     15.jpg' -> Wird zu: 'AKTIVITÄT_0003_015.jpg'
  '4__20.jpg' -> Wird zu: 'AKTIVITÄT_0004_020.jpg'

Einschränkung: Stellennummer max. 4-stellig, Positionsnummer max. 3-stellig.
Nur .jpg/.jpeg-Dateien werden verarbeitet.

-------------------------------------------------------------------
2. FLEXIBLE AKTIVITÄTSEINGABE & FILTER
-------------------------------------------------------------------
Das Feld 'Aktivität' verzeiht fast jede Schreibweise. Sobald du einen
Quell-Ordner auswählst, versucht das Programm zudem die Aktivität aus
dem Ordnernamen oder benachbarten Ordnern abzuleiten. Dies funktioniert
im Einzel- wie im Batch-Modus.

[Option: Tolerieren: EXIF-Datum älter als Aktivitätsjahr]
  Standardmäßig blockiert das Tool Fotos, deren Aufnahmedatum VOR dem
  Grabungsjahr liegt. Wenn die Kamera sich jedoch auf Werkseinstellungen
  zurückgesetzt hat, kannst du diese Sperre aufheben. Das Programm benennt
  die Bilder um, lässt das Datum in der CSV aber leer.

-------------------------------------------------------------------
3. FOTOGRAFEN*INNEN-KASKADE (Zuordnung für CSV)
-------------------------------------------------------------------
  * Hauptfotograf*in: Trage hier den Namen ein, der standardmäßig für JEDES
    Foto in die CSV geschrieben werden soll.
  * Weitere Fotograf*innen: Wenn bestimmte Fotos von jemand anderem
    gemacht wurden, trage den Namen links ein und rechts die Fundnummern
    als 'Stelle-Position' (z.B. 3-14, 6-20). Dies überschreibt den Haupteintrag.

-------------------------------------------------------------------
4. ERKLÄRUNG DER BUTTONS / FUNKTIONEN
-------------------------------------------------------------------
[1. Umbenennen, Foto-Abgabeordner und Fotoliste erstellen]
  Benennt Rohfotos um, schiebt alles in den Abgabeordner und erstellt die CSV.
  Existiert bereits eine Fotoliste, werden nur fehlende Einträge ergänzt
  (Kommentare bleiben erhalten). Bereits verarbeitete Fotos werden nicht
  erneut angefasst. Gespeichert wird erst nach dem Speichern-Dialog (4a).

[2. Nur umbenennen!]
  Sucht nach Roh-Mustern ('4-5.jpg') und benennt diese vor Ort um.

[3. Umbenannte Fotos aufspüren, verschieben, Fotoliste erstellen]
  Greift sich fertige Namen im WNK-Format (z. B. "OV_2022_1082_0023_004"),
  verschiebt und katalogisiert sie.

[4. Nur Fotoliste erstellen]
  Erzeugt die CSV-Liste aus den gefundenen Bildern, OHNE Dateien umzubenennen.
  Existiert bereits eine Fotoliste, werden nur fehlende Einträge ergänzt.

[5. Vorhandene Digitalbildliste aktualisieren]
  Wähle im Einzelmodus eine bestehende CSV im Explorer aus (vorgeschlagen wird
  die automatisch gefundene). Das Programm ergänzt neue Fotos; alle
  vorhandenen Einträge und Kommentare bleiben erhalten. Im Speichern-Dialog
  bestimmst du danach, wohin gespeichert wird. Im Batch-Modus sucht das
  Programm die Listen aller Maßnahmen selbst und zeigt sie gesammelt zur
  Bestätigung an; Maßnahmen ohne vorhandene Liste werden nur neu angelegt,
  wenn du sie anhakst.

[Letzte Aktion rückgängig machen (UNDO)]
  Nimmt die jeweils LETZTE Aktion zurück (erneut klicken = die davor):
  Dateibewegungen werden rückgängig gemacht, neu angelegte Listen gelöscht,
  ergänzte Listen bekommen den Stand unmittelbar vor dieser Aktion zurück –
  inklusive Nachträgen, die du vorher in Excel gemacht hast. Wurde eine Liste
  NACH dem Speichern noch verändert, wird dieser Stand vorher als
  '<Liste>.vor-undo' gesichert (bei mehreren '.vor-undo-2' usw. – nie
  überschrieben). Liegt unter dem alten Rohnamen inzwischen ein ANDERES Foto,
  wird das zurückgeholte als '… (UNDO).jpg' daneben gelegt – es wird nichts
  überschrieben. Ist eine Liste in Excel geöffnet, meldet das Programm das;
  nach dem Schließen UNDO einfach erneut drücken.
  Zusätzlich liegt nach jedem Ergänzen eine Sicherheitskopie (.bak) neben
  der Liste.

-------------------------------------------------------------------
4a. FOTOLISTE SPEICHERN & DOPPELTE EINTRÄGE
-------------------------------------------------------------------
  * Jede Kombination aus Aktivität, Stelle und Position steht höchstens
    EINMAL in der Fotoliste. Gibt es mehrere Fotos derselben Stelle/Position
    (z.B. ..._0005_010.jpg und ..._0005_010_A.jpg, oder ein liegengebliebenes
    Rohfoto '5-10.jpg' neben der umbenannten Kopie), entsteht nur ein Eintrag.
    Welche Fotos betroffen sind, steht im Protokoll.
  * Wird derselbe Ordner erneut bearbeitet, kommen nur Stellen/Positionen
    hinzu, die in der Liste noch fehlen.
  * Unterordner im fertigen Fotoordner (z.B. '..._Fotos/aussortiert') werden
    weder verschoben noch in die Liste aufgenommen. Ein Rohfoto, das direkt
    im fertigen Fotoordner liegt, wird dort umbenannt.
  * Enthält eine vorhandene Liste schon doppelte Einträge (z.B. aus älteren
    Programmversionen), werden sie auf Wunsch verlustfrei zusammengeführt:
    leere Felder werden aus dem Doppel aufgefüllt. Widersprechen sich die
    Angaben (z.B. zwei verschiedene Kommentare), bleiben beide Zeilen stehen
    und werden im Dialog und im Protokoll zum Prüfen genannt.
  * Speichern-Dialog: zeigt Zieldatei, Zahl der neuen Einträge und gefundene
    Dopplungen. Über »Speicherort ändern…« lässt sich jede Liste woanders
    speichern. Wählst du eine vorhandene Fotoliste als Ziel, wird sie
    ergänzt, nicht ersetzt. Vor jedem Überschreiben wird eine Sicherung
    (.bak) angelegt.
  * Batch-Modus: EIN Dialog für alle Maßnahmen, jede einzeln abhakbar.
    Würden zwei Maßnahmen in dieselbe Datei schreiben, wird das angezeigt
    und das Speichern verhindert, bis es aufgelöst ist. Ist nirgends etwas
    zu ergänzen, erscheint kein Dialog.
  * Batch-Modus, mehrere Ordner je Maßnahme: Der Block zeigt die
    zusätzlich gefundenen Ordner einzeln zum Abwählen an. Eindeutige Kopien
    ('… - Kopie', '(2)', 'Backup', oder ein anderer Ordner der Maßnahme mit
    angehängtem '_alt'/'_Sicherung') sind vorab abgewählt – ihre Fotos würden
    sonst als _A-Dubletten umbenannt. Ortsnamen wie 'Morschenich-Alt' oder
    'Hangsicherung' gelten nicht als Kopie. Abgewählte Ordner nennt die
    Abschlussmeldung mit der Zahl ihrer Fotos.
  * Die vorhandene Liste wird im Ordner der Maßnahme bis drei Ebenen tief
    gesucht (z.B. Abgabe/..._Stellenkatalog_und_Listen/), ebenso in
    Nachbarordnern derselben Maßnahme (z.B. '..._Abgabe' neben dem
    Rohfoto-Ordner). Fund-, SfM- (auch 'SfM-Fotoliste'), Zeichnungs- oder
    Stellenlisten und fremde leere Vorlagen werden nie als Fotoliste
    genommen, Kopien ('... - Kopie.csv', 'NEU_...', Ordner 'Sicherung') nur,
    wenn es keine bessere gibt. Wurde in dieser Sitzung an einem selbst
    gewählten Ort gespeichert, wird diese Liste weitergeführt.
  * Vorhandene Listen werden verlustfrei gelesen: Excel-Zeile 'sep=;' und
    Titelzeilen über der Kopfzeile, doppelte oder leere Spaltennamen, eigene
    Zusatzspalten, ';' im Kommentar ohne Anführungszeichen, UTF-8 und
    Tausenderpunkte ('1.000') bleiben erhalten bzw. werden richtig erkannt.
    Notiz- und Trennzeilen ohne Nummer bleiben an ihrem Platz.

-------------------------------------------------------------------
5. ENTWICKLER-TIPPS (Code-Anpassungen)
-------------------------------------------------------------------
[Standard-Theme (Dark/Light Mode) ändern]
  Das Programm startet standardmäßig im Dark Mode. Um stattdessen den Light
  Mode als Standard festzulegen, öffne das Skript in einem Texteditor und
  suche ganz oben (ca. Zeile 18) nach 'self.is_dark_mode = True'.
  Ändere das 'True' einfach zu 'False' (großes F!).
==================================================================="""

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = PhotoRenamerApp(root)
        root.mainloop()
    except Exception as e:
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        with open(os.path.join(desktop_path, "GRABUNGSTAUGLICH_CRASHLOG.txt"), "w") as f:
            f.write(traceback.format_exc())
