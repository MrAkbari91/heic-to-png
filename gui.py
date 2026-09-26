"""Graphical User Interface for HEIC Converter.

Allows users to select input directories, choose target image formats
(PNG, JPG, WebP, BMP, TIFF, GIF), monitor conversion progress, and view logs.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from contextlib import ExitStack

import convert_heic_to_png as converter

SUPPORTED_FORMATS = [fmt.upper() for fmt in converter.SUPPORTED_FORMATS]


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
        return
    try:
        if sys.platform == "win32":
            os.startfile(folder_path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(folder_path)], check=False)
        else:
            subprocess.run(["xdg-open", str(folder_path)], check=False)
    except Exception:
        pass


class HEICConverterGUI:
    """Modern Tkinter GUI for HEIC to multi-format image converter."""

    def __init__(
        self,
        root_window: tk.Tk,
        initial_root: Path | None = None,
        initial_format: str = "png",
    ) -> None:
        self.root = root_window
        self.root.title("HEIC to Any Image Converter")
        self.root.geometry("760x700")
        self.root.minsize(700, 640)

        # Apply icon
        icon_path = find_icon_path()
        if icon_path and sys.platform == "win32":
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        # State
        self.initial_dir = (
            initial_root.expanduser().resolve()
            if initial_root is not None
            else converter.application_root()
        )
        self.root_path_var = tk.StringVar(value=str(self.initial_dir))
        self.format_var = tk.StringVar(value=initial_format.upper())
        self.output_folder_var = tk.StringVar(value=f"heic-{initial_format.lower()}")
        self.overwrite_var = tk.BooleanVar(value=False)
        self.save_report_var = tk.BooleanVar(value=True)

        self.is_converting = False
        self.is_cancelled = False
        self.close_requested = False
        self.worker: threading.Thread | None = None
        self.last_root_dir = self.initial_dir
        self.setting_widgets = []
        self.last_output_dir: Path | None = None

        self.msg_queue: queue.Queue = queue.Queue()

        self._setup_style()
        self._build_ui()

        # Listen for messages from background conversion thread
        self.root.after(100, self._process_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self) -> None:
        style = ttk.Style()
        available_themes = style.theme_names()
        if "vista" in available_themes and sys.platform == "win32":
            style.theme_use("vista")
        elif "clam" in available_themes:
            style.theme_use("clam")

        # Custom styling
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("SubHeader.TLabel", font=("Segoe UI", 9), foreground="#555555")
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"))

    def _build_ui(self) -> None:
        main_frame = ttk.Frame(self.root, padding=16)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Header ---
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 12))

        title_lbl = ttk.Label(
            header_frame,
            text="HEIC to Any Image Converter",
            style="Header.TLabel",
        )
        title_lbl.pack(anchor=tk.W)

        subtitle_lbl = ttk.Label(
            header_frame,
            text="Convert HEIC / HEIF photos into PNG, JPG, WEBP, BMP, TIFF or GIF.",
            style="SubHeader.TLabel",
        )
        subtitle_lbl.pack(anchor=tk.W, pady=(2, 0))

        # --- Source Folder Frame ---
        folder_frame = ttk.LabelFrame(main_frame, text=" 1. Select Folder ", padding=10)
        folder_frame.pack(fill=tk.X, pady=(0, 10))

        folder_input_frame = ttk.Frame(folder_frame)
        folder_input_frame.pack(fill=tk.X)

        self.folder_entry = ttk.Entry(
            folder_input_frame, textvariable=self.root_path_var, font=("Segoe UI", 9)
        )
        self.folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        browse_btn = ttk.Button(
            folder_input_frame, text="Browse...", command=self._browse_folder
        )
        browse_btn.pack(side=tk.RIGHT)

        self.folder_info_label = ttk.Label(
            folder_frame,
            text="Scans this folder and all subfolders recursively for .heic / .heif files.",
            font=("Segoe UI", 8),
            foreground="#666666",
        )
        self.folder_info_label.pack(anchor=tk.W, pady=(4, 0))

        # --- Format & Options Frame ---
        options_frame = ttk.LabelFrame(
            main_frame, text=" 2. Conversion Settings ", padding=10
        )
        options_frame.pack(fill=tk.X, pady=(0, 10))

        # Target Format Row
        format_row = ttk.Frame(options_frame)
        format_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(
            format_row, text="Target Format:", font=("Segoe UI", 9, "bold")
        ).pack(side=tk.LEFT, padx=(0, 12))

        self.format_combo = ttk.Combobox(
            format_row, textvariable=self.format_var, values=SUPPORTED_FORMATS,
            state="readonly", width=12,
        )
        self.format_combo.pack(side=tk.LEFT)
        self.format_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_format_changed())

        # Output Folder Name Row
        folder_row = ttk.Frame(options_frame)
        folder_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(folder_row, text="Output Subfolder:").pack(
            side=tk.LEFT, padx=(0, 12)
        )
        self.output_folder_entry = ttk.Entry(
            folder_row, textvariable=self.output_folder_var, width=20
        )
        self.output_folder_entry.pack(side=tk.LEFT)

        ttk.Label(
            folder_row,
            text="(Created inside each photo directory)",
            font=("Segoe UI", 8),
            foreground="#666666",
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Checkboxes
        check_row = ttk.Frame(options_frame)
        check_row.pack(fill=tk.X)

        self.overwrite_check = ttk.Checkbutton(
            check_row, text="Overwrite existing files", variable=self.overwrite_var
        )
        self.overwrite_check.pack(side=tk.LEFT, padx=(0, 16))

        self.report_check = ttk.Checkbutton(
            check_row, text="Create summary report file", variable=self.save_report_var
        )
        self.report_check.pack(side=tk.LEFT)
        self.setting_widgets = [self.folder_entry, browse_btn, self.output_folder_entry,
                                self.overwrite_check, self.report_check]

        # --- Progress & Stats ---
        progress_frame = ttk.LabelFrame(
            main_frame, text=" 3. Progress & Status ", padding=10
        )
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(fill=tk.X, pady=(0, 6))

        info_row = ttk.Frame(progress_frame)
        info_row.pack(fill=tk.X)

        self.status_label = ttk.Label(
            info_row,
            text="Ready to convert",
            font=("Segoe UI", 9, "bold"),
            foreground="#0066cc",
        )
        self.status_label.pack(side=tk.LEFT)

        self.count_label = ttk.Label(
            info_row, text="0 / 0 (0%)", font=("Segoe UI", 9)
        )
        self.count_label.pack(side=tk.RIGHT)

        # --- Log Output Area ---
        log_frame = ttk.Frame(main_frame)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.log_text = tk.Text(
            log_frame,
            height=8,
            wrap=tk.WORD,
            font=("Consolas", 8),
            bg="#fbfbfb",
            relief=tk.SOLID,
            borderwidth=1,
        )
        log_scroll = ttk.Scrollbar(
            log_frame, orient=tk.VERTICAL, command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=log_scroll.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Log tag styling
        self.log_text.tag_configure("converted", foreground="#007700")
        self.log_text.tag_configure("skipped", foreground="#b36b00")
        self.log_text.tag_configure("failed", foreground="#cc0000")
        self.log_text.tag_configure("info", foreground="#333333")

        # --- Action Buttons ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        self.start_btn = ttk.Button(
            btn_frame,
            text="▶ Start Conversion",
            style="Primary.TButton",
            command=self._start_conversion,
        )
        self.start_btn.pack(side=tk.LEFT, padx=(0, 8), ipadx=8, ipady=3)

        self.cancel_btn = ttk.Button(
            btn_frame,
            text="⏹ Cancel",
            command=self._cancel_conversion,
            state=tk.DISABLED,
        )
        self.cancel_btn.pack(side=tk.LEFT, padx=(0, 8), ipady=3)

        self.open_btn = ttk.Button(
            btn_frame,
            text="📂 Open Output Folder",
            command=self._open_output_folder,
            state=tk.DISABLED,
        )
        self.open_btn.pack(side=tk.RIGHT, ipady=3)

    def _browse_folder(self) -> None:
        initial = (
            self.root_path_var.get()
            if Path(self.root_path_var.get()).is_dir()
            else str(converter.application_root())
        )
        selected = filedialog.askdirectory(
            parent=self.root, title="Select Photos Folder", initialdir=initial
        )
        if selected:
            self.root_path_var.set(selected)

    def _on_format_changed(self) -> None:
        fmt = self.format_var.get().lower()
        self.output_folder_var.set(f"heic-{fmt}")

    def _append_log(self, text: str, tag: str = "info") -> None:
        self.log_text.insert(tk.END, text + "\n", tag)
        self.log_text.see(tk.END)

    def _set_running(self, running: bool) -> None:
        self.is_converting = running
        for widget in self.setting_widgets:
            widget.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.format_combo.configure(state=tk.DISABLED if running else "readonly")
        self.start_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.cancel_btn.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _start_conversion(self) -> None:
        if self.close_requested or self.is_converting or (self.worker and self.worker.is_alive()):
            return
        try:
            text = self.root_path_var.get().strip().strip('"')
            if not text:
                raise ValueError("Please select a folder containing HEIC / HEIF photos.")
            root_dir = Path(text).expanduser().resolve()
            if not root_dir.is_dir():
                raise ValueError(f"Selected folder does not exist: {root_dir}")
            target_fmt = converter.normalize_format(self.format_var.get())
            output_folder = converter.validate_output_folder(
                self.output_folder_var.get().strip() or f"heic-{target_fmt}"
            )
        except (OSError, ValueError) as error:
            messagebox.showerror("Invalid Settings", str(error), parent=self.root)
            return

        self.last_root_dir = root_dir
        self.last_output_dir = None
        self.is_cancelled = False
        self._set_running(True)
        self.open_btn.config(state=tk.DISABLED)
        self.progress_bar["value"] = 0
        self.log_text.delete("1.0", tk.END)
        self.status_label.config(text="Scanning for HEIC files...", foreground="#0066cc")
        self.count_label.config(text="Scanning...")
        self.worker = threading.Thread(
            target=self._run_conversion_worker,
            args=(root_dir, target_fmt, output_folder,
                  self.overwrite_var.get(), self.save_report_var.get()),
            daemon=False,
        )
        self.worker.start()

    def _run_conversion_worker(self, root_dir: Path, target_fmt: str,
                               output_folder: str, overwrite: bool, save_report: bool) -> None:
        def log(text: str) -> None:
            self.msg_queue.put({"type": "log", "text": text})

        def progress(index: int, total: int, source: Path, status: str) -> None:
            self.msg_queue.put({"type": "progress", "index": index, "total": total,
                                "source": str(source), "status": status})

        # Decoder initialization must be inside the try: a blocked DLL is recoverable UI state.
        try:
            converter.initialize_heif()
            report_path = None
            report_warning = None
            with ExitStack() as stack:
                report = None
                if save_report:
                    candidate = root_dir / f"heic-{target_fmt}-report.txt"
                    try:
                        report = stack.enter_context(candidate.open("w", encoding="utf-8"))
                        report_path = candidate
                    except OSError as error:
                        report_warning = f"Could not create report: {error}. Conversion will continue."
                        log("WARNING: " + report_warning)
                summary = converter.convert_folder(
                    root_dir, output_folder_name=output_folder, overwrite=overwrite,
                    report=report, progress=progress, quiet=True, target_format=target_fmt,
                    cancel_check=lambda: self.is_cancelled, on_log=log,
                )
                if report_warning:
                    summary.warnings.append(report_warning)
            output_dir = root_dir / output_folder
            self.msg_queue.put({"type": "complete", "summary": summary,
                                "report_file": str(report_path) if report_path else None,
                                "output_dir": str(output_dir if output_dir.is_dir() else root_dir),
                                "cancelled": summary.cancelled})
        except Exception as error:
            self.msg_queue.put({"type": "error", "error": converter.error_message(error)})

    def _cancel_conversion(self) -> None:
        if self.is_converting:
            self.is_cancelled = True
            self.status_label.config(text="Cancelling... finishing current file", foreground="#cc6600")
            self.cancel_btn.config(state=tk.DISABLED)

    def _process_queue(self) -> None:
        if self.close_requested and (self.worker is None or not self.worker.is_alive()):
            self.root.destroy()
            return
        try:
            # Bound each batch so Cancel and window events stay responsive for large folders.
            for _ in range(100):
                msg = self.msg_queue.get_nowait()
                kind = msg.get("type")
                if kind == "log":
                    text = msg["text"]
                    tag = "failed" if text.startswith(("FAILED", "WARNING")) else "info"
                    self._append_log(text, tag)
                elif kind == "progress":
                    index, total = msg["index"], msg["total"]
                    percent = int(index / total * 100) if total else 0
                    self.progress_bar["value"] = percent
                    self.count_label.config(text=f"{index} / {total} ({percent}%)")
                    if not self.is_cancelled:
                        self.status_label.config(text=f"Converting... {msg['source']}", foreground="#0066cc")
                elif kind == "complete":
                    self._handle_completion(msg)
                elif kind == "error":
                    self._set_running(False)
                    self.status_label.config(text="Conversion could not finish", foreground="#cc0000")
                    self._append_log(f"ERROR: {msg['error']}", "failed")
                    if not self.close_requested:
                        messagebox.showerror("Conversion Error", msg["error"], parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._process_queue)

    def _handle_completion(self, msg: dict) -> None:
        self._set_running(False)
        summary = msg["summary"]
        self.last_output_dir = Path(msg["output_dir"])
        self.open_btn.config(state=tk.NORMAL)
        processed = summary.converted + summary.skipped + summary.failed
        percent = int(processed / summary.found * 100) if summary.found else 0
        self.progress_bar["value"] = percent
        self.count_label.config(text=f"{processed} / {summary.found} ({percent}%)")
        if summary.cancelled:
            title, color, dialog = "Conversion cancelled", "#cc6600", messagebox.showwarning
        elif summary.failed or summary.warnings:
            title, color, dialog = "Finished with errors or warnings", "#cc6600", messagebox.showwarning
        elif not summary.found:
            title, color, dialog = "No HEIC / HEIF photos found", "#cc6600", messagebox.showinfo
        else:
            title, color, dialog = "Conversion completed successfully!", "#008800", messagebox.showinfo
        self.status_label.config(text=title, foreground=color)
        details = (f"{title}\n\nFound: {summary.found}\nConverted: {summary.converted}"
                   f"\nSkipped: {summary.skipped}\nFailed: {summary.failed}")
        if summary.errors:
            details += "\n\nFirst error:\n" + summary.errors[0]
        if summary.warnings:
            details += "\n\nWarning:\n" + summary.warnings[0]
        if msg.get("report_file"):
            details += "\n\nReport: " + msg["report_file"]
        self._append_log(title)
        if not self.close_requested:
            dialog("Conversion Result", details, parent=self.root)

    def _open_output_folder(self) -> None:
        folder = self.last_output_dir or self.last_root_dir
        open_in_file_manager(folder)

    def _on_close(self) -> None:
        if self.close_requested:
            return
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Quit", "Stop after the current photo and close?", parent=self.root):
                return
            self.close_requested = True
            self._cancel_conversion()
            self.status_label.config(text="Closing after the current file is saved...", foreground="#cc6600")
        else:
            self.root.destroy()


def launch_gui(initial_root: Path | None = None, initial_format: str = "png") -> int:
    root = tk.Tk()
    HEICConverterGUI(root, initial_root=initial_root, initial_format=initial_format)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(launch_gui())
