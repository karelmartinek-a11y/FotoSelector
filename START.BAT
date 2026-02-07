@echo off
setlocal
REM Spusteni KájovoPhotoSelector s automatickou instalaci závislostí
cd /d "%~dp0"

REM vytvoř venv, pokud není
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
)

set "PYBIN=venv\Scripts\python.exe"

REM nainstaluj závislosti
if exist requirements.txt (
    "%PYBIN%" -m pip install --quiet --upgrade pip
    "%PYBIN%" -m pip install --quiet -r requirements.txt
) else (
    "%PYBIN%" -m pip install --quiet PyQt6 Pillow send2trash
)

"%PYBIN%" "KajovoPhotoSelector.py" %*
endlocal
