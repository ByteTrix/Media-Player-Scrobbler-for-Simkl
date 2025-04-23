@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo Building Media Player Scrobbler for SIMKL Installer
echo ===================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python not found in PATH
    exit /b 1
)

REM Check if PyInstaller is available
python -c "import PyInstaller" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PyInstaller not found. Please install it using:
    echo pip install pyinstaller
    exit /b 1
)

REM Create output directory for installer
if not exist "dist\installer" mkdir "dist\installer"

echo Step 1: Get version from pyproject.toml
echo -----------------------------
for /f %%V in ('python get_version.py') do set APP_VERSION=%%V
echo Detected version: %APP_VERSION%

echo.
echo Step 2: Clean previous builds
echo -----------------------------
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
mkdir "dist"
mkdir "dist\installer"

echo.
echo Step 3: Build executables with PyInstaller
echo -----------------------------------------
python -m PyInstaller --clean simkl-mps.spec
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: PyInstaller build failed
    exit /b %ERRORLEVEL%
)

echo.
echo Step 4: Generate Inno Setup script with correct version
echo ------------------------------------
echo Generating setup script with version %APP_VERSION%...

REM Create a temp copy of the setup script with the correct version
type setup.iss | powershell -Command "$input | ForEach-Object { $_ -replace '#define MyAppVersion \"[^\"]*\"', '#define MyAppVersion \"%APP_VERSION%\"' }" > setup_temp.iss

echo.
echo Step 5: Building Inno Setup installer
echo ------------------------------------
REM Check if Inno Setup compiler (ISCC) is in PATH or in common locations
set "ISCC_PATH="
where iscc >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "ISCC_PATH=iscc"
) else (
    for %%I in (
        "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
        "%ProgramFiles%\Inno Setup 6\ISCC.exe"
        "%ProgramFiles(x86)%\Inno Setup 5\ISCC.exe"
        "%ProgramFiles%\Inno Setup 5\ISCC.exe"
    ) do (
        if exist "%%~I" (
            set "ISCC_PATH=%%~I"
            goto :found_iscc
        )
    )
    
    echo ERROR: Inno Setup compiler (ISCC) not found.
    echo Please install Inno Setup from https://jrsoftware.org/isinfo.php
    echo or add its directory to your PATH
    exit /b 1
)

:found_iscc
echo Using Inno Setup compiler: !ISCC_PATH!
"!ISCC_PATH!" /Q setup_temp.iss
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Inno Setup compilation failed
    exit /b %ERRORLEVEL%
)

REM Clean up the temporary setup file
del setup_temp.iss

echo.
echo ===================================================
echo Build completed successfully!
echo ===================================================
echo.
echo Installer created: dist\installer\MPSS_Setup_%APP_VERSION%.exe
echo.

exit /b 0