"""Shared-engine and command-line behavior, including real process exit codes."""
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from PIL import Image
import pillow_heif

import convert_heic_to_png as converter


def make_photo(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    pillow_heif.from_pillow(Image.new("RGB", (32, 24), "teal")).save(path)
    return path


def run_cli(*arguments):
    return subprocess.run(
        [sys.executable, str(Path(converter.__file__)), "--cli", *map(str, arguments)],
        capture_output=True, text=True, timeout=30,
    )


def test_overlapping_sources_are_deduplicated_and_outputs_excluded(tmp_path):
    photo = make_photo(tmp_path / "nested" / "photo.HEIF")
    make_photo(tmp_path / "heic-png" / "ignored.heic")
    result = converter.scan_sources([tmp_path, photo.parent, photo], "heic-png")
    assert result.files == [photo]
    assert not result.warnings


def test_missing_and_unsupported_sources_are_reported(tmp_path):
    other = tmp_path / "other.txt"
    other.touch()
    scan = converter.scan_sources([tmp_path / "missing", other], "output")
    assert not scan.files
    assert len(scan.warnings) == 2


def test_parallel_name_collisions_have_distinct_readable_outputs(tmp_path):
    photos = [make_photo(tmp_path / name) for name in ("same.heic", "same.heif", "same.heic.heif")]
    originals = [p.read_bytes() for p in photos]
    progress = []
    summary = converter.convert_files(photos, workers=4, progress=lambda *event: progress.append(event))
    assert summary.converted == 3
    assert [event[0] for event in progress] == [1, 2, 3]
    outputs = list((tmp_path / "heic-png").glob("*.png"))
    assert len(outputs) == 3
    for output in outputs:
        with Image.open(output) as image:
            assert image.size == (32, 24)
    assert converter.convert_files(photos, workers=4).skipped == 3
    assert originals == [p.read_bytes() for p in photos]


def test_cancel_only_finishes_active_jobs(tmp_path, monkeypatch):
    photos = []
    for index in range(20):
        photo = tmp_path / f"{index}.heic"
        photo.touch()
        photos.append(photo)
    stop = threading.Event()
    barrier = threading.Barrier(2)
    calls = []

    def convert(source, target, **_kwargs):
        calls.append(source)
        barrier.wait(timeout=5)
        stop.set()

    monkeypatch.setattr(converter, "convert_one", convert)
    summary = converter.convert_files(photos, workers=2, cancel_check=stop.is_set)
    assert summary.cancelled
    assert len(calls) == summary.converted == 2


def test_cli_real_conversion_skip_and_overwrite(tmp_path):
    source = make_photo(tmp_path / "photo.heic")
    original = source.read_bytes()
    args = ("--root", tmp_path, "--format", "jpg", "--workers", 2)
    first = run_cli(*args)
    assert first.returncode == 0, first.stderr
    assert "Scanning root folder" in first.stdout
    assert "CONVERTED" in first.stdout
    assert (tmp_path / "heic-jpg-report.txt").is_file()
    assert "SKIPPED" in run_cli(*args).stdout
    assert "CONVERTED" in run_cli(*args, "--overwrite").stdout
    with Image.open(tmp_path / "heic-jpg" / "photo.jpg") as image:
        assert image.size == (32, 24)
    assert source.read_bytes() == original


def test_cli_empty_folder_explains_next_step(tmp_path):
    result = run_cli("--root", tmp_path, "--no-report")
    assert result.returncode == 0
    assert "No HEIC/HEIF images found" in result.stdout


def test_cli_bad_input_returns_failure(tmp_path):
    (tmp_path / "bad.heic").write_bytes(b"bad")
    result = run_cli("--root", tmp_path, "--no-report")
    assert result.returncode == 1
    assert "FAILED" in result.stdout


def test_cli_invalid_output_does_not_create_report(tmp_path):
    result = run_cli("--root", tmp_path, "--output-folder", "../outside")
    assert result.returncode != 0
    assert "folder name" in result.stderr
    assert not list(tmp_path.iterdir())


def test_cli_report_failure_still_converts(tmp_path):
    make_photo(tmp_path / "photo.heic")
    (tmp_path / "heic-png-report.txt").mkdir()
    result = run_cli("--root", tmp_path)
    assert result.returncode == 1
    assert "Could not create report" in result.stderr
    assert (tmp_path / "heic-png" / "photo.png").is_file()


def test_cli_quiet_and_no_progress(tmp_path):
    make_photo(tmp_path / "photo.heic")
    quiet = run_cli("--root", tmp_path, "--quiet", "--no-report")
    assert quiet.returncode == 0
    assert quiet.stdout == ""
    normal = run_cli("--root", tmp_path, "--no-progress", "--no-report")
    assert "Done." in normal.stdout
    assert "[1/1]" not in normal.stdout


@pytest.mark.parametrize("flags", [("--gui",), ("--workers", "0"), ("--workers", "17")])
def test_cli_rejects_conflicting_mode_and_invalid_workers(flags):
    result = run_cli(*flags)
    assert result.returncode == 2


def test_ico_large_photo_is_bounded(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (800, 600), "navy").save(source)
    target = tmp_path / "photo.ico"
    converter.convert_one(source, target, "ico")
    with Image.open(target) as image:
        assert image.size == (256, 192)
