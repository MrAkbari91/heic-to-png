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

## Features & v1.2.0 Updates

v1.2.0 adds:
- **Desktop Graphical User Interface (GUI)**: Modern Tkinter interface (`gui.py` / `run_gui.bat`) with folder selection, format choice, live progress bar, file logs, and completion dialogs.
- **Multiple Output Formats**: Convert HEIC/HEIF files to **PNG**, **JPG**, **JPEG**, or **WEBP**.
- **Per-Format Output Folders**: Automatically saves results into dedicated folders (e.g., `heic-png`, `heic-jpg`, `heic-webp`) without touching original images.
- **Custom Application Icon**: Bundled `heic_to_any.ico` icon applied to the Windows executable and GUI titlebar.
- **CLI Progress & Controls**: Visual progress indicator, `--quiet`, `--no-progress`, and `--format` options.
- **Threaded Conversion**: Non-blocking background worker thread with cancellation support.
- **Smart Color & Transparency Handling**: Safely composites RGBA transparency over white background for JPEG targets.

## Launch GUI (Graphical Interface)

- **Windows**: Double-click `run_gui.bat` or the packaged `dist/HEIC-to-PNG.exe`.
- **Command line**: Run `python convert_heic_to_png.py --gui` or `python -m gui`.

## Run from source (CLI)

```bash
# Launch GUI by default (or pass --gui)
python convert_heic_to_png.py

# Convert to JPG instead of default PNG
python convert_heic_to_png.py --format jpg --root "C:\path\to\images"

# Convert to WebP
python convert_heic_to_png.py --format webp --root "C:\path\to\images"

# Replace existing converted files
python convert_heic_to_png.py --root "C:\path\to\images" --format png --overwrite

# Force command-line execution without GUI
python convert_heic_to_png.py --cli --format jpg

# Run quietly (suppresses terminal output)
python convert_heic_to_png.py --root "C:\path\to\images" --quiet
```

On Windows:
- `run_gui.bat` launches the Graphical User Interface.
- `run_converter.bat` runs the CLI converter.

## Build a local executable

PyInstaller builds for the operating system it runs on with the custom icon:

```bash
pyinstaller --noconfirm --clean HEIC-to-PNG.spec
```

The result is in `dist/`. On Windows, double-click `build_exe.bat` instead.

## Project map

| Path | Purpose |
| --- | --- |
| `convert_heic_to_png.py` | Main application engine and CLI entry point |
| `gui.py` | Desktop GUI interface with multi-format picker and live progress |
| `heic_to_any.ico` | Application icon for window titlebars and compiled executable |
| `run_gui.bat` | Windows batch shortcut to launch the GUI |
| `run_converter.bat` | Windows batch shortcut to run CLI conversion |
| `build_exe.bat` | Windows executable build script (with icon & data bundling) |
| `HEIC-to-PNG.spec` | PyInstaller build specification with icon & hidden imports |
| `tests/` | Automated test suite (conversions, formats, GUI, CLI) |
| `pyproject.toml` | Project metadata and development dependencies |
| `requirements.txt` | Runtime dependency list |
| `.github/workflows/build.yml` | GitHub test and cross-platform build automation |
| `CHANGELOG.md` | Version history and release notes |
| `.gitignore` | Keeps local photos, output folders, and build files out of Git |

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
