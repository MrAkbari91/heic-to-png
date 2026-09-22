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

## Run from source

```bash
# Scan this project folder (the default)
python convert_heic_to_png.py

# Scan a different folder
python convert_heic_to_png.py --root "/path/to/photos"

# Replace PNGs that already exist
python convert_heic_to_png.py --root "/path/to/photos" --overwrite\n\n# Run quietly\npython convert_heic_to_png.py --root "/path/to/photos" --quiet\n\n# Keep normal logs but disable per-file progress\npython convert_heic_to_png.py --root "/path/to/photos" --no-progress
```

On Windows, `run_converter.bat` is a shortcut for running the source code.

## Build a local executable

PyInstaller builds for the operating system it runs on.

```bash
pyinstaller --noconfirm --clean --onefile --name heic-to-png convert_heic_to_png.py
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
