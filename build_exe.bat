@echo off
cd /d "%~dp0"
call setup_env.bat
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean HEIC-to-PNG.spec
if errorlevel 1 goto :error
echo.
echo New executable: dist\HEIC-to-PNG.exe
pause
exit /b 0
:error
echo Build failed. Read the error above.
pause
exit /b 1
