import os
import re
import csv
import shutil
import webbrowser
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from datetime import datetime


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
                           pady=2, command=self.action_full_process)
        btn_g1._custom_color = True
        btn_g1.grid(row=0, column=0, padx=3, pady=1)

        tk.Button(inner_g, text="2. Nur umbenennen", width=_GW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 9), pady=2,
                  command=self.action_rename_only
                  ).grid(row=0, column=1, padx=3, pady=1)

        tk.Button(inner_g, text="3. Aufspüren + Liste", width=_GW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 9), pady=2,
                  command=self.action_gather_and_csv
                  ).grid(row=0, column=2, padx=3, pady=1)

        tk.Button(inner_g, text="4. Nur Fotoliste", width=_GW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 9), pady=2,
                  command=self.action_csv_only
                  ).grid(row=1, column=0, padx=3, pady=1)

        btn_g5 = tk.Button(inner_g, text="5. Fotoliste aktualisieren", width=_GW,
                           bg="#4287f5", fg="#ffffff", font=('Helvetica', 9, 'bold'),
                           pady=2, command=self.action_update_csv)
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
            relief="raised", pady=3, command=self.action_full_process)
        btn_full._custom_color = True
        btn_full.grid(row=0, column=0, columnspan=2, padx=2, pady=(2, 3), sticky="ew")

        # Rows 1-2: 2-column layout
        tk.Button(
            frame_actions, text="2. Nur umbenennen",
            bg=self.btn_bg_highlight, fg=self.fg_color, pady=2,
            command=self.action_rename_only
        ).grid(row=1, column=0, padx=2, pady=1, sticky="ew")

        tk.Button(
            frame_actions, text="3. Fotos aufspüren, verschieben & Liste",
            bg=self.btn_bg_highlight, fg=self.fg_color, pady=2,
            command=self.action_gather_and_csv
        ).grid(row=1, column=1, padx=2, pady=1, sticky="ew")

        tk.Button(
            frame_actions, text="4. Nur Fotoliste erstellen",
            bg=self.btn_bg_highlight, fg=self.fg_color, pady=2,
            command=self.action_csv_only
        ).grid(row=2, column=0, padx=2, pady=1, sticky="ew")

        btn_update = tk.Button(
            frame_actions, text="5. Fotoliste aktualisieren",
            bg="#4287f5", fg="#ffffff", font=('Helvetica', 9, 'bold'),
            pady=2, command=self.action_update_csv)
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
        return [{
            'raw_act': self.ent_activity_einzel.get(),
            'base_dir': self.ent_dir_einzel.get(),
            'filter_raw': self.ent_filter_stellen_einzel.get(),
            'ignore_old_exif': self.var_ignore_exif_einzel.get(),
            'main_photo': self.ent_main_photo_einzel.get().strip(),
            'photo_mapping': self.build_photo_mapping(
                self.ent_main_photo_einzel.get(),
                self.additional_photographers_entries_einzel)
        }]

    def get_batch_data(self):
        data_list = []
        for block in self.batch_blocks:
            data_list.append({
                'raw_act': block['ent_activity'].get(),
                'base_dir': block['base_dir'],
                'extra_dirs': block.get('extra_dirs', []),
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
                    # Primary folder: prefer one ending in _Abgabe, else first alphabetically
                    primary = next(
                        (d for d in dirs
                         if os.path.basename(d).lower().endswith('_abgabe')),
                        dirs[0])
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
                'extra_dirs': block['extra_dirs'],
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
                         command=lambda: self.action_full_process([_block_data()]))
        btn1._custom_color = True
        btn1.grid(row=0, column=0, padx=2, pady=1)

        tk.Button(btn_frame, text="2. Nur umbenennen", width=_BW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 8), pady=1,
                  command=lambda: self.action_rename_only([_block_data()])
                  ).grid(row=0, column=1, padx=2, pady=1)

        tk.Button(btn_frame, text="3. Aufspüren + Liste", width=_BW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 8), pady=1,
                  command=lambda: self.action_gather_and_csv([_block_data()])
                  ).grid(row=0, column=2, padx=2, pady=1)

        tk.Button(btn_frame, text="4. Nur Fotoliste", width=_BW,
                  bg=self.btn_bg_highlight, fg=self.fg_color,
                  font=('Helvetica', 8), pady=1,
                  command=lambda: self.action_csv_only([_block_data()])
                  ).grid(row=1, column=0, padx=2, pady=1)

        btn5 = tk.Button(btn_frame, text="5. Fotoliste aktualisieren", width=_BW,
                         bg="#4287f5", fg="#ffffff", font=('Helvetica', 8, 'bold'), pady=1,
                         command=lambda: self.action_update_csv([_block_data()]))
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
    def _get_active_data(self):
        idx = self.notebook.index(self.notebook.select())
        if idx == 0:
            return self.get_einzel_data()
        elif idx == 1:
            return self.get_batch_data()
        return []

    def action_full_process(self, data_list=None):
        if data_list is None:
            data_list = self._get_active_data()
        if not data_list:
            return messagebox.showwarning("Achtung", "Keine Daten vorhanden.")
        t_r, t_m = 0, 0
        for d in data_list:
            res = self._core_process_photos("rename_and_move", **d)
            if res:
                t_r += res[0]
                t_m += res[1]
            self._core_create_wnk_csv(silent=True, **d)
        messagebox.showinfo("Aktion 1 beendet",
                            f"Vorgang für {len(data_list)} Ordner abgeschlossen.\n\n"
                            f"Neu umbenannt: {t_r}\nBereits fertige verschoben: {t_m}")

    def action_rename_only(self, data_list=None):
        if data_list is None:
            data_list = self._get_active_data()
        if not data_list:
            return
        t_r = sum((self._core_process_photos("rename_only", **d) or (0, 0))[0]
                  for d in data_list)
        messagebox.showinfo("Aktion 2 beendet",
                            f"Nur Umbenennen abgeschlossen!\n\nNeu umbenannt: {t_r} Fotos.")

    def action_gather_and_csv(self, data_list=None):
        if data_list is None:
            data_list = self._get_active_data()
        if not data_list:
            return
        t_m = 0
        for d in data_list:
            m = self._core_move_to_existing(**d)
            if m is not None:
                t_m += m
            self._core_create_wnk_csv(silent=True, **d)
        messagebox.showinfo("Aktion 3 beendet",
                            f"Aufspüren & Listen erstellt!\n\n"
                            f"Fotos in Abgabeordner verschoben: {t_m}")

    def action_csv_only(self, data_list=None):
        if data_list is None:
            data_list = self._get_active_data()
        for d in data_list:
            self._core_create_wnk_csv(silent=False, **d)

    def action_update_csv(self, data_list=None):
        if data_list is not None:
            # Per-block call from batch block button: auto-find CSV
            for d in data_list:
                prefix, year, proj_str = self.parse_activity(d['raw_act'])
                if not prefix:
                    continue
                act_norm = f"{prefix}_{year}_{proj_str}"
                exp_csv = self._find_existing_csv(
                    d['base_dir'], act_norm,
                    extra_dirs=d.get('extra_dirs', []))
                if exp_csv and os.path.exists(exp_csv):
                    self._core_update_csv_logic(exp_csv, **d)
                else:
                    self.log(f"Keine Fotoliste gefunden für {act_norm}.")
            messagebox.showinfo("Fotoliste aktualisiert", "Abgeschlossen.")
            return
        # Global call from Einzel-Modus action frame
        idx = self.notebook.index(self.notebook.select())
        if idx == 0:
            fp = filedialog.askopenfilename(
                title="Vorhandene Fotoliste auswählen",
                filetypes=[("CSV Dateien", "*.csv")])
            if fp:
                self._core_update_csv_logic(fp, **self.get_einzel_data()[0])
        elif idx == 1:
            for d in self.get_batch_data():
                prefix, year, proj_str = self.parse_activity(d['raw_act'])
                if not prefix:
                    continue
                act_norm = f"{prefix}_{year}_{proj_str}"
                exp_csv = self._find_existing_csv(
                    d['base_dir'], act_norm,
                    extra_dirs=d.get('extra_dirs', []))
                if exp_csv and os.path.exists(exp_csv):
                    self._core_update_csv_logic(exp_csv, **d)
                else:
                    self.log(f"Batch-Update übersprungen: Keine Fotoliste gefunden für {act_norm}.")
            messagebox.showinfo("Batch Update", "Batch-Aktualisierung abgeschlossen.")

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

    def get_output_folder_path(self, base_dir, activity_str):
        # If a matching _Fotos subdirectory already exists INSIDE base_dir, use that.
        # This handles structures like OV_2026_1014_Abgabe/OV_2026_1014_Fotos/.
        inner = os.path.join(base_dir, f"{activity_str}_Fotos")
        if os.path.isdir(inner):
            return inner
        return os.path.join(os.path.dirname(base_dir), f"{activity_str}_Fotos")

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

    def gather_all_photos(self, base_dir, skip_dir_names=None):
        """Walk base_dir recursively, optionally skipping subdirs by name."""
        skip_lower = {s.lower() for s in (skip_dir_names or [])}
        result = []
        for root, dirs, files in os.walk(base_dir):
            # Prune directories to skip (modifying dirs in-place stops os.walk from descending)
            dirs[:] = [d for d in dirs if d.lower() not in skip_lower]
            for f in files:
                if f.lower().endswith(('.jpg', '.jpeg')):
                    result.append(os.path.join(root, f))
        return result

    def _get_default_csv_path(self, base_dir, act_norm):
        """Default path for a newly created Fotoliste.

        Abgabe-type structure (base_dir contains an inner _Fotos subfolder):
          → put CSV inside base_dir under an existing *Stellenkatalog*/*Listen* subdir,
            or create {act_norm}_Stellenkatalog_und_Listen/ if none exists yet.
        Simple structure or standalone _Fotos folder:
          → put CSV next to base_dir (sibling).
        """
        t_dir = self.get_output_folder_path(base_dir, act_norm)
        # Abgabe-type: t_dir is a direct child of base_dir
        if os.path.abspath(os.path.dirname(t_dir)) == os.path.abspath(base_dir):
            # Look for an existing *Stellenkatalog* or *Listen* subdirectory
            try:
                for item in sorted(os.listdir(base_dir)):
                    sub = os.path.join(base_dir, item)
                    if os.path.isdir(sub):
                        lc = item.lower()
                        if 'stellenkatalog' in lc or 'listen' in lc:
                            return os.path.join(sub, f"{act_norm}_Fotoliste.csv")
            except Exception:
                pass
            # None found — use standard name (will be created on save)
            return os.path.join(base_dir,
                                f"{act_norm}_Stellenkatalog_und_Listen",
                                f"{act_norm}_Fotoliste.csv")
        # Simple structure: sibling of base_dir
        return os.path.join(os.path.dirname(base_dir), f"{act_norm}_Fotoliste.csv")

    def _find_existing_csv(self, base_dir, act_norm, extra_dirs=None):
        """Search for an existing compatible Fotoliste CSV.

        Searches base_dir, its parent, all their immediate subdirs, and any
        extra_dirs (merged sibling folders for the same activity) + their subdirs.
        """
        parts = act_norm.split('_')
        act_wnk = (f"{parts[0]} {parts[1]}/{int(parts[2])}"
                   if len(parts) == 3 else act_norm)

        parent = os.path.dirname(base_dir)

        dirs_to_search: list[str] = []
        for root in [base_dir, parent] + list(extra_dirs or []):
            if os.path.isdir(root) and root not in dirs_to_search:
                dirs_to_search.append(root)
                try:
                    for item in os.listdir(root):
                        sub = os.path.join(root, item)
                        if os.path.isdir(sub) and sub not in dirs_to_search:
                            dirs_to_search.append(sub)
                except Exception:
                    pass

        # Two passes: first prefer files whose name contains act_norm
        for priority_filter in [True, False]:
            for d in dirs_to_search:
                try:
                    for f in sorted(os.listdir(d)):
                        if not f.lower().endswith('.csv'):
                            continue
                        if priority_filter and act_norm.lower() not in f.lower():
                            continue
                        fp = os.path.join(d, f)
                        if not self._csv_is_compatible(fp):
                            continue
                        match = self._csv_activity_matches(fp, act_wnk)
                        if match is True or match is None:
                            return fp
                        # match is False: structure fits but activity differs — warn and skip
                        self.log(f"⚠ CSV übersprungen (andere Aktivität?): "
                                 f"{os.path.relpath(fp, parent)}")
                except Exception:
                    pass
        return None

    @staticmethod
    def _normalize_activity(s):
        """Strip separators and uppercase for comparison.
        Leading zeros in numbers are intentionally preserved:
        'OV 2026/0014' and 'OV 2026/14' are NOT the same activity."""
        return re.sub(r'[\s_/\-]+', '', s).upper()

    def _csv_is_compatible(self, csv_path):
        """Check that the CSV has at least StellenNr and PosNr columns."""
        try:
            with open(csv_path, 'r', encoding='cp1252', errors='replace') as f:
                headers = set(csv.DictReader(f, delimiter=';').fieldnames or [])
            return {'StellenNr', 'PosNr'}.issubset(headers)
        except Exception:
            return False

    def _csv_activity_matches(self, csv_path, act_wnk):
        """Read the first data row and compare the Aktivitaet field to act_wnk.
        Returns True  = match
                False = mismatch (warn the caller — could be a different activity)
                None  = no data rows yet (empty CSV; accept it)
        """
        try:
            with open(csv_path, 'r', encoding='cp1252', errors='replace') as f:
                for row in csv.DictReader(f, delimiter=';'):
                    val = row.get('Aktivitaet', '').strip()
                    if val:
                        return (self._normalize_activity(val)
                                == self._normalize_activity(act_wnk))
            return None  # header-only CSV
        except Exception:
            return None

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
        t_dir = (self.get_output_folder_path(base_dir, act_norm)
                 if mode == "rename_and_move" else base_dir)
        if mode == "rename_and_move" and not os.path.exists(t_dir):
            os.makedirs(t_dir)

        # Collect photos from primary dir + all extra (merged) dirs
        fotos_folder = f"{act_norm}_Fotos"
        all_f = list(self.gather_all_photos(base_dir, skip_dir_names=[fotos_folder]))
        for xd in (extra_dirs or []):
            if os.path.isdir(xd):
                all_f += self.gather_all_photos(xd, skip_dir_names=[fotos_folder])
        all_f = list(set(all_f))
        r_c, m_c = 0, 0
        # When the source folder IS already the _Fotos folder (standalone case),
        # base_dir == t_dir → don't apply the "already in target" skip
        base_is_target = os.path.abspath(base_dir) == os.path.abspath(t_dir)

        for fp in all_f:
            if (mode == "rename_and_move" and not base_is_target and
                    os.path.abspath(os.path.dirname(fp)) == os.path.abspath(t_dir)):
                continue
            fn = os.path.basename(fp)
            parsed = self.parse_photo_name(fn)

            if parsed:
                st, pos = parsed
                if allowed and st not in allowed:
                    continue
                ed = self.get_exif_date_pure(fp)
                if ed and ed.year < y and not ignore_old_exif:
                    self.log(f"   [X] Ignoriert: {fn} (Jahr vor Grabung).")
                    continue
                final_fn = self.get_unique_filename(
                    t_dir, f"{act_norm}_{st}_{pos}",
                    os.path.splitext(fn)[1].lower(), source_filepath=fp)
                if final_fn is None:
                    self.log(f"   [-] Übersprungen: '{fn}' identisch vorhanden.")
                    continue
                f_path = os.path.join(t_dir, final_fn)
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
        t_dir = self.get_output_folder_path(base_dir, act_norm)
        if not os.path.exists(t_dir):
            os.makedirs(t_dir)
        allowed = ([f"{int(x.strip()):04d}" for x in filter_raw.split(",")
                    if x.strip().isdigit()] if filter_raw.strip() else None)
        fotos_folder = f"{act_norm}_Fotos"
        all_photos = list(self.gather_all_photos(base_dir, skip_dir_names=[fotos_folder]))
        for xd in (extra_dirs or []):
            if os.path.isdir(xd):
                all_photos += self.gather_all_photos(xd, skip_dir_names=[fotos_folder])
        m_c = 0
        for fp in list(set(all_photos)):
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
                             p_map, main_p, search_dirs):
        all_f = list(set([f for d in search_dirs
                          if os.path.exists(d)
                          for f in self.gather_all_photos(d)]))
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
                    "_sort_pos": p_int
                })
        return rows

    def _core_create_wnk_csv(self, silent=False, raw_act="", base_dir="", filter_raw="",
                             ignore_old_exif=False, main_photo="", photo_mapping=None,
                             extra_dirs=None, **kwargs):
        if photo_mapping is None:
            photo_mapping = {}
        p, y, pr = self.parse_activity(raw_act)
        if not p or not os.path.isdir(base_dir):
            return None
        act_norm, act_wnk = f"{p}_{y}_{pr}", f"{p} {y}/{int(pr)}"

        # Auto-detect existing CSV (also in extra merged dirs); fall back to default path
        csv_p = (self._find_existing_csv(base_dir, act_norm, extra_dirs=extra_dirs or [])
                 or self._get_default_csv_path(base_dir, act_norm))
        t_dir = self.get_output_folder_path(base_dir, act_norm)

        allowed = ([f"{int(x.strip()):04d}" for x in filter_raw.split(",")
                    if x.strip().isdigit()] if filter_raw.strip() else None)
        search_dirs = [base_dir, t_dir] + [d for d in (extra_dirs or [])
                                            if os.path.isdir(d)]
        rows = self._generate_fresh_rows(
            act_norm, act_wnk, y, allowed, ignore_old_exif,
            photo_mapping, main_photo, search_dirs)
        if not rows:
            if not silent:
                messagebox.showwarning("Warnung", f"Keine Fotos für {act_norm} gefunden.")
            return 0
        # auto_save=True: always merge silently without dialog
        return self._save_csv(rows, csv_p, silent=silent, auto_save=True)

    def _core_update_csv_logic(self, existing_csv, raw_act="", base_dir="",
                               filter_raw="", ignore_old_exif=False,
                               main_photo="", photo_mapping=None,
                               extra_dirs=None, **kwargs):
        if photo_mapping is None:
            photo_mapping = {}
        p, y, pr = self.parse_activity(raw_act)
        if not p or not os.path.isdir(base_dir):
            return
        act_norm, act_wnk = f"{p}_{y}_{pr}", f"{p} {y}/{int(pr)}"
        t_dir = self.get_output_folder_path(base_dir, act_norm)
        allowed = ([f"{int(x.strip()):04d}" for x in filter_raw.split(",")
                    if x.strip().isdigit()] if filter_raw.strip() else None)
        search_dirs = [base_dir, t_dir] + [d for d in (extra_dirs or [])
                                            if os.path.isdir(d)]
        rows = self._generate_fresh_rows(
            act_norm, act_wnk, y, allowed, ignore_old_exif,
            photo_mapping, main_photo, search_dirs)
        if rows:
            # action 5: use dialog (auto_save=False)
            self._save_csv(rows, existing_csv, merge_source=existing_csv,
                           silent=False, auto_save=False)

    def _save_csv(self, fresh_rows, def_path, merge_source=None, silent=False, auto_save=False):
        """
        Save/merge CSV.
        auto_save=True  → silently backup+overwrite if file exists (for actions 1-4)
        auto_save=False → show dialog if file exists (for action 5)
        """
        f_merge = merge_source if merge_source else (
            def_path if os.path.exists(def_path) else None)
        out_path, mode, b_path = def_path, "new", None
        r_write = fresh_rows

        if f_merge and os.path.exists(f_merge):
            # Load existing rows, preserving all columns (esp. Kommentar)
            old = []
            try:
                with open(f_merge, 'r', encoding='cp1252', errors='replace') as f:
                    for r in csv.DictReader(f, delimiter=';'):
                        r["_sort_stelle"] = int(r.get("StellenNr", 0))
                        r["_sort_pos"] = int(r.get("PosNr", 0))
                        old.append(r)
            except:
                pass
            # Add only rows not yet in the existing CSV
            keys = {(r["_sort_stelle"], r["_sort_pos"]) for r in old}
            added = 0
            for fr in fresh_rows:
                if (fr["_sort_stelle"], fr["_sort_pos"]) not in keys:
                    old.append(fr)
                    added += 1
            r_write = old

            if auto_save:
                if added == 0:
                    # Nothing changed — skip write and backup entirely
                    self.log(f"Fotoliste aktuell, nichts zu ergänzen: "
                             f"{os.path.basename(f_merge)}")
                    return len(r_write)
                # New rows to add: backup and overwrite
                out_path, mode, b_path = f_merge, "overwrite", f_merge + ".bak"
                try:
                    shutil.copy2(f_merge, b_path)
                except Exception as e:
                    self.log(f"Backup fehlgeschlagen: {e}")
                    return None
                self.log(f"Auto-Merge: {added} neue Einträge → {os.path.basename(f_merge)}")
            else:
                # Dialog mode (action 5)
                is_batch = self.notebook.index(self.notebook.select()) == 1
                if is_batch:
                    choice = True
                else:
                    choice = messagebox.askyesnocancel(
                        "Speichern",
                        f"Liste existiert:\n'{os.path.basename(f_merge)}'\n\n"
                        "[Ja]=Ersetzen (Kommentare bleiben!)\n[Nein]=Neu benennen")

                if choice is None:
                    return None
                elif choice is True:
                    out_path, mode, b_path = f_merge, "overwrite", f_merge + ".bak"
                    try:
                        shutil.copy2(f_merge, b_path)
                    except Exception:
                        return None
                else:
                    out_path = filedialog.asksaveasfilename(
                        initialfile=f"NEU_{os.path.basename(f_merge)}",
                        defaultextension=".csv")
                    if not out_path:
                        return None
                    mode = "new"

        r_write.sort(key=lambda x: (x["_sort_stelle"], x["_sort_pos"]))
        try:
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(out_path, 'w', newline='', encoding='cp1252', errors='replace') as f:
                w = csv.DictWriter(
                    f, fieldnames=["Aktivitaet", "StellenNr", "PosNr",
                                   "Fotograf", "FotoDatum", "Kommentar"],
                    delimiter=';', extrasaction='ignore')
                w.writeheader()
                w.writerows(r_write)
            self.last_update_actions.append({'mode': mode, 'target': out_path, 'backup': b_path})
            self.log(f"Gespeichert: {os.path.basename(out_path)}")
            if not silent and self.notebook.index(self.notebook.select()) == 0:
                messagebox.showinfo("Gespeichert",
                                    f"Liste gespeichert:\n{os.path.basename(out_path)}")
            return len(r_write)
        except Exception as e:
            self.log(f"Fehler beim Speichern: {e}")
            return None

    # --- UNDO, LOG & EXTRA ---
    def undo_last_action(self):
        u_msg = []
        for a in self.last_update_actions:
            if a['mode'] == 'new' and os.path.exists(a['target']):
                os.remove(a['target'])
                u_msg.append(f"Erstellte Datei '{os.path.basename(a['target'])}' gelöscht.")
            elif a['mode'] == 'overwrite' and a['backup'] and os.path.exists(a['backup']):
                if os.path.exists(a['target']):
                    os.remove(a['target'])
                shutil.move(a['backup'], a['target'])
                u_msg.append("Überschriebene Original-CSV aus '.bak' wiederhergestellt.")
        self.last_update_actions.clear()

        u_c = 0
        if self.rename_history:
            for t, s in list(self.rename_history.items()):
                if os.path.exists(t):
                    try:
                        os.makedirs(os.path.dirname(s), exist_ok=True)
                        shutil.move(t, s)
                        u_c += 1
                    except:
                        pass
            self.rename_history.clear()
            if u_c > 0:
                u_msg.append(f"{u_c} Dateien in Ursprungszustand versetzt.")

        if not u_msg:
            messagebox.showinfo("Undo", "Nichts zum Rückgängig machen.")
        else:
            msg = "Undo ausgeführt:\n- " + "\n- ".join(u_msg)
            self.log(msg)
            messagebox.showinfo("Undo", msg)

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
5. Aktionen: Wähle die passende Aktion. Im Batch-Modus werden Nachfragen beim
   Aktualisieren bestehender Listen zum Zeitsparen automatisch mit "Ersetzen"
   (inkl. Backup) beantwortet.

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
  erneut angefasst.

