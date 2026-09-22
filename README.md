# HEIC to PNG

A cross-platform command-line tool that scans a folder tree for `.heic` and
`.heif` images. Every folder that contains source images receives its own
`heic-png` folder containing PNG conversions. Originals are never moved,
changed, or deleted.

## For users

Download the build matching your operating system from GitHub Actions
artifacts (or a GitHub Release when you publish one). Put the executable in
the top-level photo folder and run it.

- **Windows:** run `heic-to-png.exe` by double-clicking it.
- **macOS/Linux:** open Terminal in the photo folder, then run
  `./heic-to-png`. On macOS, you may need `chmod +x heic-to-png` once.

The app writes `heic-png-report.txt` in the scanned root. Run with
`--no-report` to disable it.

## Developer setup

Requires Python 3.10 or newer and Git.

```bash
git clone https://github.com/MrAkbari91/heic-to-png.git
cd heic-to-png
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS or Linux
source .venv/bin/activate
```

Install dependencies and run tests:

```bash
python -m pip install --upgrade pip
python -m pip install -e .[dev,build]
pytest
```

## Features & v1.1.0 Updates

v1.1.0 adds:
- **CLI progress feedback**: Visual percentage and progress indicator per file (`[CURRENT/TOTAL] PERCENT% STATUS: path`).
- **Conversion status per file**: Real-time status reporting (`CONVERTED`, `SKIPPED`, `FAILED`).
- **`--quiet` option**: Suppresses normal informational/log output while processing files.
- **`--no-progress` option**: Disables the per-file progress display while preserving standard conversion summaries.
- **Improved conversion summary**: Clear reporting of converted, skipped, and failed counters.
- **Progress callback support**: Python API support for attaching a custom `ProgressCallback` when calling `convert_folder()`.

## Run from source

```bash
# Scan this project folder (the default)
python convert_heic_to_png.py

# Scan a different folder
python convert_heic_to_png.py --root "C:\path\to\images"

# Replace PNGs that already exist
python convert_heic_to_png.py --root "C:\path\to\images" --overwrite

# Run quietly (suppresses terminal output)
python convert_heic_to_png.py --root "C:\path\to\images" --quiet

# Keep normal logs but disable per-file progress
python convert_heic_to_png.py --root "C:\path\to\images" --no-progress
```

On Windows, `run_converter.bat` is a shortcut for running the source code.

## Build a local executable

PyInstaller builds for the operating system it runs on.

```bash
pyinstaller --noconfirm --clean --onefile --name heic-to-png --icon=heic_to_any.ico convert_heic_to_png.py
```

The result is in `dist/`. On Windows, double-click `build_exe.bat` instead.

To build all three platforms, push the repository to GitHub. The workflow in
`.github/workflows/build.yml` runs tests and produces Windows, macOS, and
Linux artifacts automatically. Download them from the repository's **Actions**
page after a successful run.

## Project map

| Path | Purpose |
| --- | --- |
| `convert_heic_to_png.py` | Application code and command-line interface |
| `tests/` | Automated tests |
| `pyproject.toml` | Project metadata and development dependencies |
| `requirements.txt` | Runtime dependency list |
| `.github/workflows/build.yml` | GitHub test and cross-platform build automation |
| `build_exe.bat` | Windows local EXE build shortcut |
| `CHANGELOG.md` | Version history and release notes |
| `.gitignore` | Keeps local photos, PNG output, and build files out of Git |

## Git workflow

```bash
git checkout -b feature/my-change
# edit code and tests
pytest
git add convert_heic_to_png.py tests README.md
git commit -m "Add my change"
git push -u origin feature/my-change
```

Open a Pull Request on GitHub. GitHub Actions must pass before merging.

## Author

- **Dhruv Akbari**
  - GitHub: [@MrAkbari91](https://github.com/MrAkbari91)
  - Email: [dhruvakbari303@gmail.com](mailto:dhruvakbari303@gmail.com)

## License

MIT. See [LICENSE](LICENSE).
