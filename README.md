# HEIC / HEIF Image Converter

Convert HEIC, HEIF and HIF photos with a guided desktop app or the command line.
Supported outputs: **PNG, JPG/JPEG, WebP, BMP, TIFF/TIF, GIF, ICO, TGA and PPM**.
Original photos stay unchanged. Each source folder gets its own output subfolder.

## Windows: open the app

Open **`dist/HEIC-Converter.exe`** (version 2.1.0), or double-click **`run_gui.bat`**
to run the current source. Rebuild the executable after changing source code;
older copies of the app do not update automatically.

1. Click **Choose folder** or **Add files**. Subfolders are included automatically.
2. Wait for the background scan. The app shows the number of photos and where
   results will be saved. An empty or unreadable folder gets an explanation.
3. Choose an output format and quality/compression settings, then click **Convert N photos to FORMAT** in the
   fixed bottom bar. You can also press **Ctrl+Enter** when the scan is ready.
4. Watch the live progress and results. Click **Open results** when finished.
   If outputs are spread across folders, choose the folder from the results list.

The middle content scrolls on smaller displays; progress, Convert and Cancel
remain available at the bottom. Changing a selection or output subfolder starts
another scan. Overlapping selections are deduplicated.

- Default output: `heic-<format>` beside each source photo, for example
  `Photos/Holiday/heic-png/photo.png`. The subfolder setting accepts a folder
  name, not an absolute destination path.
- Existing outputs are skipped unless **Overwrite existing** is enabled.
  Changing quality or compression does not automatically replace existing files;
  enable overwrite or choose a new output subfolder to compare settings.
- **Parallel jobs** controls how many photos convert at once (default 4).
  Use fewer jobs for large photos or limited memory.
- **Cancel** stops scheduling new work and lets active photos finish saving.
  Closing during conversion asks before stopping and waits for active saves.
- Failed photos and scan warnings appear in **Activity & error details**.
  A batch with failures or scan warnings is never labelled successful.
- The GUI keeps logs in memory. Use **Save log** to export them when needed.
- Same-stem inputs in a batch, such as `photo.heic` and `photo.heif`, receive
  distinct output names. Saving uses a temporary file and an atomic replacement.

## Run from source

