"""Convert HEIC/HEIF photos to common image formats without changing originals."""
from __future__ import annotations

__author__ = "Dhruv Akbari"
__email__ = "dhruvakbari303@gmail.com"
__version__ = "1.2.1"

import argparse
import os
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, TextIO

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

ProgressCallback = Callable[[int, int, Path, str], None]
CancelCallback = Callable[[], bool]
LogCallback = Callable[[str], None]
HEIC_EXTENSIONS = {".heic", ".heif", ".hif"}
SUPPORTED_FORMATS = ("png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif", "gif")
PILLOW_FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP",
                  "bmp": "BMP", "tiff": "TIFF", "tif": "TIFF", "gif": "GIF"}
DEFAULT_FORMAT = "png"
DEFAULT_OUTPUT_FOLDER = "heic-png"
DEFAULT_REPORT_FILE = "heic-png-report.txt"


@dataclass
class ConversionSummary:
    folders_scanned: int = 0
    found: int = 0
    converted: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def application_root() -> Path:
    source = sys.executable if getattr(sys, "frozen", False) else __file__
    return Path(source).resolve().parent


def error_message(error: Exception) -> str:
    text = str(error)
    if text.startswith("Windows could not load the HEIC decoder."):
        return text
    if "Application Control" in text or "DLL load failed" in text:
        return ("Windows could not load the HEIC decoder. "
                "If the executable is blocked, use run_gui.bat from the source folder "
                "with the installed Python environment. On a managed PC, ask your "
                "administrator to approve the application. Details: " + text)
    return text or type(error).__name__


def initialize_heif() -> None:
    try:
        register_heif_opener()
    except Exception as error:
        raise RuntimeError(error_message(error)) from error


def normalize_format(target_format: str) -> str:
    fmt = target_format.lower().strip().lstrip(".")
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format '{target_format}'. Choose from {', '.join(SUPPORTED_FORMATS)}")
    return fmt


def validate_output_folder(name: str) -> str:
    name = name.strip()
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    if (not name or name in {".", ".."} or name.endswith((".", " "))
            or any(c in name for c in '<>:"/\\|?*')
            or any(ord(c) < 32 for c in name)
            or name.split(".")[0].upper() in reserved):
        raise ValueError("Output subfolder must be a single valid folder name, for example heic-png.")
    return name


def find_heic_files(root: Path, output_folder_name: str, on_error: Callable[[OSError], None],
                    cancel_check: CancelCallback | None = None) -> tuple[list[Path], int]:
    files: list[Path] = []
    scanned = 0
    excluded = {output_folder_name.casefold(), *(f"heic-{fmt}" for fmt in SUPPORTED_FORMATS)}
    for directory, folders, names in os.walk(root, onerror=on_error):
        if cancel_check and cancel_check():
            break
        folders[:] = sorted(n for n in folders if n.casefold() not in excluded)
        scanned += 1
        files.extend(Path(directory) / n for n in sorted(names)
                     if Path(n).suffix.casefold() in HEIC_EXTENSIONS)
    return files, scanned


def prepare_image_for_format(image: Image.Image, target_format: str) -> tuple[Image.Image, str]:
    fmt = normalize_format(target_format)
    has_alpha = "A" in image.getbands() or "transparency" in image.info
    if fmt in {"jpg", "jpeg", "bmp"}:
        if has_alpha:
            rgba = image.convert("RGBA")
            background = Image.new("RGB", rgba.size, "white")
            background.paste(rgba, mask=rgba.getchannel("A"))
            return background, PILLOW_FORMATS[fmt]
        return image.convert("RGB"), PILLOW_FORMATS[fmt]
    return image.convert("RGBA" if has_alpha else "RGB"), PILLOW_FORMATS[fmt]


