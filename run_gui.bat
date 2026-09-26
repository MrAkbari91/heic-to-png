@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
if errorlevel 1 goto :error
python -m gui
exit /b 0

:error
echo.
echo Required packages could not be installed.
pause
exit /b 1
