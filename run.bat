@echo off
setlocal EnableDelayedExpansion
title CryWatchdog Launcher

:: ============================================================================
:: This script automatically sets up a virtual environment, installs the
:: required dependencies from pyproject.toml, and runs the application.
::
:: USAGE:
::   run.bat          - Creates environment if needed and runs the app.
::   run.bat reinstall  - Deletes the old environment and does a fresh install.
:: ============================================================================

:: --- Configuration ---
cd /d "%~dp0"
set "VENV_DIR=.venv"
set "PYTHON_EXE=python"
set "ENTRY_SCRIPT=main.py"
set "REQUIREMENTS_FILE=pyproject.toml"

:: !!! UPDATED: Tools are now in the bin folder !!!
set "TOOLS_DIR=bin"
set "LUA_COMPILER=%TOOLS_DIR%\luac54.exe"
set "LUA_FORMATTER=%TOOLS_DIR%\stylua.exe"

:: --- Argument Parsing ---
set "REINSTALL_MODE=0"
if /i "%1"=="reinstall" (
    set "REINSTALL_MODE=1"
    echo ** REINSTALL MODE ACTIVATED: The environment will be rebuilt. **
    echo.
)

:: --- Header ---
echo =======================================================
echo              CryWatchdog Launcher
echo =======================================================
echo.

:: --- [1/4] Verifying Required Project Files ---
echo [1/4] Verifying required files...
if not exist "%ENTRY_SCRIPT%" (
    set "ERROR_MESSAGE=Main script '%ENTRY_SCRIPT%' not found."
    goto :error
)
if not exist "%REQUIREMENTS_FILE%" (
    set "ERROR_MESSAGE=Project file '%REQUIREMENTS_FILE%' not found. Cannot install dependencies."
    goto :error
)

:: Check for tools in the BIN folder
if not exist "%LUA_COMPILER%" (
    set "ERROR_MESSAGE=Lua compiler not found at '%LUA_COMPILER%'. Please place 'luac54.exe' inside the '%TOOLS_DIR%' folder."
    goto :error
)
if not exist "%LUA_FORMATTER%" (
    set "ERROR_MESSAGE=Lua formatter not found at '%LUA_FORMATTER%'. Please place 'stylua.exe' inside the '%TOOLS_DIR%' folder."
    goto :error
)

echo [OK] All required files are present.
echo.

:: --- [2/4] Setting Up Virtual Environment ---
if "!REINSTALL_MODE!"=="1" (
    if exist "%VENV_DIR%" (
        echo [2/4] Reinstall mode: Deleting existing virtual environment...
        rmdir /s /q "%VENV_DIR%"
        if !errorlevel! neq 0 (
            set "ERROR_MESSAGE=Could not delete the '%VENV_DIR%' directory. Check for file locks."
            goto :error
        )
    )
)

set "NEEDS_INSTALL=0"
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [2/4] Creating Python virtual environment in '%VENV_DIR%'...
    %PYTHON_EXE% -m venv %VENV_DIR%
    if !errorlevel! neq 0 (
        set "ERROR_MESSAGE=Failed to create the virtual environment. Ensure Python is installed and in your PATH."
        goto :error
    )
    set "NEEDS_INSTALL=1"
) else (
    echo [2/4] Virtual environment already exists.
)

echo Activating virtual environment...
set "PATH=%CD%\%VENV_DIR%\Scripts;%PATH%"
echo [OK] Virtual environment is active.
echo.

:: --- [3/4] Installing Dependencies ---
set "SHOULD_INSTALL=0"
if "!NEEDS_INSTALL!"=="1" set "SHOULD_INSTALL=1"
if "!REINSTALL_MODE!"=="1" set "SHOULD_INSTALL=1"

if "!SHOULD_INSTALL!"=="1" (
    echo [3/4] Installing dependencies from '%REQUIREMENTS_FILE%'... This may take a moment.
    pip install --upgrade pip

    echo --- Installing project...
    pip install .
    if !errorlevel! neq 0 (
        set "ERROR_MESSAGE=Failed to install dependencies from '%REQUIREMENTS_FILE%'. Check your internet connection and the file's contents."
        goto :error
    )
) else (
    echo [3/4] Dependencies appear to be installed. Skipping installation.
)
echo [OK] Dependencies are ready.
echo.

:: --- [4/4] Launching Application ---
echo =======================================================
echo [4/4] Starting CryWatchdog...
echo =======================================================
echo.

python "%ENTRY_SCRIPT%"
if !errorlevel! neq 0 (
    set "ERROR_MESSAGE=The application exited with an error. Please check the console output above."
    goto :error
)

echo.
echo =======================================================
echo Application finished successfully.
goto :end_success

:error
echo.
echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo [FATAL ERROR] !ERROR_MESSAGE!
echo !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo.
pause
exit /b 1

:end_success
endlocal
echo Press any key to close this window.
pause >nul