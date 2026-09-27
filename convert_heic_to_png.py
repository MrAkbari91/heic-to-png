"""Convert HEIC/HEIF photos to common image formats without changing originals."""
from __future__ import annotations

__author__ = "Dhruv Akbari"
__email__ = "dhruvakbari303@gmail.com"
__version__ = "2.0.1"

import os
import sys
import tempfile
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, TextIO

from PIL import Image, ImageOps

ProgressCallback = Callable[[int, int, Path, str], None]
CancelCallback = Callable[[], bool]
LogCallback = Callable[[str], None]
HEIC_EXTENSIONS = {".heic", ".heif", ".hif"}
SUPPORTED_FORMATS = ("png", "jpg", "jpeg", "webp", "bmp", "tiff", "tif", "gif",
                     "ico", "tga", "ppm")
PILLOW_FORMATS = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP",
                  "bmp": "BMP", "tiff": "TIFF", "tif": "TIFF", "gif": "GIF",
                  "ico": "ICO", "tga": "TGA", "ppm": "PPM"}
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
    output_dirs: list[Path] = field(default_factory=list)


@dataclass
class ScanResult:
    files: list[Path] = field(default_factory=list)
    folders_scanned: int = 0
    warnings: list[str] = field(default_factory=list)
    cancelled: bool = False


def scan_sources(sources: Iterable[Path], output_folder_name: str,
                 cancel_check: CancelCallback | None = None) -> ScanResult:
    """Discover inputs once, deduplicating overlapping file/folder selections."""
    output = validate_output_folder(output_folder_name)
    result = ScanResult()
    seen: set[Path] = set()
    for item in sources:
        if cancel_check and cancel_check():
            break
        source = Path(item).expanduser().resolve()
        if source.is_dir():
            files, count = find_heic_files(
                source, output,
                lambda error: result.warnings.append(f"Could not scan {error.filename}: {error}"),
                cancel_check,
            )
            result.folders_scanned += count
        elif source.is_file() and source.suffix.casefold() in HEIC_EXTENSIONS:
            files = [source]
        else:
            result.warnings.append(f"Source is missing or is not a HEIC/HEIF image: {source}")
            files = []
        for photo in files:
            photo = photo.resolve()
            if photo not in seen:
                seen.add(photo)
                result.files.append(photo)
    result.files.sort(key=lambda path: str(path).casefold())
    result.cancelled = bool(cancel_check and cancel_check())
    return result


def plan_targets(files: list[Path], output: str, fmt: str) -> list[Path]:
    """Reserve unique output names before starting any parallel writes."""
    stems = Counter((str(p.parent).casefold(), p.stem.casefold()) for p in files)
    used: set[str] = set()
    targets = []
    for source in files:
        key = (str(source.parent).casefold(), source.stem.casefold())
        name = source.name if stems[key] > 1 else source.stem
        target = source.parent / output / f"{name}.{fmt}"
        count = 2
        while str(target).casefold() in used:
            target = source.parent / output / f"{name}-{count}.{fmt}"
            count += 1
        used.add(str(target).casefold())
        targets.append(target)
    return targets


