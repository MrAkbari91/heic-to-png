from pathlib import Path

from convert_heic_to_png import convert_folder, find_heic_files


def test_find_heic_files_is_recursive_and_ignores_output_folders(tmp_path: Path) -> None:
    (tmp_path / "folder_a").mkdir()
    (tmp_path / "folder_a" / "photo.HEIC").write_bytes(b"test")
    (tmp_path / "folder_b" / "subfolder").mkdir(parents=True)
    (tmp_path / "folder_b" / "subfolder" / "photo.heif").write_bytes(b"test")
    (tmp_path / "folder_a" / "heic-png").mkdir()
    (tmp_path / "folder_a" / "heic-png" / "old.heic").write_bytes(b"ignore")

    found, folder_count = find_heic_files(tmp_path, "heic-png", lambda _error: None)

    assert folder_count == 4
    assert {file.relative_to(tmp_path).as_posix() for file in found} == {
        "folder_a/photo.HEIC",
        "folder_b/subfolder/photo.heif",
    }


def test_convert_folder_reports_progress_and_summary(tmp_path: Path, monkeypatch) -> None:
    source_a = tmp_path / "photo-a.heic"
    source_b = tmp_path / "photo-b.heif"
    source_a.write_bytes(b"test")
    source_b.write_bytes(b"test")

    def fake_convert(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())

    monkeypatch.setattr("convert_heic_to_png.convert_one", fake_convert)
    progress: list[tuple[int, int, str, str]] = []
    summary = convert_folder(
        tmp_path,
        progress=lambda index, total, source, status: progress.append(
            (index, total, source.as_posix(), status)
        ),
    )

    assert summary.found == 2
    assert summary.converted == 2
    assert summary.skipped == 0
    assert summary.failed == 0
    assert [item[0] for item in progress] == [1, 2]
    assert [item[1] for item in progress] == [2, 2]
    assert [item[3] for item in progress] == ["converted", "converted"]


def test_convert_folder_reports_skipped_files(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "photo.heic"
    source.write_bytes(b"test")
    target = tmp_path / "heic-png" / "photo.png"
    target.parent.mkdir()
    target.write_bytes(b"existing")

    called = False

    def fake_convert(_source: Path, _target: Path) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("convert_heic_to_png.convert_one", fake_convert)
    progress: list[str] = []
    summary = convert_folder(
        tmp_path,
        progress=lambda _index, _total, _source, status: progress.append(status),
    )

    assert summary.found == 1
    assert summary.converted == 0
    assert summary.skipped == 1
    assert summary.failed == 0
    assert progress == ["skipped"]
    assert called is False


def test_convert_folder_reports_failed_files(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "corrupt.heic"
    source.write_bytes(b"bad data")

    def fake_convert_fail(_source: Path, _target: Path) -> None:
        raise ValueError("corrupt image data")

    monkeypatch.setattr("convert_heic_to_png.convert_one", fake_convert_fail)
    progress: list[tuple[int, int, str, str]] = []
    summary = convert_folder(
        tmp_path,
        progress=lambda index, total, source, status: progress.append(
            (index, total, source.as_posix(), status)
        ),
    )

    assert summary.found == 1
    assert summary.converted == 0
    assert summary.skipped == 0
    assert summary.failed == 1
    assert progress == [(1, 1, "corrupt.heic", "failed")]


def test_convert_folder_quiet_suppresses_stdout(tmp_path: Path, monkeypatch, capsys) -> None:
    source = tmp_path / "photo.heic"
    source.write_bytes(b"test")
    monkeypatch.setattr("convert_heic_to_png.convert_one", lambda src, tgt: None)

    summary = convert_folder(tmp_path, quiet=True)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert summary.converted == 1


def test_convert_folder_without_progress_logs_default(tmp_path: Path, monkeypatch, capsys) -> None:
    source = tmp_path / "photo.heic"
    source.write_bytes(b"test")
    monkeypatch.setattr("convert_heic_to_png.convert_one", lambda src, tgt: None)

    summary = convert_folder(tmp_path)

    captured = capsys.readouterr()
    assert "Scanning root folder:" in captured.out
    assert "OK: photo.heic" in captured.out
    assert "Done. Converted: 1; skipped: 0; failed: 0" in captured.out
    assert summary.converted == 1