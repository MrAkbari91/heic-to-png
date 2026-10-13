"""Verify encoding controls using decoded pixels, real files and CLI processes."""
import random
import subprocess
import sys
from pathlib import Path

import pillow_heif
import pytest
from PIL import Image, ImageOps

import cli
import convert_heic_to_png as converter


@pytest.fixture
def photo(tmp_path):
    # Deterministic texture makes quality differences measurable without a camera fixture.
    rng = random.Random(42)
    source = tmp_path / "photo.heic"
    with Image.frombytes("RGB", (128, 96), rng.randbytes(128 * 96 * 3)) as image:
        pillow_heif.from_pillow(image).save(source, quality=95)
    return source


def decoded_pixels(path):
    converter.initialize_heif()
    with Image.open(path) as image:
        with ImageOps.exif_transpose(image) as corrected:
            with corrected.convert("RGB") as rgb:
                return rgb.size, rgb.tobytes()


@pytest.mark.parametrize("fmt", ["jpg", "jpeg", "webp"])
def test_quality_changes_real_output_size(photo, tmp_path, fmt):
    outputs = [tmp_path / f"quality-{quality}.{fmt}" for quality in (30, 95)]
    for quality, output in zip((30, 95), outputs):
        converter.convert_one(photo, output, fmt, encoding=converter.EncodingOptions(quality=quality))
        assert decoded_pixels(output)[0] == (128, 96)
    assert outputs[0].stat().st_size < outputs[1].stat().st_size
    if fmt in {"jpg", "jpeg"}:
        with Image.open(outputs[0]) as low, Image.open(outputs[1]) as high:
            assert sum(low.quantization[0]) > sum(high.quantization[0])


def test_png_compression_changes_size_without_changing_pixels(tmp_path):
    source = tmp_path / "source.png"
    with Image.new("RGBA", (128, 96), (20, 90, 130, 100)) as image:
        image.save(source)
        expected = image.tobytes()
    outputs = [tmp_path / f"level-{level}.png" for level in (0, 9)]
    for level, output in zip((0, 9), outputs):
        converter.convert_one(source, output, encoding=converter.EncodingOptions(png_compression=level))
        with Image.open(output) as image:
            assert image.mode == "RGBA"
            assert image.tobytes() == expected
    assert outputs[1].stat().st_size < outputs[0].stat().st_size


@pytest.mark.parametrize("effort", [1, 100])
def test_lossless_webp_preserves_decoded_heic_pixels(photo, tmp_path, effort):
    target = tmp_path / "lossless.webp"
    converter.convert_one(photo, target, "webp",
                          encoding=converter.EncodingOptions(quality=effort, webp_lossless=True))
    assert decoded_pixels(target) == decoded_pixels(photo)


def test_lossless_webp_preserves_transparent_pixel_colors(tmp_path):
    source = tmp_path / "alpha.png"
    target = tmp_path / "alpha.webp"
    with Image.frombytes("RGBA", (3, 1), bytes([90, 80, 70, 0, 10, 20, 30, 128, 5, 15, 25, 255])) as image:
        image.save(source)
        expected = image.tobytes()
    converter.convert_one(source, target, "webp", encoding=converter.EncodingOptions(webp_lossless=True))
    with Image.open(target) as image:
        assert image.convert("RGBA").tobytes() == expected


def test_parallel_batch_presets_reach_each_encoder_and_keep_skip_policy(photo, tmp_path):
    second = tmp_path / "second.heic"
    second.write_bytes(photo.read_bytes())
    original = photo.read_bytes()
    small = converter.resolve_encoding_options("small-file")
    high = converter.resolve_encoding_options("high-quality")
    first = converter.convert_files([photo, second], target_format="jpg", workers=2, encoding=small)
    assert first.converted == 2
    outputs = sorted((tmp_path / "heic-jpg").glob("*.jpg"))
    sizes = [p.stat().st_size for p in outputs]
    skipped = converter.convert_files([photo, second], target_format="jpg", workers=2, encoding=high)
    assert skipped.skipped == 2
    assert sizes == [p.stat().st_size for p in outputs]
    replaced = converter.convert_files([photo, second], target_format="jpg", workers=2,
                                       overwrite=True, encoding=high)
    assert replaced.converted == 2
    assert all(p.stat().st_size > size for p, size in zip(outputs, sizes))
    assert photo.read_bytes() == original


@pytest.mark.parametrize("settings", [
    {"quality": 0}, {"quality": 101}, {"quality": 85.5}, {"quality": True},
    {"png_compression": -1}, {"png_compression": 10}, {"png_compression": False},
    {"webp_lossless": "false"},
])
def test_invalid_api_options_are_rejected(settings):
    with pytest.raises(ValueError):
        converter.EncodingOptions(**settings)


def test_cli_explicit_controls_override_preset_regardless_of_order():
    for args in (["--preset", "small-file", "--quality", "92"],
                 ["--quality", "92", "--preset", "small-file"]):
        options = cli.parse_arguments(["--format", "jpeg", *args]).encoding
        assert options.quality == 92
    assert cli.parse_arguments(["--preset", "small-file", "--png-compression", "0"]).encoding.png_compression == 0


@pytest.mark.parametrize("flags", [
    ["--format", "jpg", "--quality", "0"],
    ["--format", "webp", "--quality", "101"],
    ["--png-compression", "10"],
    ["--quality", "85"],
    ["--format", "jpg", "--webp-lossless"],
    ["--format", "webp", "--png-compression", "3"],
])
def test_invalid_cli_settings_fail_before_creating_files(tmp_path, flags):
    result = subprocess.run([sys.executable, str(Path(converter.__file__)), "--cli",
                             "--root", str(tmp_path), *flags], capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "error:" in result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("fmt,flags,description", [
    ("jpg", ["--preset", "small-file", "--quality", "91"], "JPEG quality: 91/100"),
    ("png", ["--png-compression", "0"], "compression level: 0/9"),
    ("webp", ["--webp-lossless", "--quality", "80"], "compression effort: 80/100"),
])
def test_cli_real_encoding_and_report(photo, fmt, flags, description):
    result = subprocess.run([sys.executable, str(Path(converter.__file__)), "--cli",
                             "--root", str(photo.parent), "--format", fmt, *flags],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert description in result.stdout
    assert description in (photo.parent / f"heic-{fmt}-report.txt").read_text(encoding="utf-8")
    output = photo.parent / f"heic-{fmt}" / f"photo.{fmt}"
    if fmt in {"png", "webp"}:
        assert decoded_pixels(output) == decoded_pixels(photo)
    else:
        expected = photo.parent / "expected.jpg"
        converter.convert_one(photo, expected, "jpg", encoding=converter.EncodingOptions(quality=91))
        assert output.read_bytes() == expected.read_bytes()


def test_cli_gui_handoff_preserves_encoding_options(monkeypatch):
    import gui
    received = {}
    monkeypatch.setattr(sys, "argv", ["converter", "--gui", "--format", "webp",
                                     "--preset", "balanced", "--webp-lossless"])
    monkeypatch.setattr(gui, "launch_gui", lambda **kwargs: received.update(kwargs) or 0)
    assert cli.main() == 0
    assert received["initial_encoding"] == converter.EncodingOptions(quality=85, webp_lossless=True)
