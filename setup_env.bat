@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto :check
where py >nul 2>nul
if errorlevel 1 goto :python
py -3 -m venv .venv
if errorlevel 1 exit /b 1
goto :check
:python
python -m venv .venv
if errorlevel 1 exit /b 1
:check
".venv\Scripts\python.exe" -c "import tkinter; from convert_heic_to_png import initialize_heif; initialize_heif()" >nul 2>nul
if not errorlevel 1 exit /b 0
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -c "import tkinter; from convert_heic_to_png import initialize_heif; initialize_heif()"
exit /b %errorlevel%
