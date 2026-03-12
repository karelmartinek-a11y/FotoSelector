@echo off
setlocal enableextensions

rem Jednotny build KajovoPhotoSelector do .exe pomoci PyInstalleru.
rem Script pouziva stejne logo jako aplikace i vysledny .exe soubor.

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

set "APP_NAME=KajovoPhotoSelector"
set "SPEC_FILE=%REPO_ROOT%\KajovoPhotoSelector.spec"
set "ICON_FILE=%REPO_ROOT%\resources\kajovo_photoselector.ico"
set "VENV_PYTHON=%REPO_ROOT%\venv\Scripts\python.exe"

if not exist "%SPEC_FILE%" (
    echo Chyba: nenasel jsem soubor "%SPEC_FILE%".
    exit /b 1
)

if not exist "%ICON_FILE%" (
    echo Chyba: nenasel jsem ikonu "%ICON_FILE%".
    exit /b 1
)

if exist "%VENV_PYTHON%" (
    set "PYTHON_EXE=%VENV_PYTHON%"
    echo Pouziji Python z virtualniho prostredi: "%PYTHON_EXE%"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PYTHON_EXE=py"
        echo Pouziji launcher "py".
    ) else (
        where python >nul 2>nul
        if errorlevel 1 (
            echo Chyba: Python nebyl nalezen.
            exit /b 1
        )
        set "PYTHON_EXE=python"
        echo Pouziji systemovy prikaz "python".
    )
)

pushd "%REPO_ROOT%" || exit /b 1

echo.
echo Kontroluji PyInstaller...
%PYTHON_EXE% -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo PyInstaller chybi, instaluji ho...
    %PYTHON_EXE% -m pip install pyinstaller
    if errorlevel 1 (
        echo Chyba: instalace PyInstalleru selhala.
        popd
        exit /b 1
    )
)

echo.
echo Cistim predchozi vystupy...
if exist "%REPO_ROOT%\dist\%APP_NAME%" rmdir /s /q "%REPO_ROOT%\dist\%APP_NAME%"
if exist "%REPO_ROOT%\build\%APP_NAME%" rmdir /s /q "%REPO_ROOT%\build\%APP_NAME%"

echo.
echo Spoustim build .exe...
%PYTHON_EXE% -m PyInstaller --noconfirm --clean "%SPEC_FILE%"
if errorlevel 1 (
    echo.
    echo Build selhal.
    popd
    exit /b 1
)

echo.
echo Build dokonceny.
echo EXE najdete zde:
echo "%REPO_ROOT%\dist\%APP_NAME%\%APP_NAME%.exe"

popd
exit /b 0
