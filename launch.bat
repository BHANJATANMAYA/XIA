@echo off
setlocal EnableDelayedExpansion

:: ============================================================
::  xia — Self-Bootstrapping Launcher
::  Double-click this file to start xia on any Windows machine.
::  It will handle everything: Python, Ollama, venv, and launch.
:: ============================================================

title xia — Starting...

:: ── Detect root (where this .bat file lives) ─────────────────
set "XIA_ROOT=%~dp0"
:: Remove trailing backslash
if "%XIA_ROOT:~-1%"=="\" set "XIA_ROOT=%XIA_ROOT:~0,-1%"

:: ── Set Ollama paths FIRST, before anything else ─────────────
:: Must be set before ollama.exe is ever invoked (even by launch.py).
set "OLLAMA_MODELS=%XIA_ROOT%\models\ollama"
set "OLLAMA_HOME=%XIA_ROOT%\models\ollama"

:: Also persist to user environment so any child-spawned ollama sees them.
setx OLLAMA_MODELS "%XIA_ROOT%\models\ollama" >nul 2>&1
setx OLLAMA_HOME   "%XIA_ROOT%\models\ollama" >nul 2>&1

:: ── Venv paths ───────────────────────────────────────────────
set "XIA_VENV=%XIA_ROOT%\.venv"
set "XIA_PYTHON=%XIA_VENV%\Scripts\python.exe"

echo.
echo  ============================================
echo   xia ^| Portable AI Agent
echo   Root  : %XIA_ROOT%
echo   Models: %OLLAMA_MODELS%
echo  ============================================
echo.

:: ── Kill any running Ollama so it restarts with our env vars ─
echo  [launcher] Stopping any existing Ollama instance...
taskkill /IM ollama.exe /F >nul 2>&1
timeout /t 2 /nobreak >nul

:: ── Ensure model directory exists ────────────────────────────
if not exist "%OLLAMA_MODELS%" (
    echo  [launcher] Creating models directory: %OLLAMA_MODELS%
    mkdir "%OLLAMA_MODELS%"
)

:: ── Check for venv Python ────────────────────────────────────
if exist "%XIA_PYTHON%" (
    echo  [launcher] Virtual environment found.
    goto :run_bootstrap
)

:: ── No venv — fall back to system Python ─────────────────────
echo  [launcher] Venv not found. Looking for system Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    goto :install_python
)
goto :run_bootstrap

:run_bootstrap
echo  [launcher] Launching xia with venv Python...
echo  [launcher] OLLAMA_MODELS = %OLLAMA_MODELS%
echo  [launcher] OLLAMA_HOME   = %OLLAMA_HOME%
echo.

:: Child process inherits all env vars set above (setlocal scope)
"%XIA_PYTHON%" "%XIA_ROOT%\launch.py"
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Bootstrap failed. See above for details.
    echo  Press any key to exit.
    pause >nul
    exit /b 1
)
goto :end

:install_python
echo.
echo  [!] Python not found on this machine.
echo.
echo  xia needs Python 3.11+ to run.
echo  Would you like to download and install it now?
echo.
choice /C YN /M "  Install Python? [Y/N]"
if %errorlevel% equ 2 (
    echo  Cancelled. Install Python manually from https://python.org
    pause >nul
    exit /b 1
)

echo.
echo  [launcher] Downloading Python installer...
set "PY_INSTALLER=%TEMP%\python_installer.exe"
curl -L -o "%PY_INSTALLER%" "https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
if %errorlevel% neq 0 (
    echo  [ERROR] Download failed. Check your internet connection.
    echo  Then install Python manually from https://python.org
    pause >nul
    exit /b 1
)

echo  [launcher] Installing Python (this may take a minute)...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
if %errorlevel% neq 0 (
    echo  [ERROR] Python installation failed.
    echo  Please install manually from https://python.org
    pause >nul
    exit /b 1
)

call refreshenv >nul 2>&1
echo  [launcher] Python installed successfully.
goto :run_bootstrap

:end
endlocal
