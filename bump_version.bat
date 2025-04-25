@echo off
:: bump_version.bat - Utility to bump version, commit changes, and create a tag in one command
:: This script uses version_manager.py to handle version updates and Git operations
:: Created: April 25, 2025

setlocal enabledelayedexpansion

echo ===== Version, Commit, and Tag Utility =====

:: Check for Python availability
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not available in PATH. Please ensure Python is installed and in your PATH.
    exit /b 1
)

:: Process arguments
if "%~1"=="" (
    echo Usage options:
    echo   bump_version.bat patch [message]   - Bump patch version (e.g., 1.2.3 to 1.2.4)
    echo   bump_version.bat minor [message]   - Bump minor version (e.g., 1.2.3 to 1.3.0)
    echo   bump_version.bat major [message]   - Bump major version (e.g., 1.2.3 to 2.0.0)
    echo   bump_version.bat set X.Y.Z [message] - Set specific version
    echo.
    echo Examples:
    echo   bump_version.bat patch "Fix critical bug in API handler"
    echo   bump_version.bat minor "Add new feature for VLC detection"
    exit /b 1
)

set ACTION=%~1
set VERSION_TYPE=
set VERSION=
set CUSTOM_MSG=%~2

:: Determine the action and parameters
if /i "%ACTION%"=="patch" (
    set VERSION_TYPE=patch
) else if /i "%ACTION%"=="minor" (
    set VERSION_TYPE=minor
) else if /i "%ACTION%"=="major" (
    set VERSION_TYPE=major
) else if /i "%ACTION%"=="set" (
    if "%~2"=="" (
        echo ERROR: When using "set", you must specify a version number.
        echo Example: bump_version.bat set 2.1.0 "Version message"
        exit /b 1
    )
    set VERSION=%~2
    set CUSTOM_MSG=%~3
) else (
    echo ERROR: Unknown action "%ACTION%"
    echo Valid actions are: patch, minor, major, set
    exit /b 1
)

:: Confirmation step
echo.
if not "%VERSION%"=="" (
    echo Will set version to: %VERSION%
    echo Commit message: %CUSTOM_MSG%
) else (
    echo Will bump %VERSION_TYPE% version
    echo Commit message: %CUSTOM_MSG%
)

set /p CONFIRM="Are you sure you want to proceed? (y/n): "
if /i not "%CONFIRM%"=="y" (
    echo Operation cancelled.
    exit /b 0
)

echo.
echo ----- Updating Version, Committing, and Tagging -----

:: Execute version manager with appropriate command
if not "%VERSION%"=="" (
    :: Handle "set" command
    if "%CUSTOM_MSG%"=="" (
        python version_manager.py set %VERSION% --force-tag
    ) else (
        python version_manager.py set %VERSION% --force-tag --message "%CUSTOM_MSG%"
    )
) else (
    :: Handle "bump" command (patch, minor, major)
    if "%CUSTOM_MSG%"=="" (
        python version_manager.py bump %VERSION_TYPE% --force-tag
    ) else (
        python version_manager.py bump %VERSION_TYPE% --force-tag --message "%CUSTOM_MSG%"
    )
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERROR: Failed to update version and create tag.
    exit /b %ERRORLEVEL%
)

echo.
echo ✅ Version update, commit, and tag creation completed successfully!
echo This should trigger your build workflow.
exit /b 0
