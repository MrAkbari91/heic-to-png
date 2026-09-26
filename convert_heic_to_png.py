"""Find HEIC/HEIF images recursively and convert them to PNG, JPG, JPEG, or WEBP files.

Each source folder receives its own output directory (``heic-<format>`` by
default). The original image is never moved, changed, or deleted.
"""

from __future__ import annotations

__author__ = "Dhruv Akbari"
__email__ = "dhruvakbari303@gmail.com"
__version__ = "1.2.0"

import argparse
import inspect
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO

ProgressCallback = Callable[[int, int, Path, str], None]
CancelCallback = Callable[[], bool]

try:
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener
except ImportError as error:
    raise SystemExit(
        "Required packages are missing. Install them with: python -m pip install ."
    ) from error


HEIC_EXTENSIONS = {".heic", ".heif"}
SUPPORTED_FORMATS = ("png", "jpg", "jpeg", "webp")
DEFAULT_FORMAT = "png"
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
    excluded_names = {
        output_folder_name.casefold(),
        "heic-png",
        "heic-jpg",
        "heic-jpeg",
        "heic-webp",
    }
    for directory, folder_names, file_names in os.walk(root, onerror=on_error):
        # Editing this list tells os.walk not to enter old conversion results.
        folder_names[:] = [
            name
            for name in folder_names
            if name.casefold() not in excluded_names
            and not name.casefold().startswith("heic-")
        ]
        folders_scanned += 1
        current_folder = Path(directory)
        files.extend(
            current_folder / name
            for name in file_names
            if Path(name).suffix.casefold() in HEIC_EXTENSIONS
        )
    return files, folders_scanned


def prepare_image_for_format(image: Image.Image, target_format: str) -> tuple[Image.Image, str]:
    """Prepare PIL Image for saving in target format and return (image, pillow_format)."""
    fmt = target_format.lower().strip(".")
    if fmt in ("jpg", "jpeg"):
        pillow_format = "JPEG"
        if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
            alpha_image = image.convert("RGBA")
            background = Image.new("RGB", alpha_image.size, (255, 255, 255))
            background.paste(alpha_image, mask=alpha_image.split()[3])
            return background, pillow_format
        elif image.mode != "RGB":
            return image.convert("RGB"), pillow_format
        return image, pillow_format
    elif fmt == "webp":
        pillow_format = "WEBP"
        if image.mode not in {"RGB", "RGBA"}:
            return image.convert("RGBA" if "A" in image.getbands() else "RGB"), pillow_format
        return image, pillow_format
    else:  # PNG
        pillow_format = "PNG"
        if image.mode not in {"RGB", "RGBA"}:
            return image.convert("RGBA" if "A" in image.getbands() else "RGB"), pillow_format
        return image, pillow_format


def convert_one(source: Path, target: Path, target_format: str = "png") -> None:
    """Convert one image to target format and apply its EXIF camera orientation."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        corrected_image = ImageOps.exif_transpose(image)
        prepared_image, pillow_format = prepare_image_for_format(corrected_image, target_format)
        save_kwargs = {}
        if pillow_format in ("JPEG", "WEBP"):
            save_kwargs["quality"] = 95
        prepared_image.save(target, pillow_format, **save_kwargs)


def convert_folder(
    root: Path,
    output_folder_name: str | None = None,
    overwrite: bool = False,
    report: TextIO | None = None,
    progress: ProgressCallback | None = None,
    quiet: bool = False,
    target_format: str = DEFAULT_FORMAT,
    cancel_check: CancelCallback | None = None,
) -> ConversionSummary:
    """Convert all supported images below root and return a progress summary."""
    fmt = target_format.lower().strip(".")
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported format '{target_format}'. Choose from {SUPPORTED_FORMATS}"
        )

    actual_output_folder = (
        output_folder_name if output_folder_name is not None else f"heic-{fmt}"
    )
    ext = f".{fmt}"

    summary = ConversionSummary()

    def log(message: str) -> None:
        if not quiet:
            print(message)
        if report is not None:
            report.write(message + "\n")

    walk_errors: list[str] = []

    def on_walk_error(error: OSError) -> None:
        walk_errors.append(f"WARNING: Could not open {error.filename}: {error}")

    files, summary.folders_scanned = find_heic_files(
        root, actual_output_folder, on_walk_error
    )
    total = len(files)
    summary.found = total
    log(f"Scanning root folder: {root}")
    log(f"Folders scanned: {summary.folders_scanned}")
    log(f"Target format: {fmt.upper()}")
    log(f"HEIC/HEIF files found: {summary.found}")
    for error_message in walk_errors:
        log(error_message)

    for index, source in enumerate(files, start=1):
        if cancel_check is not None and cancel_check():
            log("Conversion cancelled by user.")
            break

        relative_source = source.relative_to(root)
        target = source.parent / actual_output_folder / f"{source.stem}{ext}"
        if target.exists() and not overwrite:
            summary.skipped += 1
            if report is not None:
                report.write(
                    f"SKIPPED ({fmt.upper()} already exists): {relative_source}\n"
                )
            if progress is not None:
                progress(index, total, relative_source, "skipped")
            elif not quiet:
                print(f"SKIPPED ({fmt.upper()} already exists): {relative_source}")
            continue
        try:
            sig = inspect.signature(convert_one)
            if "target_format" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                convert_one(source, target, target_format=fmt)
            elif len(sig.parameters) >= 3 or any(
                p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
            ):
                convert_one(source, target, fmt)
            else:
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
        description="Recursively convert HEIC/HEIF images to PNG, JPG, JPEG, or WEBP beside their source folders."
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
    parser.add_argument(
        "--gui", action="store_true", help="Launch Graphical User Interface (GUI)."
    )
    parser.add_argument(
        "--cli", action="store_true", help="Force command-line mode without GUI."
    )
    return parser.parse_args()


def gui_main() -> int:
    """Direct entry point for GUI launcher."""
    from gui import launch_gui

    return launch_gui()


def main() -> int:
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
                initial_root=arguments.root, initial_format=arguments.format
            )
        except Exception as gui_err:
            if arguments.gui:
                print(f"ERROR: Failed to launch GUI: {gui_err}", file=sys.stderr)
                return 1
            # Fall back to CLI if auto-detection failed

    root = (
        arguments.root.expanduser().resolve()
        if arguments.root
        else application_root()
    )
    if not root.is_dir():
        print(f"ERROR: Folder does not exist: {root}", file=sys.stderr)
        return 2

    register_heif_opener()
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

    if arguments.no_report:
        summary = convert_folder(
            root,
            output_folder_name=arguments.output_folder,
            overwrite=arguments.overwrite,
            progress=progress_callback,
            quiet=arguments.quiet,
            target_format=fmt,
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
                target_format=fmt,
            )
        if not arguments.quiet:
            print(f"Report saved: {report_path}")

    if arguments.pause or (getattr(sys, "frozen", False) and sys.platform == "win32"):
        input("\nPress Enter to close...")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
