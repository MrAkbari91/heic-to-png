# HEIC / HEIF Image Converter

Convert HEIC, HEIF and HIF photos recursively with a desktop GUI or command line.
Output formats: **PNG, JPG, JPEG, WebP, BMP, TIFF, TIF and GIF**.
Each photo folder gets its own `heic-<format>` output folder. Originals stay unchanged.

## Windows: ready-to-run app

Open `dist/HEIC-to-PNG.exe`, choose your photo folder, select the output format,
and click **Start Conversion**. The log shows each result and the reason for any failure.
The app searches subfolders too. **Open Output Folder** opens the output folder,
or the selected photo folder when results are spread across subfolders.

- Existing output files are skipped unless **Overwrite existing files** is selected.
- **Cancel** finishes the current photo before stopping. Closing the app also waits for it.
- Output is saved to a temporary file first, then moved into place after a successful save.
- Failures and warnings are shown in the result dialog; a failed batch is never labelled successful.
- Reports are saved as `heic-<format>-report.txt` in the selected folder.
- If a report cannot be created, the GUI continues converting and shows a warning.
- Files with the same stem, such as `photo.heic` and `photo.heif`, get distinct output names.

## Windows: run the source

Install Python 3.10 or newer with Tcl/Tk support, then double-click **run_gui.bat**.
The launcher uses this project's `.venv` and installs runtime dependencies if needed.
It does not reinstall packages on every launch when the environment already works.
The first setup needs internet access to download dependencies.

`run_converter.bat` starts CLI mode and accepts the same arguments as the Python command.
`build_exe.bat` rebuilds the executable from the same project environment.

### Decoder / Application Control errors

If an older executable shows `DLL load failed while importing _pillow_heif` or
`An Application Control policy has blocked this file`, use the rebuilt executable
or run `run_gui.bat` from the source folder. The GUI now catches decoder initialization
errors and displays the full details instead of leaving the worker stuck.
If your managed PC blocks the current package too, your administrator must approve it.
The application does not change Windows security policies.

## Source setup (all platforms)

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev,build]"
python gui.py
```

Linux distributions may require their Python Tk package and a graphical display for the GUI.
CLI conversion works without a display.

```sh
python convert_heic_to_png.py --cli --root "path/to/photos" --format jpg
python convert_heic_to_png.py --cli --root "path/to/photos" --format webp --no-report
python convert_heic_to_png.py --cli --root "path/to/photos" --format png --overwrite
python convert_heic_to_png.py --cli --root "path/to/photos" --format tiff --quiet
python convert_heic_to_png.py --gui --root "path/to/photos" --format png
```

Use `--output-folder converted` to choose a different output subfolder name.
Use `--no-progress` to hide per-file CLI updates, or `--pause` to wait before exiting.
The CLI returns a nonzero exit status for conversion failures, scan warnings or startup errors.
Running without arguments opens the GUI on Windows/macOS or when a display is available.

## Image behavior

- Converts the primary image of a HEIF container, applies camera orientation, and preserves
  the ICC color profile for PNG/JPEG/WebP/TIFF when present.
- Converts decoded photos to 8-bit RGB/RGBA; this is not a lossless HDR/archive converter.
- JPEG/WebP use quality 95. JPEG and BMP flatten transparency onto white.
- PNG, WebP and TIFF preserve alpha; GIF uses a limited palette and limited transparency.
- Videos and non-HEIF input files are ignored. Unsupported/corrupt HEIF files are logged.
- Metadata preservation varies by output format; retain the original photos as your archive.

## Tests and build

```sh
python -m pytest -q
python -m PyInstaller --noconfirm --clean HEIC-to-PNG.spec
```

The tests include actual encoded HEIC/HEIF inputs in every output format, atomic-save failure,
name collisions, folder exclusions, and real Tk GUI conversion/error/cancellation tests.
GUI tests require a display; use `xvfb-run -a python -m pytest` on a headless Linux host.
The Windows build creates `dist/HEIC-to-PNG.exe` with the icon and decoder libraries.
GitHub Actions uses the same build specification.

## Project files

| File | Purpose |
| --- | --- |
| `convert_heic_to_png.py` | Conversion engine and CLI |
| `gui.py` | Desktop GUI |
| `setup_env.bat` | Prepare and check the project Python environment |
| `run_gui.bat` | Windows GUI launcher |
| `run_converter.bat` | Windows CLI launcher |
| `build_exe.bat` | Windows build launcher |
| `HEIC-to-PNG.spec` | Executable packaging |
| `tests/` | Automated tests |

Author: Dhruv Akbari. See LICENSE for license terms.
