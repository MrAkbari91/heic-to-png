from pathlib import Path
import tkinter as tk
from PIL import Image

import convert_heic_to_png as converter
from convert_heic_to_png import (
    convert_folder,
    convert_one,
    parse_arguments,
    prepare_image_for_format,
    SUPPORTED_FORMATS,
)
import gui


def test_prepare_image_for_format_handles_jpeg_transparency() -> None:
    # Transparent image
    rgba_image = Image.new("RGBA", (20, 20), (255, 0, 0, 128))
    prepared_jpg, fmt_jpg = prepare_image_for_format(rgba_image, "jpg")
    assert fmt_jpg == "JPEG"
    assert prepared_jpg.mode == "RGB"

    prepared_jpeg, fmt_jpeg = prepare_image_for_format(rgba_image, "jpeg")
    assert fmt_jpeg == "JPEG"
    assert prepared_jpeg.mode == "RGB"


def test_prepare_image_for_format_preserves_png_and_webp_alpha() -> None:
    rgba_image = Image.new("RGBA", (20, 20), (0, 255, 0, 100))
    prepared_png, fmt_png = prepare_image_for_format(rgba_image, "png")
    assert fmt_png == "PNG"
    assert prepared_png.mode == "RGBA"

    prepared_webp, fmt_webp = prepare_image_for_format(rgba_image, "webp")
    assert fmt_webp == "WEBP"
    assert prepared_webp.mode == "RGBA"


def test_convert_one_supports_all_formats(tmp_path: Path) -> None:
    source_img = tmp_path / "sample.png"
    Image.new("RGBA", (15, 15), (0, 100, 200, 255)).save(source_img, "PNG")

    for fmt in SUPPORTED_FORMATS:
        target = tmp_path / f"output.{fmt}"
        convert_one(source_img, target, target_format=fmt)
        assert target.exists()
        with Image.open(target) as img:
            assert img.size == (15, 15)


def test_convert_folder_with_jpg_creates_heic_jpg_folder(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "sample.heic"
    source.write_bytes(b"dummy_data")

    def fake_convert(src: Path, tgt: Path, target_format: str = "png") -> None:
        tgt.parent.mkdir(parents=True, exist_ok=True)
        tgt.write_text(f"converted to {target_format}")

    monkeypatch.setattr("convert_heic_to_png.convert_one", fake_convert)

    summary = convert_folder(tmp_path, target_format="jpg")

    assert summary.found == 1
    assert summary.converted == 1
    assert summary.skipped == 0
    assert summary.failed == 0

    expected_file = tmp_path / "heic-jpg" / "sample.jpg"
    assert expected_file.exists()
    assert expected_file.read_text() == "converted to jpg"


def test_convert_folder_cancellation(tmp_path: Path, monkeypatch) -> None:
    for i in range(3):
        (tmp_path / f"photo{i}.heic").write_bytes(b"data")

    def fake_convert(src: Path, tgt: Path, **kwargs) -> None:
        tgt.parent.mkdir(parents=True, exist_ok=True)
        tgt.touch()

    monkeypatch.setattr("convert_heic_to_png.convert_one", fake_convert)

    cancelled = False

    def cancel_after_first() -> bool:
        return cancelled

    def progress_callback(index: int, total: int, source: Path, status: str) -> None:
        nonlocal cancelled
        if index == 1:
            cancelled = True

    summary = convert_folder(
        tmp_path,
        target_format="webp",
        progress=progress_callback,
        cancel_check=cancel_after_first,
    )

    # First file converted, then cancelled before completing all 3
    assert summary.found == 3
    assert summary.converted == 1


def test_parse_arguments_format_and_flags(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["convert_heic_to_png.py", "--format", "WEBP", "--gui"])
    args = parse_arguments()
    assert args.format == "webp"
    assert args.gui is True
    assert args.cli is False


def test_gui_find_icon_path() -> None:
    icon_path = gui.find_icon_path()
    assert icon_path is not None
    assert icon_path.name == "heic_to_any.ico"
    assert icon_path.exists()
