"""Graphical User Interface for HEIC Converter.

Guided CustomTkinter UI with background discovery and a shared batch engine.
"""

from __future__ import annotations

import datetime
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import convert_heic_to_png as converter

# ──────────────────────────── Constants ──────────────────────────────────────

# Unique display formats for dropdown (skip aliases like JPEG, TIF)
_ALIAS_SKIP = {"JPEG", "TIF"}
SUPPORTED_FORMATS = [fmt.upper() for fmt in converter.SUPPORTED_FORMATS if fmt.upper() not in _ALIAS_SKIP]

# Color palette
COLOR_BG = "#0f0f13"
COLOR_CARD = "#1a1a24"
COLOR_CARD_HOVER = "#22222f"
COLOR_BORDER = "#2a2a3a"
COLOR_ACCENT = "#6c5ce7"
COLOR_ACCENT_HOVER = "#7f6ff0"
COLOR_ACCENT_DIM = "#4a3fb5"
COLOR_SUCCESS = "#00b894"
COLOR_WARNING = "#fdcb6e"
COLOR_ERROR = "#e17055"
COLOR_TEXT = "#e8e8f0"
COLOR_TEXT_DIM = "#8888a0"
COLOR_TEXT_MUTED = "#55556a"
COLOR_LOG_BG = "#12121a"
COLOR_PROGRESS_BG = "#1e1e2e"
COLOR_PROGRESS_FG = "#6c5ce7"
COLOR_CANCEL = "#e17055"
COLOR_CANCEL_HOVER = "#d65d45"

DEFAULT_WORKERS = 4
MAX_WORKERS = 16


# ──────────────────────────── Utility ────────────────────────────────────────

def find_icon_path() -> Path | None:
    """Find the bundled or local icon file."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "heic_to_any.ico"
        if bundled.is_file():
            return bundled

    script_dir = Path(__file__).resolve().parent
    for candidate in (script_dir / "heic_to_any.ico", Path.cwd() / "heic_to_any.ico"):
        if candidate.is_file():
            return candidate
    return None


def open_in_file_manager(folder_path: Path) -> None:
    """Open folder in native OS file explorer."""
    if not folder_path.is_dir():
        messagebox.showerror("Output folder unavailable", f"This folder no longer exists:\n{folder_path}")
        return
    try:
        if sys.platform == "win32":
            os.startfile(folder_path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(folder_path)], check=True)
        else:
            subprocess.run(["xdg-open", str(folder_path)], check=True)
    except (OSError, subprocess.SubprocessError) as error:
        messagebox.showerror("Could not open results", f"{folder_path}\n\n{error}")


def format_duration(seconds: float) -> str:
    """Human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.0f}s"


# ──────────────────────────── GUI ────────────────────────────────────────────

