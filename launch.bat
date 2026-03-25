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
set "OLLAMA_MODELS=%XIA_ROOT%\models\ollama"
set "OLLAMA_HOME=%XIA_ROOT%\models\ollama"

:: Persist to user environment so child-spawned ollama sees them too
setx OLLAMA_MODELS "%XIA_ROOT%\models\ollama" >nul 2>&1
setx OLLAMA_HOME   "%XIA_ROOT%\models\ollama" >nul 2>&1

:: ── Venv paths ───────────────────────────────────────────────
set "XIA_VENV=%XIA_ROOT%\.venv"
set "XIA_PYTHON=%XIA_VENV%\Scripts\python.exe"
set "SYS_PYTHON="

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
    echo  [launcher] Creating models directory...
    mkdir "%OLLAMA_MODELS%"
)

:: ── Validate the venv Python (not just that the file exists) ─
:: A venv built on another PC contains a hardcoded path to the
:: original system Python. That path won't exist on this machine.
:: We must actually RUN python.exe to know if the venv is healthy.
echo  [launcher] Checking virtual environment...

if not exist "%XIA_PYTHON%" goto :no_venv

:: Test if it actually works
"%XIA_PYTHON%" --version >nul 2>&1
if %errorlevel% equ 0 (
    echo  [launcher] Virtual environment OK.
    goto :run_xia
)

:: Venv exists but is broken — built on a different PC
echo  [launcher] Venv is stale (built on a different machine).
echo  [launcher] Removing broken venv and rebuilding...
rmdir /s /q "%XIA_VENV%"

:no_venv
echo  [launcher] No working venv found. Looking for system Python...

:: ── Find a working system Python ─────────────────────────────
call :find_python
if defined SYS_PYTHON goto :build_venv

:: Nothing found — download and install Python
goto :install_python

:build_venv
echo  [launcher] Building virtual environment with: !SYS_PYTHON!
"!SYS_PYTHON!" -m venv "%XIA_VENV%"
if %errorlevel% neq 0 (
    echo  [ERROR] Failed to create virtual environment.
    pause >nul
    exit /b 1
)
echo  [launcher] Virtual environment created.

:run_xia
echo  [launcher] OLLAMA_MODELS = %OLLAMA_MODELS%
echo  [launcher] OLLAMA_HOME   = %OLLAMA_HOME%
echo.

"%XIA_PYTHON%" "%XIA_ROOT%\launch.py"
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Bootstrap failed. See above for details.
    echo  Press any key to exit.
    pause >nul
    exit /b 1
)
goto :end

:: ─────────────────────────────────────────────────────────────
:install_python
echo.
echo  [!] Python is not installed on this machine.
echo  [!] xia needs Python 3.12 to run.
echo.
choice /C YN /M "  Download and install Python now? [Y/N]"
if %errorlevel% equ 2 (
    echo  Cancelled. Install Python manually from https://python.org
    pause >nul
    exit /b 1
)

echo.
echo  [launcher] Downloading Python 3.12.4...
echo  [launcher] (this may take a moment — watch the progress bar below)
echo.
set "PY_INSTALLER=%TEMP%\xia_python_setup.exe"

:: --progress-bar shows a real download bar instead of silent output
curl --progress-bar -L -o "%PY_INSTALLER%" "https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Download failed. Check your internet connection.
    echo  Install Python manually from https://python.org then re-run xia.
    pause >nul
    exit /b 1
)

echo.
echo  [launcher] Installing Python silently (no admin required)...
"%PY_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1
if %errorlevel% neq 0 (
    echo  [ERROR] Installation failed.
    echo  Please install Python manually from https://python.org
    pause >nul
    exit /b 1
)

echo  [launcher] Python installed. Locating it...

:: Scan the per-user install directory (no refreshenv needed)
call :find_python

if not defined SYS_PYTHON (
    echo  [ERROR] Could not locate the newly installed Python.
    echo  Please close this window and re-run launch.bat.
    pause >nul
    exit /b 1
)

echo  [launcher] Found Python: !SYS_PYTHON!
goto :build_venv

:: ─────────────────────────────────────────────────────────────
:find_python
:: Check per-user install location (default for /quiet InstallAllUsers=0)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" set "SYS_PYTHON=%%D\python.exe"
)
if defined SYS_PYTHON exit /b 0

:: Check system-wide install
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" set "SYS_PYTHON=%%D\python.exe"
)
if defined SYS_PYTHON exit /b 0

:: Check py launcher (ships with Python)
where py >nul 2>&1
if %errorlevel% equ 0 ( set "SYS_PYTHON=py" & exit /b 0 )

:: Check plain python in PATH
where python >nul 2>&1
if %errorlevel% equ 0 ( set "SYS_PYTHON=python" & exit /b 0 )

exit /b 0

:end
endlocal
