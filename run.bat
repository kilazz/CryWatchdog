@echo off
setlocal EnableDelayedExpansion
title CryWatchdog Launcher

:: ============================================================================
:: CryWatchdog Launcher Script (Powered by uv)
::
:: USAGE:
::   run.bat           - Standard launch (creates/updates environment and runs).
::   run.bat reinstall - Deletes .venv and performs a clean reinstall.
:: ============================================================================

cd /d "%~dp0"

:: --- Configuration ---
set "VENV_DIR=.venv"
set "ENTRY_SCRIPT=main.py"
set "REQUIREMENTS_FILE=pyproject.toml"
set "TOOLS_DIR=bin"
set "LUA_COMPILER=%TOOLS_DIR%\luac55.exe"
set "LUA_FORMATTER=%TOOLS_DIR%\stylua.exe"

:: --- Parse Arguments ---
set "REINSTALL_MODE=0"
if /i "%~1"=="reinstall" set "REINSTALL_MODE=1"
if /i "%~1"=="clean" set "REINSTALL_MODE=1"

echo =======================================================
echo              CryWatchdog Launcher
echo =======================================================
echo.

if "!REINSTALL_MODE!"=="1" (
    echo ** REINSTALL MODE ACTIVATED: The environment will be rebuilt. **
    echo.
)

:: --- [1/4] Verifying Required Project Files ---
echo [1/4] Verifying required project files...

if not exist "%ENTRY_SCRIPT%" (
    set "ERROR_MESSAGE=Main script '%ENTRY_SCRIPT%' not found."
    goto :error
)

if not exist "%REQUIREMENTS_FILE%" (
    set "ERROR_MESSAGE=Project configuration file '%REQUIREMENTS_FILE%' not found."
    goto :error
)

if not exist "%LUA_COMPILER%" (
    set "ERROR_MESSAGE=Lua compiler not found at '%LUA_COMPILER%'. Please place 'luac55.exe' inside the '%TOOLS_DIR%' directory."
    goto :error
)

if not exist "%LUA_FORMATTER%" (
    set "ERROR_MESSAGE=Lua formatter not found at '%LUA_FORMATTER%'. Please place 'stylua.exe' inside the '%TOOLS_DIR%' directory."
    goto :error
)

echo [OK] All required project files are present.
echo.

:: --- [2/4] Verifying / Installing UV Package Manager ---
echo [2/4] Checking for 'uv' package manager...

where uv >nul 2>nul
if !errorlevel! neq 0 (
    echo 'uv' was not found in PATH. Installing uv automatically...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

    :: Add standard uv install locations to current session PATH
    set "PATH=%USERPROFILE%\.cargo\bin;%USERPROFILE%\.local\bin;%USERPROFILE%\.bin;%PATH%"

    where uv >nul 2>nul
    if !errorlevel! neq 0 (
        set "ERROR_MESSAGE=Failed to locate 'uv' after installation. Please install it manually: https://github.com/astral-sh/uv"
        goto :error
    )
)

echo [OK] 'uv' package manager is ready.
echo.

:: --- [3/4] Virtual Environment & Dependencies ---
if "!REINSTALL_MODE!"=="1" (
    if exist "%VENV_DIR%" (
        echo [3/4] Reinstall mode: Removing existing virtual environment '%VENV_DIR%'...
        rmdir /s /q "%VENV_DIR%"
        if !errorlevel! neq 0 (
            set "ERROR_MESSAGE=Failed to delete '%VENV_DIR%'. Ensure no running processes are locking its files."
            goto :error
        )
    )
)

echo [3/4] Synchronizing virtual environment and dependencies with uv...
uv venv %VENV_DIR% --quiet
if !errorlevel! neq 0 (
    set "ERROR_MESSAGE=Failed to create virtual environment using uv."
    goto :error
)

uv pip install -e . --quiet
if !errorlevel! neq 0 (
    set "ERROR_MESSAGE=Failed to install project dependencies from '%REQUIREMENTS_FILE%'."
    goto :error
)

echo [OK] Virtual environment and dependencies are ready.
echo.

:: --- [4/4] Launching Application ---
echo =======================================================
echo [4/4] Starting CryWatchdog...
echo =======================================================
echo.

uv run python "%ENTRY_SCRIPT%"
if !errorlevel! neq 0 (
    set "ERROR_MESSAGE=The application exited with an error. Please check the console log above."
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
