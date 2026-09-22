from pathlib import Path

from convert_heic_to_png import find_heic_files


def test_find_heic_files_is_recursive_and_ignores_output_folders(tmp_path: Path) -> None:
    (tmp_path / "Camera").mkdir()
    (tmp_path / "Camera" / "photo.HEIC").write_bytes(b"test")
    (tmp_path / "dem" / "siblings").mkdir(parents=True)
    (tmp_path / "dem" / "siblings" / "photo.heif").write_bytes(b"test")
    (tmp_path / "Camera" / "heic-png").mkdir()
    (tmp_path / "Camera" / "heic-png" / "old.heic").write_bytes(b"ignore")

    found, folder_count = find_heic_files(tmp_path, "heic-png", lambda _error: None)

    assert folder_count == 4
    assert {file.relative_to(tmp_path).as_posix() for file in found} == {
        "Camera/photo.HEIC",
        "dem/siblings/photo.heif",
    }
\n\ndef test_convert_folder_reports_progress_and_summary(tmp_path: Path, monkeypatch) -> None:\n    source_a = tmp_path / "photo-a.heic"\n    source_b = tmp_path / "photo-b.heif"\n    source_a.write_bytes(b"test")\n    source_b.write_bytes(b"test")\n\n    def fake_convert(source: Path, target: Path) -> None:\n        target.parent.mkdir(parents=True, exist_ok=True)\n        target.write_bytes(source.read_bytes())\n\n    monkeypatch.setattr("convert_heic_to_png.convert_one", fake_convert)\n    progress: list[tuple[int, int, str, str]] = []\n    summary = convert_folder(\n        tmp_path,\n        progress=lambda index, total, source, status: progress.append(\n            (index, total, source.as_posix(), status)\n        ),\n    )\n\n    assert summary.found == 2\n    assert summary.converted == 2\n    assert summary.skipped == 0\n    assert summary.failed == 0\n    assert [item[0] for item in progress] == [1, 2]\n    assert [item[1] for item in progress] == [2, 2]\n    assert [item[3] for item in progress] == ["converted", "converted"]\n\n\ndef test_convert_folder_reports_skipped_files(tmp_path: Path, monkeypatch) -> None:\n    source = tmp_path / "photo.heic"\n    source.write_bytes(b"test")\n    target = tmp_path / "heic-png" / "photo.png"\n    target.parent.mkdir()\n    target.write_bytes(b"existing")\n\n    called = False\n\n    def fake_convert(_source: Path, _target: Path) -> None:\n        nonlocal called\n        called = True\n\n    monkeypatch.setattr("convert_heic_to_png.convert_one", fake_convert)\n    progress: list[str] = []\n    summary = convert_folder(\n        tmp_path,\n        progress=lambda _index, _total, _source, status: progress.append(status),\n    )\n\n    assert summary.found == 1\n    assert summary.converted == 0\n    assert summary.skipped == 1\n    assert summary.failed == 0\n    assert progress == ["skipped"]\n    assert called is False