@echo off
cd /d "%~dp0"
call setup_env.bat
if errorlevel 1 goto :error
".venv\Scripts\python.exe" gui.py
if errorlevel 1 goto :error
exit /b 0
:error
echo.
echo Could not start the converter. Read the error above.
echo Install Python 3.10 or newer with Tcl/Tk support if Python is missing.
echo If Windows Application Control blocks a DLL, ask your administrator to approve it.
pause
exit /b 1
