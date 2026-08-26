@echo off
title Free Downloader Tool
cd /d "%~dp0"

REM Find Python. The "py" launcher comes with the python.org installer and
REM is the most reliable. Plain "python" on a new Windows 11 is only a stub
REM that points at the Microsoft Store, so it comes later in the list.
set "PY="
if not defined PY (
    py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    py -c "import sys" >nul 2>&1 && set "PY=py"
)
if not defined PY (
    python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    python3 -c "import sys" >nul 2>&1 && set "PY=python3"
)

if not defined PY goto no_python

%PY% "video_downloader.py" %*
pause
exit /b

:no_python
echo.
echo   Python was not found on this computer.
echo.
echo   Free Downloader Tool needs Python 3.9 or newer.
echo   Download it here:
echo.
echo       https://www.python.org/downloads/
echo.
echo   In the installer, tick "Add python.exe to PATH" before you press
echo   Install. Then run this file again.
echo.
echo   If you do not want to install Python, get the ready-made program
echo   from the Releases page of the project instead.
echo.
pause
exit /b 1
