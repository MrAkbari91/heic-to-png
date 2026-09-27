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
    root = gui.ctk.CTk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app(tmp_path, monkeypatch, tk_root):
    import tkinter as tk
    root = gui.ctk.CTkToplevel(tk_root)
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


def ready(app):
    app._update_file_list_display()
    deadline = time.monotonic() + 10
    while (app.is_scanning or app.scan_after is not None) and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    assert not app.is_scanning


def drain_worker(app):
    deadline = time.monotonic() + 15
    while app.is_converting and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    assert not app.is_converting


def test_gui_converts_real_photo(app, heif_photo):
    app.format_var.set("WEBP")
    app._on_format_changed()
    ready(app)
    app.start_btn.invoke()
    drain_worker(app)
    target = heif_photo.parent / "heic-webp" / "photo.webp"
    with Image.open(target) as image:
        assert image.size == (32, 24)
    assert "successfully" in app.status_label.cget("text")
    assert app.start_btn.cget("state") == "normal"


def test_gui_recovers_after_blocked_decoder(app, monkeypatch):
    def blocked():
        raise ImportError("DLL load failed: An Application Control policy has blocked this file.")
    (app.initial_dir / "photo.heic").touch()
    monkeypatch.setattr(converter, "initialize_heif", blocked)
    ready(app)
    app.start_btn.invoke()
    drain_worker(app)
    assert gui.messagebox.showerror.called
    assert "Application Control" in app.log_text.get("1.0", "end")
    assert app.start_btn.cget("state") == "normal"


def test_gui_reports_failures(app):
    (app.initial_dir / "bad.heic").write_bytes(b"broken")
    ready(app)
    app.start_btn.invoke()
    drain_worker(app)
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


def test_gui_converts_without_automatic_report(app, heif_photo):
    (app.initial_dir / "heic-png-report.txt").mkdir()
    ready(app)
    app.start_btn.invoke()
    drain_worker(app)
    assert (app.initial_dir / "heic-png" / "photo.png").is_file()
    assert "OK:" in app.log_text.get("1.0", "end")
    assert "successfully" in app.status_label.cget("text")


def test_palette_transparency_is_preserved():
    image = Image.new("P", (2, 2))
    image.info["transparency"] = 0
    result, _ = converter.prepare_image_for_format(image, "webp")
    assert result.mode == "RGBA"
    assert result.getpixel((0, 0))[3] == 0


def test_folder_selection_shows_count_destination_and_action(app, heif_photo, monkeypatch):
    app.source_files.clear()
    monkeypatch.setattr(gui.filedialog, "askdirectory", lambda **kwargs: str(heif_photo.parent))
    app.add_folder_btn.invoke()
    deadline = time.monotonic() + 10
    while app.is_scanning and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    assert "1 photos" in app.file_count_label.cget("text")
    assert "Convert 1 photos to PNG" == app.start_btn.cget("text")
    assert str(heif_photo.parent / "heic-png") in app.file_status_label.cget("text")
    app.start_btn.invoke()
    drain_worker(app)
    assert (heif_photo.parent / "heic-png" / "photo.png").is_file()


def test_scan_is_background_and_stale_results_do_not_restore_cleared_selection(app, heif_photo, monkeypatch):
    release = threading.Event()
    started = threading.Event()
    scan_sources = converter.scan_sources

    def slow(*args, **kwargs):
        started.set()
        release.wait(5)
        return scan_sources(*args, **kwargs)

    monkeypatch.setattr(converter, "scan_sources", slow)
    try:
        app._update_file_list_display()
        assert started.wait(2)
        assert app.is_scanning
        assert app.start_btn.cget("state") == "disabled"
        heartbeat = []
        app.root.after(0, lambda: heartbeat.append(True))
        app.root.update()
        assert heartbeat
        app.clear_btn.invoke()
        release.set()
        app._handle_scan({"generation": app.scan_generation - 1,
                          "result": converter.ScanResult(files=[heif_photo])})
        assert app.source_files == []
        assert app.start_btn.cget("state") == "disabled"
        assert "Step 1" in app.status_label.cget("text")
    finally:
        release.set()


def test_empty_folder_has_actionable_message_and_disabled_start(app):
    ready(app)
    assert "No HEIC" in app.status_label.cget("text")
    assert "Choose another folder" in app.file_status_label.cget("text")
    assert app.start_btn.cget("state") == "disabled"


def test_custom_output_survives_format_changes(app, heif_photo):
    app.output_folder_var.set("my-exports")
    app.format_var.set("JPG")
    app._on_format_changed()
    ready(app)
    assert app.output_folder_var.get() == "my-exports"
    assert "JPG" in app.start_btn.cget("text")


def test_pending_settings_edit_cannot_start_with_stale_scan(app, heif_photo):
    ready(app)
    app.output_folder_var.set("../invalid")
    app._start_conversion()
    assert not app.is_converting
    assert app.start_btn.cget("state") == "disabled"
    ready(app)
    assert "Check the output" in app.status_label.cget("text")


def test_gui_same_stem_files_do_not_overwrite_each_other(app, heif_photo):
    (heif_photo.parent / "photo.heif").write_bytes(heif_photo.read_bytes())
    ready(app)
    app.start_btn.invoke()
    drain_worker(app)
    assert len(list((heif_photo.parent / "heic-png").glob("*.png"))) == 2
    assert app.stat_converted.cget("text") == "2"


def test_gui_cancel_recovers_controls_and_preserves_completed_outputs(app, heif_photo, monkeypatch):
    release = threading.Event()
    started = threading.Event()
    real_convert = converter.convert_one
    for index in range(5):
        (heif_photo.parent / f"other{index}.heic").write_bytes(heif_photo.read_bytes())

    def slow(*args, **kwargs):
        started.set()
        release.wait(5)
        real_convert(*args, **kwargs)

    monkeypatch.setattr(converter, "convert_one", slow)
    app.workers_var.set(1)
    ready(app)
    app.start_btn.invoke()
    assert started.wait(3)
    app.cancel_btn.invoke()
    release.set()
    drain_worker(app)
    assert app.status_label.cget("text") == "Cancelled"
    assert app.stat_converted.cget("text") == "1"
    assert app.start_btn.cget("state") == "normal"
    assert app.open_btn.cget("state") == "normal"


@pytest.mark.parametrize("scaling", [1.0, 1.5])
def test_primary_action_stays_visible_at_minimum_window_size(app, heif_photo, scaling):
    try:
        gui.ctk.set_widget_scaling(scaling)
        gui.ctk.set_window_scaling(scaling)
        app.root.geometry("820x540")
        app.root.deiconify()
        ready(app)
        # CTkToplevel restores its requested geometry on a deferred WM event.
        deadline = time.monotonic() + 3
        while app.root.winfo_width() < 800 and time.monotonic() < deadline:
            app.root.update()
            time.sleep(0.01)
        for widget in (app.start_btn, app.cancel_btn, app.open_btn, app.status_label):
            assert widget.winfo_viewable()
            left = widget.winfo_rootx() - app.root.winfo_rootx()
            top = widget.winfo_rooty() - app.root.winfo_rooty()
            assert 0 <= left < app.root.winfo_width()
            assert 0 <= top < app.root.winfo_height()
            assert top + widget.winfo_height() <= app.root.winfo_height()
            assert left + widget.winfo_width() <= app.root.winfo_width()
    finally:
        gui.ctk.set_widget_scaling(1)
        gui.ctk.set_window_scaling(1)