def convert_files(files: list[Path], output_folder_name: str | None = None,
                  overwrite: bool = False, target_format: str = DEFAULT_FORMAT,
                  workers: int = 1, progress: ProgressCallback | None = None,
                  cancel_check: CancelCallback | None = None,
                  on_log: LogCallback | None = None) -> ConversionSummary:
    """Shared CLI/GUI batch engine. Callbacks run on the coordinating thread."""
    fmt = normalize_format(target_format)
    output = validate_output_folder(output_folder_name if output_folder_name is not None else f"heic-{fmt}")
    if not 1 <= workers <= 16:
        raise ValueError("Workers must be between 1 and 16.")
    files = sorted(set(Path(p).resolve() for p in files), key=lambda p: str(p).casefold())
    summary = ConversionSummary(found=len(files))
    def cancelled() -> bool:
        return bool(cancel_check and cancel_check())
    if cancelled():
        summary.cancelled = True
        return summary
    if not files:
        return summary
    initialize_heif()
    jobs = iter(zip(files, plan_targets(files, output, fmt)))

    def convert_job(source: Path, target: Path) -> tuple[str, str]:
        if target.is_file() and not overwrite:
            return "skipped", f"SKIPPED (already exists): {source}"
        try:
            convert_one(source, target, target_format=fmt)
            return "converted", f"OK: {source} -> {target}"
        except Exception as error:
            return "failed", f"FAILED: {source} -- {error_message(error)}"

    # Keep only `workers` futures outstanding so cancellation does not wait on a
    # queue containing the entire library. Running saves finish atomically.
    with ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {}

        def submit_next() -> None:
            if cancelled():
                return
            job = next(jobs, None)
            if job is not None:
                pending[executor.submit(convert_job, *job)] = job

        for _ in range(workers):
            submit_next()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                source, target = pending.pop(future)
                status, detail = future.result()
                setattr(summary, status, getattr(summary, status) + 1)
                if status == "failed":
                    summary.errors.append(detail)
                elif target.parent not in summary.output_dirs:
                    summary.output_dirs.append(target.parent)
                if on_log:
                    on_log(detail)
                if progress:
                    progress(summary.converted + summary.skipped + summary.failed,
                             summary.found, source, status)
            for _ in done:
                submit_next()
    summary.cancelled = cancelled() and summary.converted + summary.skipped + summary.failed < summary.found
    return summary


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
        from pillow_heif import register_heif_opener
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
    # Formats that do not support alpha channel
    if fmt in {"jpg", "jpeg", "bmp", "ppm"}:
        if has_alpha:
            with image.convert("RGBA") as rgba:
                background = Image.new("RGB", rgba.size, "white")
                with rgba.getchannel("A") as alpha:
                    background.paste(rgba, mask=alpha)
            return background, PILLOW_FORMATS[fmt]
        return image.convert("RGB"), PILLOW_FORMATS[fmt]
    # ICO format: max 256x256
    if fmt == "ico":
        img = image.convert("RGBA" if has_alpha else "RGB")
        img.thumbnail((256, 256), Image.LANCZOS)
        return img, PILLOW_FORMATS[fmt]
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
                if pillow_format == "ICO":
                    kwargs["sizes"] = [prepared.size]
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
                   on_log: LogCallback | None = None, workers: int = 1) -> ConversionSummary:
    fmt = normalize_format(target_format)
    output = validate_output_folder(output_folder_name if output_folder_name is not None else f"heic-{fmt}")
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Folder does not exist: {root}")

    def log(message: str) -> None:
        if not quiet:
            print(message, flush=True)
        if report is not None:
            report.write(message + "\n")
        if on_log is not None:
            on_log(message)

    # Announce scanning before touching a potentially large directory tree.
    log(f"Scanning root folder: {root}")
    scan = scan_sources([root], output, cancel_check)
    log(f"Folders scanned: {scan.folders_scanned}")
    log(f"Target format: {fmt.upper()}")
    log(f"HEIC/HEIF files found: {len(scan.files)}")
    for warning in scan.warnings:
        log(f"WARNING: {warning}")

    def detail(message: str) -> None:
        # Relative paths keep CLI reports readable.
        message = message.replace(str(root) + os.sep, "")
        if report is not None:
            report.write(message + "\n")
        if on_log is not None:
            on_log(message)
        if progress is None and not quiet:
            print(message, flush=True)

    def notify(index: int, total: int, source: Path, status: str) -> None:
        if progress:
            progress(index, total, source.relative_to(root), status)

    summary = convert_files(scan.files, output, overwrite, fmt, workers,
                            notify, cancel_check, detail)
    summary.folders_scanned = scan.folders_scanned
    summary.warnings = scan.warnings
    summary.cancelled = summary.cancelled or scan.cancelled
    if summary.cancelled:
        log("Conversion cancelled by user.")
    elif not summary.found:
        log("No HEIC/HEIF images found. Choose a folder containing .heic, .heif or .hif photos.")
    log(f"\nDone. Converted: {summary.converted}; skipped: {summary.skipped}; failed: {summary.failed}")
    return summary


# Keep existing script and installed entry points compatible.
def parse_arguments(argv: list[str] | None = None):
    from cli import parse_arguments as parse
    return parse(argv)


def gui_main() -> int:
    from gui import launch_gui
    return launch_gui()


def main() -> int:
    from cli import main as run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