def convert_one(source: Path, target: Path, target_format: str = "png") -> None:
    """Decode a photo and atomically replace its output only after a complete save."""
    fmt = normalize_format(target_format)
    initialize_heif()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with Image.open(source) as image:
            corrected = ImageOps.exif_transpose(image)
            prepared, pillow_format = prepare_image_for_format(corrected, fmt)
            try:
                kwargs = {"quality": 95} if pillow_format in {"JPEG", "WEBP"} else {}
                if image.info.get("icc_profile") and pillow_format in {"PNG", "JPEG", "WEBP", "TIFF"}:
                    kwargs["icc_profile"] = image.info["icc_profile"]
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".heic-", suffix=".tmp", delete=False) as temp:
                    temp_path = Path(temp.name)
                prepared.save(temp_path, pillow_format, **kwargs)
                os.replace(temp_path, target)
            finally:
                prepared.close()
                corrected.close()
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def convert_folder(root: Path, output_folder_name: str | None = None, overwrite: bool = False,
                   report: TextIO | None = None, progress: ProgressCallback | None = None,
                   quiet: bool = False, target_format: str = DEFAULT_FORMAT,
                   cancel_check: CancelCallback | None = None,
                   on_log: LogCallback | None = None) -> ConversionSummary:
    fmt = normalize_format(target_format)
    output = validate_output_folder(output_folder_name if output_folder_name is not None else f"heic-{fmt}")
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Folder does not exist: {root}")
    initialize_heif()
    summary = ConversionSummary()

    def log(message: str) -> None:
        if not quiet:
            print(message)
        if report is not None:
            report.write(message + "\n")
        if on_log is not None:
            on_log(message)

    def walk_error(error: OSError) -> None:
        summary.warnings.append(f"Could not scan {error.filename}: {error}")

    files, summary.folders_scanned = find_heic_files(root, output, walk_error, cancel_check)
    summary.found = len(files)
    log(f"Scanning root folder: {root}")
    log(f"Folders scanned: {summary.folders_scanned}")
    log(f"Target format: {fmt.upper()}")
    log(f"HEIC/HEIF files found: {summary.found}")
    for warning in summary.warnings:
        log(f"WARNING: {warning}")

    # Both photo.heic and photo.heif may exist beside each other.
    stems = Counter((str(p.parent).casefold(), p.stem.casefold()) for p in files)
    used_targets: set[str] = set()
    targets = []
    for source in files:
        name = source.name if stems[(str(source.parent).casefold(), source.stem.casefold())] > 1 else source.stem
        target = source.parent / output / f"{name}.{fmt}"
        count = 2
        while str(target).casefold() in used_targets:
            target = source.parent / output / f"{name}-{count}.{fmt}"
            count += 1
        used_targets.add(str(target).casefold())
        targets.append(target)

    for index, (source, target) in enumerate(zip(files, targets), start=1):
        if cancel_check and cancel_check():
            summary.cancelled = True
            break
        relative = source.relative_to(root)
        status = "converted"
        if target.exists() and not overwrite:
            summary.skipped += 1
            status = "skipped"
            detail = f"SKIPPED ({fmt.upper()} already exists): {relative}"
        else:
            try:
                convert_one(source, target, target_format=fmt)
                summary.converted += 1
                detail = f"OK: {relative}"
            except Exception as error:
                summary.failed += 1
                status = "failed"
                detail = f"FAILED: {relative} -- {error_message(error)}"
                summary.errors.append(detail)
        if report is not None:
            report.write(detail + "\n")
        if on_log is not None:
            on_log(detail)
        if progress is not None:
            progress(index, len(files), relative, status)
        elif not quiet:
            print(detail)
    if cancel_check and cancel_check() and summary.converted + summary.skipped + summary.failed < summary.found:
        summary.cancelled = True
    if cancel_check and cancel_check() and not files:
        summary.cancelled = True
    if summary.cancelled:
        log("Conversion cancelled by user.")
    log(f"\nDone. Converted: {summary.converted}; skipped: {summary.skipped}; failed: {summary.failed}")
    return summary


def parse_arguments() -> argparse.Namespace:
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

    if arguments.pause:
        input("\nPress Enter to close...")
    return 1 if summary.failed or summary.warnings else 0


def main() -> int:
    try:
        return _main()
    except (OSError, ValueError, RuntimeError, ImportError) as error:
        print(f"ERROR: {error_message(error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
