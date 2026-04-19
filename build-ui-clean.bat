@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "APP_NAME=awl-text-sync"
set "ENTRY=awl_text_sync\ui.py"
set "DIST_DIR=%CD%\dist"
set "BUILD_DIR=%CD%\build"
set "SPEC_FILE=%CD%\%APP_NAME%.spec"
set "EXE_PATH=%DIST_DIR%\%APP_NAME%.exe"

where python >nul 2>nul
if errorlevel 1 (
    echo [error] Python not found in PATH.
    exit /b 1
)

python -m PyInstaller --noconfirm --clean --onefile --windowed --name "%APP_NAME%" "%ENTRY%"
if errorlevel 1 (
    echo [error] UI build failed.
    exit /b 1
)

if not exist "%EXE_PATH%" (
    echo [error] Expected EXE not found: "%EXE_PATH%"
    exit /b 1
)

if exist "%BUILD_DIR%" rd /s /q "%BUILD_DIR%"
if exist "%SPEC_FILE%" del /f /q "%SPEC_FILE%"

for %%F in ("%CD%\warn-*.txt" "%CD%\xref-*.html" "%CD%\*.manifest" "%CD%\*.pkg" "%CD%\*.toc") do (
    if exist "%%~fF" del /f /q "%%~fF"
)

if exist "%DIST_DIR%" (
    for /d %%D in ("%DIST_DIR%\*") do (
        rd /s /q "%%~fD"
    )
    for %%F in ("%DIST_DIR%\*") do (
        if /i not "%%~nxF"=="%APP_NAME%.exe" del /f /q "%%~fF"
    )
)

echo [ok] Built UI EXE: "%EXE_PATH%"
endlocal
