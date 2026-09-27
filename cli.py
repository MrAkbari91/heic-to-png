"""Command-line parsing and launch policy for HEIC Converter."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from convert_heic_to_png import (
    DEFAULT_FORMAT, SUPPORTED_FORMATS, ProgressCallback, application_root,
    convert_folder, error_message, validate_output_folder,
)

def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recursively convert HEIC/HEIF images to PNG, JPG, WEBP, BMP, TIFF, or GIF."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Folder to scan. Default: folder containing this script or executable.",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=SUPPORTED_FORMATS,
        default=DEFAULT_FORMAT,
        type=str.lower,
        help=f"Target image format: {', '.join(SUPPORTED_FORMATS)}. Default: {DEFAULT_FORMAT}.",
    )
    parser.add_argument(
        "--output-folder",
        default=None,
        help="Output folder created beside source files. Default: heic-<format> (e.g. heic-png, heic-jpg)",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace existing converted files."
    )
    parser.add_argument(
        "--no-report", action="store_true", help="Do not create a report file."
    )
    parser.add_argument(
        "--pause", action="store_true", help="Wait for Enter before closing."
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress conversion output and terminal progress.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable per-file progress output.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--gui", action="store_true", help="Launch Graphical User Interface (GUI)."
    )
    mode.add_argument(
        "--cli", action="store_true", help="Force command-line mode without GUI."
    )
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=4, help="Parallel conversions (1-16). Default: 4.")
    return parser.parse_args(argv)


def _main() -> int:
    """Run the CLI or GUI and return zero when all conversions succeed."""
    arguments = parse_arguments()

    # Determine whether to launch the GUI
    should_launch_gui = arguments.gui
    if not should_launch_gui and not arguments.cli and len(sys.argv) == 1:
        # If no arguments provided, launch GUI if a display is present or running frozen exe
        has_display = sys.platform in ("win32", "darwin") or bool(
            os.environ.get("DISPLAY")
        )
        if has_display:
            should_launch_gui = True

    if should_launch_gui:
        try:
            from gui import launch_gui

            return launch_gui(
                initial_root=arguments.root, initial_format=arguments.format,
                initial_output=arguments.output_folder, initial_overwrite=arguments.overwrite,
                initial_workers=arguments.workers
            )
        except Exception as gui_err:
            if arguments.gui:
                print(f"ERROR: Failed to launch GUI: {gui_err}", file=sys.stderr)
                return 1
            print(f"ERROR: Failed to launch GUI: {gui_err}. Run with --cli for terminal mode.", file=sys.stderr)
            return 1

    root = (
        arguments.root.expanduser().resolve()
        if arguments.root
        else application_root()
    )
    if not root.is_dir():
        print(f"ERROR: Folder does not exist: {root}", file=sys.stderr)
        return 2

    validate_output_folder(arguments.output_folder if arguments.output_folder is not None else f"heic-{arguments.format}")
    fmt = arguments.format.lower()
    report_file_name = f"heic-{fmt}-report.txt"
    report_path = root / report_file_name

    progress_callback: ProgressCallback | None = None
    if not arguments.quiet and not arguments.no_progress:

        def cli_progress(index: int, total: int, source: Path, status: str) -> None:
            percent = int((index / total) * 100) if total > 0 else 0
            print(
                f"[{index}/{total}] {percent}% {status.upper()}: {source.as_posix()}"
            )

        progress_callback = cli_progress
    elif arguments.no_progress and not arguments.quiet:
        progress_callback = lambda _index, _total, _source, _status: None

    report = None
    report_warning = None
    if not arguments.no_report:
        try:
            report = report_path.open("w", encoding="utf-8")
        except OSError as error:
            report_warning = f"Could not create report: {error}"
            print(f"WARNING: {report_warning}", file=sys.stderr)
    try:
        summary = convert_folder(
            root,
            output_folder_name=arguments.output_folder,
            overwrite=arguments.overwrite,
            progress=progress_callback,
            quiet=arguments.quiet,
            target_format=fmt, workers=arguments.workers,
            report=report,
        )
    finally:
        if report is not None:
            report.close()
    if report_warning:
        summary.warnings.append(report_warning)
    elif report is not None and not arguments.quiet:
        print(f"Report saved: {report_path}")

    if arguments.pause:
        input("\nPress Enter to close...")
    return 1 if summary.failed or summary.warnings else 0


def main() -> int:
    try:
        return _main()
    except KeyboardInterrupt:
        print("\nConversion interrupted.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        print(f"ERROR: {error_message(error)}", file=sys.stderr)
        return 1