[2. Nur umbenennen!]
  Sucht nach Roh-Mustern ('4-5.jpg') und benennt diese vor Ort um.

[3. Umbenannte Fotos aufspüren, verschieben, Fotoliste erstellen]
  Greift sich fertige Namen im WNK-Format (z. B. "OV_2022_1082_0023_004"),
  verschiebt und katalogisiert sie.

[4. Nur Fotoliste erstellen]
  Erzeugt die CSV-Liste aus den gefundenen Bildern, OHNE Dateien umzubenennen.
  Existiert bereits eine Fotoliste, werden nur fehlende Einträge ergänzt.

[5. Vorhandene Digitalbildliste aktualisieren]
  Wähle im Einzelmodus eine bestehende CSV im Explorer aus. Das Programm fügt
  neue Fotos aus den Ordnern nahtlos ein. Es fragt dich danach, ob du die
  gewählte Datei ersetzen möchtest (wobei alle Kommentare erhalten bleiben!)
  oder neu benennst. Im Batch-Modus geschieht das Ersetzen (inkl. Erstellung
  von Sicherheitskopien) vollautomatisch für alle gefundenen Maßnahmen.

[Letzte Aktion rückgängig machen (UNDO)]
  Macht Dateibewegungen rückgängig und löscht/restauriert die veränderten CSVs
  mithilfe von Sicherheitskopien (.bak).

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