Install Python 3.10 or newer with Tcl/Tk support. The Windows launchers use the
project `.venv` and install runtime dependencies only if their import check fails.
The first setup needs internet access. Startup errors remain visible in the
launcher console.

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[dev,build]"
python gui.py
```

Linux requires Tk and a graphical display for the GUI. CLI conversion does not
require a display. If Windows blocks a decoder DLL, the app shows the decoder
error; use `run_gui.bat` with an approved Python environment or contact the PC
administrator. The app does not change Windows security policies.

## Command line

`run_converter.bat` starts CLI mode. Installed entry points are `heic-to-png`
and `heic-to-png-gui`. Running the main script without arguments opens the GUI
when a display is available. Explicit `--gui` and `--cli` are mutually exclusive.

```sh
python convert_heic_to_png.py --cli --root "path/to/photos" --format jpg --workers 4
python convert_heic_to_png.py --cli --root "path/to/photos" --format webp --no-report
python convert_heic_to_png.py --cli --root "path/to/photos" --output-folder converted
python convert_heic_to_png.py --cli --root "path/to/photos" --format png --overwrite
python convert_heic_to_png.py --gui --root "path/to/photos" --format png
python convert_heic_to_png.py --cli --root "path/to/photos" --format jpg --preset balanced
python convert_heic_to_png.py --cli --root "path/to/photos" --format jpg --preset small-file --quality 90
python convert_heic_to_png.py --cli --root "path/to/photos" --format webp --webp-lossless
python convert_heic_to_png.py --cli --root "path/to/photos" --format png --png-compression 9
```

| Option | Behavior |
| --- | --- |
| `--root PATH` | Recursively scan this folder; default is the script/executable folder |
| `--format FORMAT`, `-f FORMAT` | Output format; default PNG |
| `--output-folder NAME` | Subfolder created beside each source; default `heic-<format>` |
| `--workers 1..16` | Parallel conversions; default 4 |
| `--preset NAME` | `high-quality` (default), `balanced`, or `small-file` |
| `--quality 1..100` | JPG/JPEG/WebP quality; lossless WebP compression effort |
| `--webp-lossless` | Lossless WebP encoding; requires `--format webp` |
| `--png-compression 0..9` | PNG compression level; default 6; requires PNG output |
| `--overwrite` | Replace existing output files |
| `--no-report` | Disable the CLI report |
| `--quiet` | Suppress normal terminal output |
| `--no-progress` | Hide per-photo progress |
| `--pause` | Wait for Enter before exiting |

CLI reports are saved as `heic-<format>-report.txt` under the root. A report-open
failure produces a warning while conversion continues. Invalid output settings
are rejected before creating a report. Exit status is nonzero for failures,
warnings or invalid arguments; Ctrl+C returns 130. An empty valid folder returns
zero with a message explaining that no supported photos were found.

## Image behavior

- Converts the primary image of a HEIF container and applies camera orientation.
- Preserves ICC color profiles for PNG/JPEG/WebP/TIFF when available.
- Decodes to 8-bit RGB/RGBA; this is not an HDR archival converter.
- JPEG/WebP default to quality 95. JPEG, BMP and PPM flatten transparency onto white.
- PNG, WebP and TIFF preserve alpha. GIF has a limited palette/transparency.
- ICO fits the image within 256 x 256 without enlarging small images.
- Videos and unsupported input formats are ignored during folder discovery.
  Corrupt HEIF photos are reported individually without aborting the batch.
- Metadata preservation varies by output format; retain originals as your archive.

## Quality and compression

The GUI shows controls for the selected format. Move a slider or toggle lossless
WebP to switch the preset label to **Custom**. Settings are fixed for the running
batch; controls become available again when the batch finishes or is cancelled.

| Preset | JPG / lossy WebP quality | PNG compression |
| --- | --- | --- |
| High Quality | 95 | 6 |
| Balanced | 85 | 6 |
| Small File | 70 | 9 |

All presets use lossy WebP; choosing a preset resets the lossless switch.
Enable **Lossless WebP** after choosing a preset if needed. PNG is always
lossless: presets only change its compression effort, never pixel quality.
Other output formats continue to use their standard encoding.

- JPG/WebP quality is 1-100. Lower values usually make smaller files with less
  detail. JPEG values above 95 can increase size substantially for little gain;
  JPEG quality 100 is still lossy.
- PNG compression is 0-9: 0 disables compression, 1 is fastest compression, and
  9 uses the most compression effort. Actual size and speed depend on the image.
- Lossless WebP preserves the decoded pixels. Its slider becomes **Compression
  effort**: higher values spend more time trying to reduce file size, without
  changing image quality. This does not restore information already lost in the
  source HEIC or enable HDR preservation.
- CLI explicit controls override presets regardless of argument order.
  Format-specific flags used with the wrong output format are rejected before
  creating reports or output files. `--gui` accepts the same initial settings.
- Effective encoding settings appear in the GUI activity log and CLI report.
  Presets do not resize photos or guarantee a particular file size.

## Development and packaging

```sh
python -m pytest -q
python -m PyInstaller --noconfirm --clean HEIC-to-PNG.spec
```

`build_exe.bat` uses the same specification and produces
`dist/HEIC-Converter.exe`. The executable includes CustomTkinter assets and the
HEIF decoder libraries. Use Python or `run_converter.bat` for terminal output;
the packaged desktop executable is a windowed app.

Tests exercise real HEIC/HEIF decoding in every output format, atomic saves,
parallel collisions, cancellation, CLI subprocesses, responsive GUI discovery,
stale scan results, failure recovery and action visibility at small window sizes
and increased scaling. Headless Linux GUI tests use `xvfb-run -a python -m pytest`.

| Module | Responsibility |
| --- | --- |
| `convert_heic_to_png.py` | Discovery, target planning, image conversion and shared batch engine; compatible script entry point |
| `cli.py` | Argument validation, mode selection, reports and exit codes |
| `gui.py` | Desktop presentation, asynchronous scan lifecycle and queued UI updates |
| `tests/` | Engine, CLI and GUI regression coverage |
| `setup_env.bat` / `run_*.bat` | Windows environment and launchers |
| `HEIC-to-PNG.spec` / `build_exe.bat` | Executable packaging |

Author: Dhruv Akbari. See LICENSE for license terms.
