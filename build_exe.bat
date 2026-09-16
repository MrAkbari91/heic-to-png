@echo off
cd /d "%~dp0"

REM Run this after changing convert_heic_to_png.py.
REM It creates or replaces dist\HEIC-to-PNG.exe.
python -m pip install --upgrade -r requirements.txt pyinstaller
if errorlevel 1 goto :error
python -m PyInstaller --noconfirm --clean --onefile --name HEIC-to-PNG convert_heic_to_png.py
if errorlevel 1 goto :error
echo.
echo New EXE created: dist\HEIC-to-PNG.exe
pause
exit /b 0

:error
echo.
echo EXE build failed.
pause
exit /b 1
