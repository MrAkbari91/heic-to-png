from pathlib import Path
from unittest.mock import Mock
import queue
import threading
import time

import pytest
from PIL import Image
import pillow_heif
import convert_heic_to_png as converter
import gui


@pytest.fixture
def heif_photo(tmp_path):
    photo = tmp_path / "photo.heic"
    pillow_heif.from_pillow(Image.new("RGB", (32, 24), (80, 160, 200))).save(photo, quality=90)
    return photo


@pytest.mark.parametrize("fmt", converter.SUPPORTED_FORMATS)
@pytest.mark.parametrize("extension", [".heic", ".heif"])
def test_real_heif_conversion(heif_photo, tmp_path, fmt, extension):
    source = heif_photo.with_suffix(extension)
    if source != heif_photo:
        source.write_bytes(heif_photo.read_bytes())
    target = tmp_path / "output" / f"photo.{fmt}"
    converter.convert_one(source, target, fmt)
    with Image.open(target) as result:
        result.load()
        assert result.size == (32, 24)
        assert result.format == converter.PILLOW_FORMATS[fmt]
    assert source.read_bytes() == heif_photo.read_bytes()


def test_scanner_keeps_heic_originals(tmp_path):
    folder = tmp_path / "heic-originals"
    folder.mkdir()
    (folder / "photo.HEIF").touch()
    for name in ("heic-png", "custom-output"):
        output = tmp_path / name
        output.mkdir()
        (output / "old.heic").touch()
    found, _ = converter.find_heic_files(tmp_path, "custom-output", lambda e: None)
    assert found == [folder / "photo.HEIF"]


def test_cancel_stops_scan(tmp_path):
    (tmp_path / "photo.heic").touch()
    summary = converter.convert_folder(tmp_path, cancel_check=lambda: True, quiet=True)
    assert summary.cancelled
    assert summary.folders_scanned == 0
    assert summary.converted == 0


def test_failed_save_preserves_existing_output_and_removes_temp(heif_photo, tmp_path, monkeypatch):
    target = tmp_path / "photo.png"
    target.write_bytes(b"previous-output")
    def broken_save(self, path, *args, **kwargs):
        Path(path).write_bytes(b"partial-image")
        raise OSError("Disk full")
    monkeypatch.setattr(Image.Image, "save", broken_save)
    with pytest.raises(OSError, match="Disk full"):
        converter.convert_one(heif_photo, target)
    assert target.read_bytes() == b"previous-output"
    assert not list(tmp_path.glob(".heic-*.tmp"))


def test_same_stem_sources_have_distinct_outputs(heif_photo, tmp_path):
    (tmp_path / "photo.heif").write_bytes(heif_photo.read_bytes())
    summary = converter.convert_folder(tmp_path, target_format="jpg", quiet=True)
    assert summary.converted == 2
    assert len(list((tmp_path / "heic-jpg").glob("*.jpg"))) == 2
    assert converter.convert_folder(tmp_path, target_format="jpg", quiet=True).skipped == 2


@pytest.mark.parametrize("name", ["..", "../outside", "C:\\output", "one/two", "CON", "NUL.txt", "bad?"])
def test_invalid_output_folder_is_rejected(tmp_path, name):
    with pytest.raises(ValueError, match="folder name"):
        converter.convert_folder(tmp_path, output_folder_name=name)


def test_error_details_reach_gui_log(tmp_path):
    (tmp_path / "broken.heic").write_bytes(b"not an image")
    logs = []
    summary = converter.convert_folder(tmp_path, quiet=True, on_log=logs.append)
    assert summary.failed == 1
    assert "broken.heic" in summary.errors[0]
    assert any("FAILED:" in line and "cannot identify image" in line for line in logs)


@pytest.fixture(scope="module")
def tk_root():
    import os
    import sys
    import tkinter as tk
    if sys.platform not in {"win32", "darwin"} and not os.environ.get("DISPLAY"):
        pytest.skip("GUI requires a display; use xvfb-run on Linux")
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app(tmp_path, monkeypatch, tk_root):
    import tkinter as tk
    root = tk.Toplevel(tk_root)
    root.withdraw()
    destroy = root.destroy
    for method in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(gui.messagebox, method, Mock())
    instance = gui.HEICConverterGUI(root, initial_root=tmp_path)
    yield instance
    if instance.worker and instance.worker.is_alive():
        instance.is_cancelled = True
        instance.worker.join(timeout=15)
    try:
        destroy()
    except tk.TclError:
        pass


def drain_worker(app):
    deadline = time.monotonic() + 15
    while app.is_converting and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    assert not app.is_converting


def test_gui_converts_real_photo(app, heif_photo):
    app.format_var.set("WEBP")
    app._on_format_changed()
    app.start_btn.invoke()
    drain_worker(app)
    target = heif_photo.parent / "heic-webp" / "photo.webp"
    with Image.open(target) as image:
        assert image.size == (32, 24)
    assert "successfully" in app.status_label.cget("text")
    assert app.start_btn.instate(["!disabled"])


def test_gui_recovers_after_blocked_decoder(app, monkeypatch):
    def blocked():
        raise ImportError("DLL load failed: An Application Control policy has blocked this file.")
    monkeypatch.setattr(converter, "initialize_heif", blocked)
    app.start_btn.invoke()
    drain_worker(app)
    assert gui.messagebox.showerror.called
    assert "Application Control" in app.log_text.get("1.0", "end")
    assert app.start_btn.instate(["!disabled"])


def test_gui_reports_failures(app):
    (app.initial_dir / "bad.heic").write_bytes(b"broken")
    app.start_btn.invoke()
    drain_worker(app)
    assert gui.messagebox.showwarning.called
    assert not gui.messagebox.showinfo.called
    assert "errors" in app.status_label.cget("text")
    assert "cannot identify image" in app.log_text.get("1.0", "end")


def test_gui_closing_waits_for_worker(app, monkeypatch):
    release = threading.Event()
    app.worker = threading.Thread(target=lambda: release.wait(10))
    app.worker.start()
    app._set_running(True)
    monkeypatch.setattr(gui.messagebox, "askyesno", lambda *a, **k: True)
    destroy = Mock()
    monkeypatch.setattr(app.root, "destroy", destroy)
    try:
        app._on_close()
        assert app.is_cancelled
        app._process_queue()
        destroy.assert_not_called()
        release.set()
        app.worker.join(5)
        app._process_queue()
        destroy.assert_called_once()
    finally:
        release.set()


def test_gui_continues_when_report_cannot_be_created(app, heif_photo):
    (app.initial_dir / "heic-png-report.txt").mkdir()
    app.start_btn.invoke()
    drain_worker(app)
    assert (app.initial_dir / "heic-png" / "photo.png").is_file()
    assert "Could not create report" in app.log_text.get("1.0", "end")
    assert gui.messagebox.showwarning.called


def test_palette_transparency_is_preserved():
    image = Image.new("P", (2, 2))
    image.info["transparency"] = 0
    result, _ = converter.prepare_image_for_format(image, "webp")
    assert result.mode == "RGBA"
    assert result.getpixel((0, 0))[3] == 0
