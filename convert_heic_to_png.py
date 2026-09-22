"""Find HEIC/HEIF images recursively and convert them to PNG files.

Each source folder receives its own output directory (``heic-png`` by
default). The original image is never moved, changed, or deleted.
"""

from __future__ import annotations

__author__ = "Dhruv Akbari"
__email__ = "dhruvakbari303@gmail.com"
__version__ = "1.1.0"

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO

ProgressCallback = Callable[[int, int, Path, str], None]

try:
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener
except ImportError as error:
    raise SystemExit(
        "Required packages are missing. Install them with: python -m pip install ."
    ) from error


HEIC_EXTENSIONS = {".heic", ".heif"}
DEFAULT_OUTPUT_FOLDER = "heic-png"
DEFAULT_REPORT_FILE = "heic-png-report.txt"


@dataclass
class ConversionSummary:
    """Counters returned after a complete folder scan."""

    folders_scanned: int = 0
    found: int = 0
    converted: int = 0
    skipped: int = 0
    failed: int = 0


def application_root() -> Path:
    """Return the folder containing this script or the packaged executable."""
    executable_or_script = sys.executable if getattr(sys, "frozen", False) else __file__
    return Path(executable_or_script).resolve().parent


def find_heic_files(
    root: Path,
    output_folder_name: str,
    on_error: Callable[[OSError], None],
) -> tuple[list[Path], int]:
    """Find input files while excluding generated output folders."""
    files: list[Path] = []
    folders_scanned = 0
    for directory, folder_names, file_names in os.walk(root, onerror=on_error):
        # Editing this list tells os.walk not to enter old conversion results.
        folder_names[:] = [
            name for name in folder_names if name.casefold() != output_folder_name.casefold()
        ]
        folders_scanned += 1
        current_folder = Path(directory)
        files.extend(
            current_folder / name
            for name in file_names
            if Path(name).suffix.casefold() in HEIC_EXTENSIONS
        )
    return files, folders_scanned


def convert_one(source: Path, target: Path) -> None:
    """Convert one image to PNG and apply its EXIF camera orientation."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        corrected_image = ImageOps.exif_transpose(image)
        if corrected_image.mode not in {"RGB", "RGBA"}:
            corrected_image = corrected_image.convert(
                "RGBA" if "A" in corrected_image.getbands() else "RGB"
            )
        corrected_image.save(target, "PNG")


def convert_folder(
    root: Path,
    output_folder_name: str = DEFAULT_OUTPUT_FOLDER,
    overwrite: bool = False,
    report: TextIO | None = None,
    progress: ProgressCallback | None = None,
    quiet: bool = False,
) -> ConversionSummary:
    """Convert all supported images below root and return a progress summary."""
    summary = ConversionSummary()

    def log(message: str) -> None:
        if not quiet:
            print(message)
        if report is not None:
            report.write(message + "\n")

    walk_errors: list[str] = []

    def on_walk_error(error: OSError) -> None:
        walk_errors.append(f"WARNING: Could not open {error.filename}: {error}")

    files, summary.folders_scanned = find_heic_files(root, output_folder_name, on_walk_error)
    total = len(files)
    summary.found = total
    log(f"Scanning root folder: {root}")
    log(f"Folders scanned: {summary.folders_scanned}")
    log(f"HEIC/HEIF files found: {summary.found}")
    for error_message in walk_errors:
        log(error_message)

    for index, source in enumerate(files, start=1):
        relative_source = source.relative_to(root)
        target = source.parent / output_folder_name / f"{source.stem}.png"
        if target.exists() and not overwrite:
            summary.skipped += 1
            if report is not None:
                report.write(f"SKIPPED (PNG already exists): {relative_source}\n")
            if progress is not None:
                progress(index, total, relative_source, "skipped")
            elif not quiet:
                print(f"SKIPPED (PNG already exists): {relative_source}")
            continue
        try:
            convert_one(source, target)
            summary.converted += 1
            if report is not None:
                report.write(f"OK: {relative_source}\n")
            if progress is not None:
                progress(index, total, relative_source, "converted")
            elif not quiet:
                print(f"OK: {relative_source}")
        except Exception as error:
            summary.failed += 1
            if report is not None:
                report.write(f"FAILED: {relative_source} -- {error}\n")
            if progress is not None:
                progress(index, total, relative_source, "failed")
            elif not quiet:
                print(f"FAILED: {relative_source} -- {error}")

    log(
        "\nDone. "
        f"Converted: {summary.converted}; skipped: {summary.skipped}; failed: {summary.failed}"
    )
    return summary


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recursively convert HEIC/HEIF images to PNG beside their source folders."
    )
    parser.add_argument(
        "--root", type=Path, default=application_root(),
        help="Folder to scan. Default: folder containing this script or executable.",
    )
    parser.add_argument(
        "--output-folder", default=DEFAULT_OUTPUT_FOLDER,
        help=f"Output folder created beside source files. Default: {DEFAULT_OUTPUT_FOLDER}",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing PNG files.")
    parser.add_argument("--no-report", action="store_true", help="Do not create a report file.")
    parser.add_argument("--pause", action="store_true", help="Wait for Enter before closing.")
    parser.add_argument("--quiet", action="store_true", help="Suppress conversion output and terminal progress.")
    parser.add_argument("--no-progress", action="store_true", help="Disable per-file progress output.")
    return parser.parse_args()


def main() -> int:
    """Run the CLI and return zero when all conversions succeed."""
    arguments = parse_arguments()
    root = arguments.root.expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: Folder does not exist: {root}", file=sys.stderr)
        return 2

    register_heif_opener()
    report_path = root / DEFAULT_REPORT_FILE

    progress_callback: ProgressCallback | None = None
    if not arguments.quiet and not arguments.no_progress:
        def cli_progress(index: int, total: int, source: Path, status: str) -> None:
            percent = int((index / total) * 100) if total > 0 else 0
            print(f"[{index}/{total}] {percent}% {status.upper()}: {source.as_posix()}")

        progress_callback = cli_progress
    elif arguments.no_progress and not arguments.quiet:
        progress_callback = lambda _index, _total, _source, _status: None

    if arguments.no_report:
        summary = convert_folder(
            root,
            output_folder_name=arguments.output_folder,
            overwrite=arguments.overwrite,
            progress=progress_callback,
            quiet=arguments.quiet,
        )
    else:
        with report_path.open("w", encoding="utf-8") as report:
            summary = convert_folder(
                root,
                output_folder_name=arguments.output_folder,
                overwrite=arguments.overwrite,
                report=report,
                progress=progress_callback,
                quiet=arguments.quiet,
            )
        if not arguments.quiet:
            print(f"Report saved: {report_path}")

    if arguments.pause or (getattr(sys, "frozen", False) and sys.platform == "win32"):
        input("\nPress Enter to close...")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
