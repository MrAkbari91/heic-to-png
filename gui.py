"""Graphical User Interface for HEIC Converter.

Allows users to select input directories, choose target image formats
(PNG, JPG, JPEG, WEBP), monitor real-time conversion progress, and view logs.
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
from typing import Callable

from pillow_heif import register_heif_opener

import convert_heic_to_png as converter

SUPPORTED_FORMATS = ["PNG", "JPG", "JPEG", "WEBP"]


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
        self.root.geometry("640x660")
        self.root.minsize(580, 540)

        # Apply icon
        icon_path = find_icon_path()
        if icon_path and sys.platform == "win32":
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        # State
        self.initial_dir = (
            initial_root
            if initial_root and initial_root.is_dir()
            else converter.application_root()
        )
        self.root_path_var = tk.StringVar(value=str(self.initial_dir))
        self.format_var = tk.StringVar(value=initial_format.upper())
        self.output_folder_var = tk.StringVar(value=f"heic-{initial_format.lower()}")
        self.overwrite_var = tk.BooleanVar(value=False)
        self.save_report_var = tk.BooleanVar(value=True)

        self.is_converting = False
        self.is_cancelled = False
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
            text="Convert HEIC / HEIF photos recursively into PNG, JPG, JPEG, or WEBP.",
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

        for fmt in SUPPORTED_FORMATS:
            rb = ttk.Radiobutton(
                format_row,
                text=fmt,
                value=fmt,
                variable=self.format_var,
                command=self._on_format_changed,
            )
            rb.pack(side=tk.LEFT, padx=8)

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

    def _start_conversion(self) -> None:
        root_dir = Path(self.root_path_var.get().strip()).expanduser().resolve()
        if not root_dir.is_dir():
            messagebox.showerror(
                "Invalid Folder",
                f"Selected folder does not exist:\n{root_dir}",
                parent=self.root,
            )
            return

        target_fmt = self.format_var.get().lower()
        output_folder = self.output_folder_var.get().strip() or f"heic-{target_fmt}"
        overwrite = self.overwrite_var.get()
        save_report = self.save_report_var.get()

        self.is_converting = True
        self.is_cancelled = False
        self.start_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.open_btn.config(state=tk.DISABLED)
        self.progress_bar["value"] = 0
        self.log_text.delete("1.0", tk.END)
        self.status_label.config(text="Scanning for HEIC files...", foreground="#0066cc")
        self.count_label.config(text="Scanning...")

        self._append_log(f"Selected folder: {root_dir}")
        self._append_log(f"Target format: {target_fmt.upper()}")
        self._append_log(f"Output folder: {output_folder}")
        self._append_log("-" * 50)

        # Run conversion in background worker thread
        thread = threading.Thread(
            target=self._run_conversion_worker,
            args=(root_dir, target_fmt, output_folder, overwrite, save_report),
            daemon=True,
        )
        thread.start()

    def _run_conversion_worker(
        self,
        root_dir: Path,
        target_fmt: str,
        output_folder: str,
        overwrite: bool,
        save_report: bool,
    ) -> None:
        register_heif_opener()

        def progress_cb(index: int, total: int, source: Path, status: str) -> None:
            self.msg_queue.put(
                {
                    "type": "progress",
                    "index": index,
                    "total": total,
                    "source": str(source),
                    "status": status,
                }
            )

        def is_cancelled() -> bool:
            return self.is_cancelled

        report_file = (
            (root_dir / f"heic-{target_fmt}-report.txt") if save_report else None
        )

        try:
            if report_file:
                with report_file.open("w", encoding="utf-8") as rep:
                    summary = converter.convert_folder(
                        root=root_dir,
                        output_folder_name=output_folder,
                        overwrite=overwrite,
                        report=rep,
                        progress=progress_cb,
                        quiet=True,
                        target_format=target_fmt,
                        cancel_check=is_cancelled,
                    )
            else:
                summary = converter.convert_folder(
                    root=root_dir,
                    output_folder_name=output_folder,
                    overwrite=overwrite,
                    progress=progress_cb,
                    quiet=True,
                    target_format=target_fmt,
                    cancel_check=is_cancelled,
                )

            self.msg_queue.put(
                {
                    "type": "complete",
                    "summary": summary,
                    "report_file": str(report_file) if report_file else None,
                    "output_dir": str(root_dir / output_folder),
                    "cancelled": self.is_cancelled,
                }
            )
        except Exception as exc:
            self.msg_queue.put({"type": "error", "error": str(exc)})

    def _cancel_conversion(self) -> None:
        if self.is_converting:
            self.is_cancelled = True
            self.status_label.config(
                text="Cancelling... finishing current file", foreground="#cc6600"
            )
            self.cancel_btn.config(state=tk.DISABLED)

    def _process_queue(self) -> None:
        """Poll the thread-safe message queue and update GUI widgets."""
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                msg_type = msg.get("type")

                if msg_type == "progress":
                    index = msg["index"]
                    total = msg["total"]
                    status = msg["status"]
                    source = msg["source"]

                    percent = int((index / total) * 100) if total > 0 else 0
                    self.progress_bar["value"] = percent
                    self.count_label.config(text=f"{index} / {total} ({percent}%)")

                    status_tag = status.lower()
                    status_text = f"[{status.upper()}] {source}"
                    self._append_log(status_text, tag=status_tag)
                    self.status_label.config(
                        text=f"Converting... ({status.upper()})", foreground="#0066cc"
                    )

                elif msg_type == "complete":
                    self._handle_completion(msg)

                elif msg_type == "error":
                    self.is_converting = False
                    self.start_btn.config(state=tk.NORMAL)
                    self.cancel_btn.config(state=tk.DISABLED)
                    self.status_label.config(
                        text="Error during conversion!", foreground="#cc0000"
                    )
                    self._append_log(f"ERROR: {msg['error']}", tag="failed")
                    messagebox.showerror(
                        "Conversion Error",
                        f"An error occurred:\n{msg['error']}",
                        parent=self.root,
                    )

        except queue.Empty:
            pass

        self.root.after(100, self._process_queue)

    def _handle_completion(self, msg: dict) -> None:
        self.is_converting = False
        summary = msg["summary"]
        report_file = msg.get("report_file")
        self.last_output_dir = Path(msg["output_dir"])

        self.start_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.open_btn.config(state=tk.NORMAL)

        if msg.get("cancelled"):
            self.status_label.config(
                text="Conversion cancelled by user", foreground="#cc6600"
            )
            self._append_log("-" * 50)
            self._append_log(
                f"Cancelled. Converted: {summary.converted}, Skipped: {summary.skipped}, Failed: {summary.failed}"
            )
            messagebox.showwarning(
                "Cancelled",
                f"Conversion cancelled by user.\n\n"
                f"Converted: {summary.converted}\n"
                f"Skipped: {summary.skipped}\n"
                f"Failed: {summary.failed}",
                parent=self.root,
            )
        else:
            self.progress_bar["value"] = 100
            self.status_label.config(
                text="Conversion completed successfully!", foreground="#008800"
            )
            self._append_log("-" * 50)
            self._append_log(
                f"Done! Converted: {summary.converted}, Skipped: {summary.skipped}, Failed: {summary.failed}",
                tag="converted",
            )
            if report_file:
                self._append_log(f"Report saved: {report_file}")

            msg_box_text = (
                f"Conversion Complete!\n\n"
                f"Total HEIC files: {summary.found}\n"
                f"Converted: {summary.converted}\n"
                f"Skipped: {summary.skipped}\n"
                f"Failed: {summary.failed}"
            )
            if report_file:
                msg_box_text += f"\n\nReport saved:\n{report_file}"

            messagebox.showinfo("Finished", msg_box_text, parent=self.root)

    def _open_output_folder(self) -> None:
        if self.last_output_dir and self.last_output_dir.is_dir():
            open_in_file_manager(self.last_output_dir)
        else:
            root_dir = Path(self.root_path_var.get())
            if root_dir.is_dir():
                open_in_file_manager(root_dir)

    def _on_close(self) -> None:
        if self.is_converting:
            if messagebox.askyesno(
                "Quit",
                "A conversion is currently in progress. Do you really want to quit?",
                parent=self.root,
            ):
                self.is_cancelled = True
                self.root.destroy()
        else:
            self.root.destroy()


def launch_gui(initial_root: Path | None = None, initial_format: str = "png") -> int:
    """Initialize and run the HEIC Converter Tkinter window."""
    root = tk.Tk()
    app = HEICConverterGUI(
        root, initial_root=initial_root, initial_format=initial_format
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(launch_gui())
