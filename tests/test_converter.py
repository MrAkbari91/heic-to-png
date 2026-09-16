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
