@echo off
cd /d "%~dp0"
call setup_env.bat
if errorlevel 1 goto :error
".venv\Scripts\python.exe" convert_heic_to_png.py --cli %*
set "converter_result=%errorlevel%"
pause
exit /b %converter_result%
:error
echo Could not prepare Python or the HEIC decoder. Read the error above.
pause
exit /b 1