class HEICConverterGUI:
    """Modern CustomTkinter GUI for HEIC to multi-format image converter."""

    def __init__(
        self,
        root_window: ctk.CTk,
        initial_root: Path | None = None,
        initial_format: str = "png",
        initial_output: str | None = None,
        initial_overwrite: bool = False,
        initial_workers: int = DEFAULT_WORKERS,
    ) -> None:
        self.root = root_window
        self.root.title(f"HEIC Converter {converter.__version__}")
        scale = self.root._get_window_scaling()
        height = max(540, min(720, int(self.root.winfo_screenheight() / scale) - 90))
        width = max(820, min(980, int(self.root.winfo_screenwidth() / scale) - 60))
        self.root.geometry(f"{width}x{height}")
        self.root.minsize(820, 540)

        # Appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.root.configure(fg_color=COLOR_BG)

        # Icon
        icon_path = find_icon_path()
        if icon_path and sys.platform == "win32":
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        # ─── State ───
        self.initial_dir = (
            initial_root.expanduser().resolve()
            if initial_root is not None
            else converter.application_root()
        )
        initial_format = {"jpeg": "jpg", "tif": "tiff"}.get(initial_format.lower(), initial_format.lower())
        self.format_var = tk.StringVar(value=initial_format.upper())
        self.output_folder_var = tk.StringVar(value=initial_output or f"heic-{initial_format.lower()}")
        self.overwrite_var = tk.BooleanVar(value=initial_overwrite)
        self.workers_var = tk.IntVar(value=initial_workers)

        self.is_converting = False
        self.is_cancelled = False
        self.close_requested = False
        self.worker: threading.Thread | None = None
        self.last_output_dir: Path | None = None

        # File list: list of Path objects (individual files or folders)
        self.source_files: list[Path] = [self.initial_dir] if initial_root is not None else []
        self.scan_result = converter.ScanResult()
        self.is_scanning = False
        self.scan_generation = 0
        self.scan_cancel = threading.Event()
        self.scan_after = None
        self.output_dirs: list[Path] = []
        # Log lines stored in memory — only written to disk on user request
        self.log_lines: list[str] = []

        self.msg_queue: queue.Queue = queue.Queue()

        # Stats
        self.conversion_start_time: float = 0
        self.total_converted = 0
        self.total_skipped = 0
        self.total_failed = 0
        self.total_found = 0

        self._build_ui()
        self.root.after(80, self._process_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Control-Return>", lambda _event: self._start_conversion())
        self.output_folder_var.trace_add("write", self._settings_changed)
        self._update_file_list_display()

    # ─────────────────────────── UI BUILD ────────────────────────────────────

    def _build_ui(self) -> None:
        # Reserve the primary action before laying out scrollable content.
        # This keeps Start/Cancel and progress reachable on short or scaled screens.
        footer = ctk.CTkFrame(self.root, fg_color=COLOR_BG)
        footer.pack(side="bottom", fill="x", padx=20, pady=(8, 16))
        self._build_progress_section(footer)
        self._build_action_bar(footer)
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.pack(side="top", fill="x", padx=24, pady=(16, 0))
        self._build_header(header)
        container = ctk.CTkScrollableFrame(self.root, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16)
        self._build_source_section(container)
        mid_row = ctk.CTkFrame(container, fg_color="transparent")
        mid_row.pack(fill="x", pady=(0, 12))
        mid_row.columnconfigure(0, weight=3)
        mid_row.columnconfigure(1, weight=2)
        self._build_settings_card(mid_row)
        self._build_stats_card(mid_row)
        self._build_log_section(container)

    def _build_header(self, parent) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", pady=(0, 16))

        title = ctk.CTkLabel(
            header,
            text="HEIC Converter",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=COLOR_TEXT,
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header,
            text="1  Add photos     /     2  Choose format     /     3  Start conversion",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_DIM,
        )
        subtitle.pack(anchor="w", pady=(2, 0))

    def _build_source_section(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        card.pack(fill="x", pady=(0, 12))

        # Card header
        card_header = ctk.CTkFrame(card, fg_color="transparent")
        card_header.pack(fill="x", padx=16, pady=(14, 8))

        ctk.CTkLabel(
            card_header,
            text="1  Add your photos",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=COLOR_TEXT,
        ).pack(side="left")

        self.file_count_label = ctk.CTkLabel(
            card_header,
            text="0 files",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_DIM,
        )
        self.file_count_label.pack(side="right")

        # File list area
        list_frame = ctk.CTkFrame(card, fg_color=COLOR_LOG_BG, corner_radius=8)
        list_frame.pack(fill="x", padx=16, pady=(0, 10))

        self.file_listbox = tk.Listbox(
            list_frame,
            height=4,
            selectmode="extended",
            exportselection=False,
            bg=COLOR_LOG_BG,
            fg=COLOR_TEXT_DIM,
            selectbackground=COLOR_ACCENT_DIM,
            selectforeground=COLOR_TEXT,
            font=("Consolas", 9),
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            activestyle="none",
        )
        scrollbar = ctk.CTkScrollbar(list_frame, command=self.file_listbox.yview, height=0)
        self.file_listbox.configure(yscrollcommand=scrollbar.set)
        self.file_listbox.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=4)

        # Placeholder text
        self.file_listbox.insert(0, "  No files added yet. Click buttons below to add files or folders.")
        self.file_listbox.configure(state="disabled")

        # Buttons row
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 14))

        self.add_files_btn = ctk.CTkButton(
            btn_row, text="Add files", width=120, height=32,
            corner_radius=8,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._add_files,
        )
        self.add_files_btn.pack(side="left", padx=(0, 8))

        self.add_folder_btn = ctk.CTkButton(
            btn_row, text="Choose folder", width=130, height=32,
            corner_radius=8,
            fg_color=COLOR_CARD_HOVER, hover_color=COLOR_BORDER,
            border_width=1, border_color=COLOR_BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            command=self._add_folder,
        )
        self.add_folder_btn.pack(side="left", padx=(0, 8))

        self.clear_btn = ctk.CTkButton(
            btn_row, text="Clear all", width=100, height=32,
            corner_radius=8,
            fg_color="transparent", hover_color=COLOR_CARD_HOVER,
            border_width=1, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_DIM,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self._clear_files,
        )
        self.clear_btn.pack(side="left")

        self.remove_selected_btn = ctk.CTkButton(
            btn_row, text="Remove Selected", width=130, height=32,
            corner_radius=8,
            fg_color="transparent", hover_color=COLOR_CARD_HOVER,
            border_width=1, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_DIM,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=self._remove_selected,
        )
        self.remove_selected_btn.pack(side="right")

    def _build_settings_card(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        ctk.CTkLabel(
            card, text="2  Choose how to save",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=COLOR_TEXT,
        ).pack(anchor="w", padx=16, pady=(14, 10))

        settings_inner = ctk.CTkFrame(card, fg_color="transparent")
        settings_inner.pack(fill="x", padx=16, pady=(0, 14))

        # Row 1: Format + Output folder
        row1 = ctk.CTkFrame(settings_inner, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(row1, text="Format", text_color=COLOR_TEXT_DIM,
                      font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        self.format_menu = ctk.CTkOptionMenu(
            row1, variable=self.format_var, values=SUPPORTED_FORMATS,
            width=90, height=30, corner_radius=6,
            fg_color=COLOR_LOG_BG, button_color=COLOR_ACCENT_DIM,
            button_hover_color=COLOR_ACCENT,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_format_changed,
        )
        self.format_menu.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(row1, text="Subfolder", text_color=COLOR_TEXT_DIM,
                      font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))
        self.output_entry = ctk.CTkEntry(
            row1, textvariable=self.output_folder_var, width=140, height=30,
            corner_radius=6, fg_color=COLOR_LOG_BG, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT, font=ctk.CTkFont(size=11),
        )
        self.output_entry.pack(side="left")

        # Row 2: Workers + Overwrite
        row2 = ctk.CTkFrame(settings_inner, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(row2, text="Parallel jobs", text_color=COLOR_TEXT_DIM,
                      font=ctk.CTkFont(size=11)).pack(side="left", padx=(0, 6))

        workers_values = [str(i) for i in range(1, MAX_WORKERS + 1)]
        self.workers_menu = ctk.CTkOptionMenu(
            row2, values=workers_values,
            width=70, height=30, corner_radius=6,
            fg_color=COLOR_LOG_BG, button_color=COLOR_ACCENT_DIM,
            button_hover_color=COLOR_ACCENT,
            font=ctk.CTkFont(size=12),
            command=self._on_workers_changed,
        )
        self.workers_menu.set(str(self.workers_var.get()))
        self.workers_menu.pack(side="left", padx=(0, 16))

        self.overwrite_switch = ctk.CTkSwitch(
            row2, text="Overwrite existing",
            variable=self.overwrite_var,
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_DIM,
            progress_color=COLOR_ACCENT,
            button_color=COLOR_TEXT_MUTED,
            button_hover_color=COLOR_TEXT_DIM,
        )
        self.overwrite_switch.pack(side="left")

    def _build_stats_card(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        ctk.CTkLabel(
            card, text="Batch results",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=COLOR_TEXT,
        ).pack(anchor="w", padx=16, pady=(14, 10))

        stats_grid = ctk.CTkFrame(card, fg_color="transparent")
        stats_grid.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        stats_grid.columnconfigure(0, weight=1)
        stats_grid.columnconfigure(1, weight=1)

        self.stat_converted = self._stat_pill(stats_grid, "Converted", "0", COLOR_SUCCESS, 0, 0)
        self.stat_skipped = self._stat_pill(stats_grid, "Skipped", "0", COLOR_WARNING, 0, 1)
        self.stat_failed = self._stat_pill(stats_grid, "Failed", "0", COLOR_ERROR, 1, 0)
        self.stat_time = self._stat_pill(stats_grid, "Time", "—", COLOR_ACCENT, 1, 1)

    def _stat_pill(self, parent, label: str, value: str, color: str, row: int, col: int):
        pill = ctk.CTkFrame(parent, fg_color=COLOR_LOG_BG, corner_radius=8, height=52)
        pill.grid(row=row, column=col, sticky="ew", padx=3, pady=3)
        pill.grid_propagate(False)

        val_lbl = ctk.CTkLabel(pill, text=value, font=ctk.CTkFont(size=18, weight="bold"),
                                text_color=color)
        val_lbl.pack(pady=(8, 0))
        ctk.CTkLabel(pill, text=label, font=ctk.CTkFont(size=9),
                      text_color=COLOR_TEXT_DIM).pack(pady=(0, 6))
        return val_lbl

    def _build_progress_section(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        card.pack(fill="x", pady=(0, 12))

        progress_inner = ctk.CTkFrame(card, fg_color="transparent")
        progress_inner.pack(fill="x", padx=16, pady=14)

        top_row = ctk.CTkFrame(progress_inner, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 8))

        self.status_label = ctk.CTkLabel(
            top_row, text="Ready",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_ACCENT,
            wraplength=660, justify="left", anchor="w",
        )
        self.status_label.pack(side="left")

        self.percent_label = ctk.CTkLabel(
            top_row, text="0%",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_TEXT_DIM,
        )
        self.percent_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(
            progress_inner, height=8, corner_radius=4,
            fg_color=COLOR_PROGRESS_BG,
            progress_color=COLOR_PROGRESS_FG,
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x")

        self.file_status_label = ctk.CTkLabel(
            progress_inner, text="",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR_TEXT_DIM,
            anchor="w",
        )
        self.file_status_label.configure(wraplength=740, justify="left")
        self.file_status_label.pack(fill="x", pady=(6, 0))

    def _build_log_section(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color=COLOR_BORDER)
        card.pack(fill="both", expand=True, pady=(0, 12))

        # Header row with Save Log button
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            header, text="Activity & error details",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_TEXT,
        ).pack(side="left")

        self.save_log_btn = ctk.CTkButton(
            header, text="Save log", width=100, height=28,
            corner_radius=6,
            fg_color="transparent", hover_color=COLOR_CARD_HOVER,
            border_width=1, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_DIM,
            font=ctk.CTkFont(size=11),
            command=self._save_log,
        )
        self.save_log_btn.pack(side="right")

        self.clear_log_btn = ctk.CTkButton(
            header, text="Clear", width=60, height=28,
            corner_radius=6,
            fg_color="transparent", hover_color=COLOR_CARD_HOVER,
            border_width=1, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_DIM,
            font=ctk.CTkFont(size=10),
            command=self._clear_log,
        )
        self.clear_log_btn.pack(side="right", padx=(0, 6))

        log_frame = ctk.CTkFrame(card, fg_color=COLOR_LOG_BG, corner_radius=8)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(0, 14))

        self.log_text = tk.Text(
            log_frame,
            wrap="word",
            height=8,
            font=("Consolas", 9),
            bg=COLOR_LOG_BG,
            fg=COLOR_TEXT_DIM,
            insertbackground=COLOR_TEXT,
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            state="disabled",
        )
        log_scroll = ctk.CTkScrollbar(log_frame, command=self.log_text.yview, height=0)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        log_scroll.pack(side="right", fill="y", padx=(0, 4), pady=4)

        # Log tag styling
        self.log_text.tag_configure("converted", foreground=COLOR_SUCCESS)
        self.log_text.tag_configure("skipped", foreground=COLOR_WARNING)
        self.log_text.tag_configure("failed", foreground=COLOR_ERROR)
        self.log_text.tag_configure("info", foreground=COLOR_TEXT_DIM)
        self.log_text.tag_configure("header", foreground=COLOR_ACCENT)

    def _build_action_bar(self, parent) -> None:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x")

        self.start_btn = ctk.CTkButton(
            bar, text="3  Start conversion", width=200, height=42,
            corner_radius=10,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            command=self._start_conversion,
        )
        self.start_btn.pack(side="left", padx=(0, 10))

        self.cancel_btn = ctk.CTkButton(
            bar, text="Cancel", width=120, height=42,
            corner_radius=10,
            fg_color=COLOR_CANCEL, hover_color=COLOR_CANCEL_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            command=self._cancel_conversion,
            state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=(0, 10))

        self.open_btn = ctk.CTkButton(
            bar, text="Open results", width=140, height=42,
            corner_radius=10,
            fg_color=COLOR_CARD_HOVER, hover_color=COLOR_BORDER,
            border_width=1, border_color=COLOR_BORDER,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=self._open_output_folder,
            state="disabled",
        )
        self.open_btn.pack(side="right")

    # ─────────────────────────── File Management ─────────────────────────────

    def _settings_changed(self, *_args) -> None:
        if self.is_converting or self.close_requested:
            return
        # Invalidate results immediately, debounce edits to the subfolder name.
        self.scan_cancel.set()
        self.scan_generation += 1
        self.start_btn.configure(state="disabled")
        if self.scan_after is not None:
            self.root.after_cancel(self.scan_after)
        self.scan_after = self.root.after(250, self._begin_scan)

    def _update_file_list_display(self) -> None:
        """Render selections only; never walk the filesystem on Tk's thread."""
        self.file_listbox.configure(state="normal")
        self.file_listbox.delete(0, "end")
        for item in self.source_files:
            self.file_listbox.insert("end", f"  {item}")
        if not self.source_files:
            self.file_listbox.insert(0, "  Choose a folder or add HEIC / HEIF files to begin.")
            self.file_listbox.configure(state="disabled")
        self._begin_scan()

    def _begin_scan(self) -> None:
        if self.scan_after is not None:
            self.root.after_cancel(self.scan_after)
        self.scan_after = None
        if self.is_converting or self.close_requested:
            return
        self.scan_cancel.set()
        self.scan_cancel = threading.Event()
        self.scan_generation += 1
        generation = self.scan_generation
        self.scan_result = converter.ScanResult()
        self.is_scanning = False
        self.start_btn.configure(state="disabled", text="3  Start conversion")
        self.open_btn.configure(state="disabled")
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.percent_label.configure(text="")
        if not self.source_files:
            self.file_count_label.configure(text="No photos selected")
            self.status_label.configure(text="Step 1: Choose a folder or add files", text_color=COLOR_TEXT)
            self.file_status_label.configure(text="Subfolders are included. Your original photos stay unchanged.")
            return
        try:
            output = converter.validate_output_folder(self.output_folder_var.get())
        except ValueError as error:
            self.status_label.configure(text="Check the output subfolder name", text_color=COLOR_WARNING)
            self.file_status_label.configure(text=str(error))
            return
        self.is_scanning = True
        self.file_count_label.configure(text="Scanning selected sources...")
        self.status_label.configure(text="Finding your HEIC / HEIF photos...", text_color=COLOR_ACCENT)
        self.file_status_label.configure(text="Scanning subfolders in the background. You can still change your selection.")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        sources = tuple(self.source_files)
        cancel = self.scan_cancel

        def scan():
            try:
                result = converter.scan_sources(sources, output, cancel.is_set)
                self.msg_queue.put({"type": "scan", "generation": generation, "result": result})
            except Exception as error:
                self.msg_queue.put({"type": "scan", "generation": generation,
                                    "result": converter.ScanResult(warnings=[converter.error_message(error)])})
        threading.Thread(target=scan, daemon=True).start()

    def _handle_scan(self, msg) -> None:
        if msg["generation"] != self.scan_generation or self.close_requested:
            return
        self.is_scanning = False
        self.scan_result = msg["result"]
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        count = len(self.scan_result.files)
        self.file_count_label.configure(text=f"{count} photos • {len(self.source_files)} sources")
        for warning in self.scan_result.warnings:
            self._append_log(f"WARNING: {warning}", "skipped")
        if not count:
            self.status_label.configure(text="No HEIC / HEIF photos found", text_color=COLOR_WARNING)
            self.file_status_label.configure(text="Choose another folder or add .heic, .heif or .hif files. Check Activity for scan warnings.")
            return
        self.start_btn.configure(state="normal", text=f"Convert {count} photos to {self.format_var.get()}")
        warning = " Scan warnings: see Activity." if self.scan_result.warnings else ""
        self.status_label.configure(text=f"Ready: {count} photos. Click Convert below.{warning}", text_color=COLOR_SUCCESS)
        example = self.scan_result.files[0].parent / self.output_folder_var.get()
        self.file_status_label.configure(text=f"Save to: {example}\nEach source folder gets its own output subfolder. Originals are kept.")

    def _add_files(self) -> None:
        if self.is_converting:
            return
        filetypes = [
            ("HEIC/HEIF Images", "*.heic *.heif *.hif"),
            ("All Files", "*.*"),
        ]
        files = filedialog.askopenfilenames(
            parent=self.root,
            title="Select HEIC/HEIF Files",
            initialdir=str(self.initial_dir),
            filetypes=filetypes,
        )
        if files:
            for f in files:
                p = Path(f).resolve()
                if p not in self.source_files:
                    self.source_files.append(p)
            self._update_file_list_display()

    def _add_folder(self) -> None:
        if self.is_converting:
            return
        folder = filedialog.askdirectory(
            parent=self.root,
            title="Select Folder Containing HEIC/HEIF Photos",
            initialdir=str(self.initial_dir),
        )
        if folder:
            p = Path(folder).resolve()
            if p not in self.source_files:
                self.source_files.append(p)
            self.initial_dir = p
            self._update_file_list_display()

    def _clear_files(self) -> None:
        if self.is_converting:
            return
        self.source_files.clear()
        self._update_file_list_display()

    def _remove_selected(self) -> None:
        if self.is_converting:
            return
        selection = self.file_listbox.curselection()
        if not selection:
            return
        # Remove in reverse to preserve indices
        for idx in reversed(selection):
            if 0 <= idx < len(self.source_files):
                self.source_files.pop(idx)
        self._update_file_list_display()

    # ─────────────────────────── Log ─────────────────────────────────────────

    def _append_log(self, text: str, tag: str = "info") -> None:
        self.log_lines.append(text)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_lines.clear()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _save_log(self) -> None:
        if not self.log_lines:
            messagebox.showinfo("Save Log", "No log entries to save.", parent=self.root)
            return
        filepath = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save Log File",
            defaultextension=".log",
            filetypes=[("Log Files", "*.log"), ("Text Files", "*.txt"), ("All Files", "*.*")],
            initialfile=f"heic_converter_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write("\n".join(self.log_lines))
                messagebox.showinfo("Log Saved", f"Log saved to:\n{filepath}", parent=self.root)
            except OSError as e:
                messagebox.showerror("Save Error", f"Could not save log:\n{e}", parent=self.root)

    # ─────────────────────────── Format ──────────────────────────────────────

    def _on_format_changed(self, _value=None) -> None:
        fmt = self.format_var.get().lower()
        current = self.output_folder_var.get()
        if current in {f"heic-{f}" for f in converter.SUPPORTED_FORMATS}:
            self.output_folder_var.set(f"heic-{fmt}")
        else:
            self._settings_changed()

    def _on_workers_changed(self, value) -> None:
        self.workers_var.set(int(value))

    # ─────────────────────────── Conversion ──────────────────────────────────

    def _set_running(self, running: bool) -> None:
        self.is_converting = running
        state = "disabled" if running else "normal"
        self.add_files_btn.configure(state=state)
        self.add_folder_btn.configure(state=state)
        self.clear_btn.configure(state=state)
        self.remove_selected_btn.configure(state=state)
        self.format_menu.configure(state=state)
        self.output_entry.configure(state=state)
        self.workers_menu.configure(state=state)
        self.overwrite_switch.configure(state=state)
        self.start_btn.configure(state="disabled" if running or not self.scan_result.files else "normal")
        self.cancel_btn.configure(state="normal" if running else "disabled")

    def _start_conversion(self) -> None:
        if self.close_requested or self.is_converting or self.is_scanning or self.scan_after is not None:
            return
        if self.worker and self.worker.is_alive():
            return

        if not self.scan_result.files:
            messagebox.showwarning("No Files", "Please add files or folders first.", parent=self.root)
            return

        try:
            target_fmt = converter.normalize_format(self.format_var.get())
            output_folder = converter.validate_output_folder(
                self.output_folder_var.get().strip() or f"heic-{target_fmt}"
            )
        except (OSError, ValueError) as error:
            messagebox.showerror("Invalid Settings", str(error), parent=self.root)
            return

        self.is_cancelled = False
        self._set_running(True)
        self.open_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.percent_label.configure(text="0%")
        self._clear_log()
        self.total_converted = 0
        self.total_skipped = 0
        self.total_failed = 0
        self.total_found = 0
        self._update_stats(0, 0, 0, 0)
        self.status_label.configure(text="Converting photos...", text_color=COLOR_ACCENT)
        self.file_status_label.configure(text="")
        self.conversion_start_time = time.time()

        self.active_files = tuple(self.scan_result.files)
        self.active_warnings = list(self.scan_result.warnings)
        self.scan_generation += 1
        num_workers = self.workers_var.get()
        overwrite = self.overwrite_var.get()

        self.worker = threading.Thread(
            target=self._run_conversion_worker,
            args=(target_fmt, output_folder, overwrite, num_workers),
            daemon=True,
        )
        self.worker.start()

    def _run_conversion_worker(self, target_fmt: str, output_folder: str,
                                overwrite: bool, num_workers: int) -> None:
        """Workers only send messages; all Tk reads and writes stay on the UI thread."""
        def log(text):
            tag = "failed" if text.startswith("FAILED") else "skipped" if text.startswith("SKIPPED") else "info"
            self.msg_queue.put({"type": "log", "text": text, "tag": tag})

        def progress(index, total, source, status):
            self.msg_queue.put({"type": "progress", "index": index, "total": total,
                                "source": str(source), "status": status})
        try:
            log(f"Converting {len(self.active_files)} photos to {target_fmt.upper()} with {num_workers} parallel jobs.")
            for warning in self.active_warnings:
                log(f"WARNING: {warning}")
            summary = converter.convert_files(
                list(self.active_files), output_folder, overwrite, target_fmt,
                num_workers, progress, lambda: self.is_cancelled, log,
            )
            self.msg_queue.put({"type": "complete", "cancelled": summary.cancelled,
                                "converted": summary.converted, "skipped": summary.skipped,
                                "failed": summary.failed, "found": summary.found,
                                "output_dirs": summary.output_dirs, "warnings": self.active_warnings})
        except Exception as error:
            self.msg_queue.put({"type": "error", "error": converter.error_message(error)})

    def _cancel_conversion(self) -> None:
        if self.is_converting:
            self.is_cancelled = True
            self.status_label.configure(text="Cancelling...", text_color=COLOR_WARNING)
            self.cancel_btn.configure(state="disabled")

    # ─────────────────────────── Queue Processing ────────────────────────────

    def _process_queue(self) -> None:
        if self.close_requested and (self.worker is None or not self.worker.is_alive()):
            self.root.destroy()
            return
        try:
            for _ in range(200):
                msg = self.msg_queue.get_nowait()
                kind = msg.get("type")
                if kind == "scan":
                    self._handle_scan(msg)
                elif kind == "log":
                    tag = msg.get("tag", "info")
                    self._append_log(msg["text"], tag)
                elif kind == "progress":
                    idx, total = msg["index"], msg["total"]
                    pct = int(idx / total * 100) if total else 0
                    self.progress_bar.set(pct / 100)
                    self.percent_label.configure(text=f"{pct}%")
                    if not self.is_cancelled:
                        self.status_label.configure(
                            text=f"Converting  ({idx}/{total})",
                            text_color=COLOR_ACCENT,
                        )
                        self.file_status_label.configure(text=f"  {msg['source']}")
                    attr = "total_" + msg["status"]
                    setattr(self, attr, getattr(self, attr) + 1)
                    self._update_stats(self.total_converted, self.total_skipped,
                                       self.total_failed, time.time() - self.conversion_start_time)
                elif kind == "complete":
                    self._handle_completion(msg)
                elif kind == "error":
                    self._set_running(False)
                    self.status_label.configure(text="Error", text_color=COLOR_ERROR)
                    self._append_log(f"ERROR: {msg['error']}", "failed")
                    if not self.close_requested:
                        messagebox.showerror("Conversion Error", msg["error"], parent=self.root)
        except queue.Empty:
            pass
        self.root.after(60, self._process_queue)

    def _update_stats(self, converted: int, skipped: int, failed: int, elapsed: float) -> None:
        self.stat_converted.configure(text=str(converted))
        self.stat_skipped.configure(text=str(skipped))
        self.stat_failed.configure(text=str(failed))
        self.stat_time.configure(text=format_duration(elapsed) if elapsed > 0 else "—")

    def _handle_completion(self, msg: dict) -> None:
        self._set_running(False)
        elapsed = time.time() - self.conversion_start_time

        converted = msg.get("converted", 0)
        skipped = msg.get("skipped", 0)
        failed = msg.get("failed", 0)
        found = msg.get("found", 0)
        cancelled = msg.get("cancelled", False)

        self._update_stats(converted, skipped, failed, elapsed)

        processed = converted + skipped + failed
        pct = int(processed / found * 100) if found else 0
        self.progress_bar.set(pct / 100)
        self.percent_label.configure(text=f"{pct}%")

        self.output_dirs = msg.get("output_dirs", [])
        if self.output_dirs:
            self.last_output_dir = self.output_dirs[0]
            self.open_btn.configure(state="normal", text=f"Open results ({len(self.output_dirs)})" if len(self.output_dirs) > 1 else "Open results")

        if cancelled:
            title = "Cancelled"
            color = COLOR_WARNING
            self._append_log(f"\n⚠ Conversion cancelled. {converted} converted, {skipped} skipped, {failed} failed.", "skipped")
        elif failed or msg.get("warnings"):
            title = "Completed with errors or scan warnings — see Activity"
            color = COLOR_WARNING
            self._append_log(f"\n⚠ Done with errors. {converted} converted, {skipped} skipped, {failed} failed.", "failed")
        elif found == 0:
            title = "No HEIC files found"
            color = COLOR_WARNING
            self._append_log("\nNo HEIC/HEIF files found in the selected sources.", "skipped")
        else:
            title = "Completed successfully"
            color = COLOR_SUCCESS
            self._append_log(
                f"\n✓ All done! {converted} converted, {skipped} skipped in {format_duration(elapsed)}.",
                "converted",
            )

        self.status_label.configure(text=title, text_color=color)
        self.file_status_label.configure(text=f"{converted} converted • {skipped} already exist • {failed} failed. "
                                         + ("Open results to view your photos." if self.output_dirs else "Check Activity for details."))

    # ─────────────────────────── Actions ─────────────────────────────────────

    def _open_output_folder(self) -> None:
        if len(self.output_dirs) == 1:
            open_in_file_manager(self.output_dirs[0])
        elif self.output_dirs:
            dialog = ctk.CTkToplevel(self.root)
            dialog.title("Output folders")
            dialog.geometry("720x360")
            dialog.transient(self.root)
            ctk.CTkLabel(dialog, text="Choose a folder to view converted photos", font=ctk.CTkFont(size=17, weight="bold")).pack(pady=16)
            folders = ctk.CTkScrollableFrame(dialog)
            folders.pack(fill="both", expand=True, padx=16, pady=(0, 16))
            for folder in self.output_dirs:
                ctk.CTkButton(folders, text=str(folder), anchor="w",
                              command=lambda path=folder: open_in_file_manager(path)).pack(fill="x", pady=4)

    def _on_close(self) -> None:
        if self.close_requested:
            return
        self.scan_cancel.set()
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Quit", "Stop conversion and close?", parent=self.root):
                return
            self.close_requested = True
            self._cancel_conversion()
            self.status_label.configure(text="Closing...", text_color=COLOR_WARNING)
        else:
            self.root.destroy()


# ──────────────────────────── Entry Point ────────────────────────────────────

def launch_gui(initial_root: Path | None = None, initial_format: str = "png", **settings) -> int:
    root = ctk.CTk()
    HEICConverterGUI(root, initial_root=initial_root, initial_format=initial_format, **settings)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(launch_gui())
