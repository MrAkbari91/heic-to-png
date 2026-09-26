# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0]
 
### Added
- Graphical User Interface (GUI) powered by Tkinter (`gui.py`)
- Multi-format conversion support: PNG, JPG, JPEG, and WEBP
- Format selection with automatic output subfolder mapping (`heic-<format>`)
- Exe icon integration using `heic_to_any.ico` for Windows window and taskbar
- `--format` CLI flag with format choices
- `--gui` and `--cli` flags
- `run_gui.bat` shortcut to launch the GUI directly on Windows
- Safe RGBA transparency handling when converting to JPG/JPEG
- Worker thread conversion to prevent GUI freezing

### Tests
- Added multi-format conversion unit tests
- Added JPEG alpha composite tests
- Added conversion cancellation tests
- Added GUI icon locator tests

## [1.1.0]

### Added
- CLI progress reporting
- Per-file conversion status
- `--quiet` option
- `--no-progress` option
- Progress callback API

### Improved
- CLI conversion summary

### Tests
- Added regression tests for progress callbacks
- Added tests for skipped-file progress reporting
