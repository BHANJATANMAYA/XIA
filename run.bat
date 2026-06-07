@echo off
setlocal EnableDelayedExpansion
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
title xia — Starting...

:: ================================================================
::  xia — Offline-First Self-Bootstrapping Launcher v2.0
::
::  Works 100% offline if installers\ folder is pre-bundled.
::  Falls back to internet download if bundles are missing.
::
::  Offline bundle (pre-download once, carry on SSD forever):
::    installers\
::      python-3.12.4-amd64.exe    <- Python offline installer
::      OllamaSetup.exe            <- Ollama offline installer
::
::  To prepare offline bundle on a machine with internet:
::    1. Run this launcher once (it downloads and caches both)
::    2. Copy the entire xia\ folder to your SSD
::    3. It will never need internet again on any machine
:: ================================================================

:: ── Locate SSD root (always relative, drive-letter agnostic) ─────────
set "XIA_ROOT=%~dp0"
if "%XIA_ROOT:~-1%"=="\" set "XIA_ROOT=%XIA_ROOT:~0,-1%"

:: ── Key paths ─────────────────────────────────────────────────────────
set "XIA_VENV=%XIA_ROOT%\.venv"
set "XIA_PYTHON=%XIA_VENV%\Scripts\python.exe"
set "XIA_INSTALLERS=%XIA_ROOT%\installers"
set "XIA_PY_INSTALLER=%XIA_INSTALLERS%\python-3.12.4-amd64.exe"
set "XIA_OLLAMA_INSTALLER=%XIA_INSTALLERS%\OllamaSetup.exe"
set "PY_DOWNLOAD_URL=https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
set "OLLAMA_DOWNLOAD_URL=https://ollama.com/download/OllamaSetup.exe"
set "SYS_PYTHON="
set "TOTAL_STEPS=6"

:: ── Set Ollama & Cache storage paths BEFORE anything starts ──────────
:: Redirects all libraries to the SSD, leaving zero footprint on host.
set "OLLAMA_MODELS=%XIA_ROOT%\models\ollama"
set "OLLAMA_HOME=%XIA_ROOT%\models\ollama"
set "PLAYWRIGHT_BROWSERS_PATH=%XIA_ROOT%\models\playwright"
set "HF_HOME=%XIA_ROOT%\models\hf_home"
set "PIP_NO_CACHE_DIR=1"

:: ── Header ────────────────────────────────────────────────────────────
echo.
echo  ================================================================
echo   xia  ^|  Portable AI Agent  ^|  Offline-First Launcher v2.0
echo  ================================================================
echo   Root     : %XIA_ROOT%
echo   Models   : %OLLAMA_MODELS%
echo   Bundles  : %XIA_INSTALLERS%
echo  ================================================================
echo.

:: ── Ensure required folders exist ────────────────────────────────────
if not exist "%XIA_INSTALLERS%"    mkdir "%XIA_INSTALLERS%"
if not exist "%OLLAMA_MODELS%"     mkdir "%OLLAMA_MODELS%"

:: ================================================================
::  [1/6] PYTHON CHECK
:: ================================================================
echo  [1/%TOTAL_STEPS%] Checking Python...

:: Test venv Python first (fastest path)
if exist "%XIA_PYTHON%" (
    "%XIA_PYTHON%" --version >nul 2>&1
    if !errorlevel! equ 0 (
        echo   [OK] Virtual environment is healthy.
        goto :step3_deps
    )
    :: Venv exists but won't run — ported from another machine
    echo   [!] Venv is stale ^(built on a different machine^).
    echo   [!] Removing and rebuilding...
    rmdir /s /q "%XIA_VENV%" >nul 2>&1
)

:: Search for system Python in known locations
call :find_system_python
if defined SYS_PYTHON (
    echo   [OK] Found Python: !SYS_PYTHON!
    goto :step2_build_venv
)

:: No Python found anywhere
echo   [!] No Python found on this machine.

:: ================================================================
::  [2/6] PYTHON INSTALL (offline-first)
:: ================================================================
echo.
echo  [2/%TOTAL_STEPS%] Installing Python 3.12.4...

if exist "%XIA_PY_INSTALLER%" (
    echo   [OK] Offline installer found: installers\python-3.12.4-amd64.exe
    echo   [..] Installing silently (no internet required)...
    goto :do_install_python
)

:: No local installer — try downloading
echo   [!] Offline installer not found in installers\ folder.
echo   [..] Attempting download from python.org...
echo.

curl --progress-bar -L -o "%XIA_PY_INSTALLER%" "%PY_DOWNLOAD_URL%"
if !errorlevel! neq 0 (
    del /f /q "%XIA_PY_INSTALLER%" >nul 2>&1
    echo.
    echo  ================================================================
    echo   [OFFLINE] Cannot install Python automatically.
    echo.
    echo   Option A - Copy installer to SSD ^(Recommended^):
    echo     1. On a machine with internet, download:
    echo        https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe
    echo     2. Place it here:
    echo        %XIA_PY_INSTALLER%
    echo     3. Re-run run.bat
    echo.
    echo   Option B - Install Python manually:
    echo     1. Install Python 3.11+ from https://python.org
    echo     2. Re-run run.bat
    echo  ================================================================
    echo.
    pause >nul
    exit /b 1
)
echo   [OK] Download complete. Cached for offline use.

:do_install_python
"%XIA_PY_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_test=0 Include_doc=0
if !errorlevel! neq 0 (
    echo.
    echo   [ERROR] Python installation failed ^(code: !errorlevel!^).
    echo   Try running manually: %XIA_PY_INSTALLER%
    echo.
    pause >nul
    exit /b 1
)
echo   [OK] Python installed.
echo   [..] Locating installation...

call :find_system_python
if not defined SYS_PYTHON (
    echo.
    echo   [ERROR] Python installed but cannot be located.
    echo   Close this window and re-run run.bat.
    echo.
    pause >nul
    exit /b 1
)
echo   [OK] Found at: !SYS_PYTHON!

:step2_build_venv
echo.
echo  [2/%TOTAL_STEPS%] Building virtual environment...
echo   [..] Using: !SYS_PYTHON!

"!SYS_PYTHON!" -m venv "%XIA_VENV%"
if !errorlevel! neq 0 (
    echo.
    echo   [ERROR] Failed to create virtual environment.
    echo.
    pause >nul
    exit /b 1
)

"%XIA_PYTHON%" --version >nul 2>&1
if !errorlevel! neq 0 (
    echo   [ERROR] Venv created but Python won't run inside it.
    pause >nul
    exit /b 1
)
echo   [OK] Virtual environment ready.

:: ================================================================
::  [3/6] PYTHON DEPENDENCIES
:: ================================================================
:step3_deps
echo.
echo  [3/%TOTAL_STEPS%] Checking Python dependencies...

set "STAMP_FILE=%XIA_VENV%\.install_stamp"
set "REQ_FILE=%XIA_ROOT%\requirements.txt"

if not exist "%REQ_FILE%" (
    echo   [!] requirements.txt not found - skipping.
    goto :step4_ollama
)

set "NEEDS_INSTALL=1"
if exist "%STAMP_FILE%" (
    fc /b "%REQ_FILE%" "%STAMP_FILE%" >nul 2>&1
    if !errorlevel! equ 0 set "NEEDS_INSTALL=0"
)

if "!NEEDS_INSTALL!" == "0" (
    echo   [OK] Dependencies up to date.
    goto :step4_ollama
)

echo   [..] Installing dependencies...
"%XIA_PYTHON%" -m pip install -r "%REQ_FILE%" --quiet --disable-pip-version-check --no-cache-dir
if !errorlevel! neq 0 (
    echo.
    echo   [ERROR] Dependency installation failed.
    echo   Run manually: "%XIA_PYTHON%" -m pip install -r "%REQ_FILE%"
    echo.
    pause >nul
    exit /b 1
)

copy /y "%REQ_FILE%" "%STAMP_FILE%" >nul 2>&1
echo   [OK] Dependencies installed.

:: ================================================================
::  [4/6] OLLAMA CHECK AND INSTALL
:: ================================================================
:step4_ollama
echo.
echo  [4/%TOTAL_STEPS%] Checking Ollama...

:: Only restart Ollama if server isn't already responding
curl -s http://localhost:11434/api/tags >nul 2>&1
if !errorlevel! equ 0 (
    echo   [OK] Ollama is already running.
    goto :step5_server
)
taskkill /IM ollama.exe /F >nul 2>&1
timeout /t 1 /nobreak >nul

:: Prepend default/local search paths to PATH first to make detection idempotent
set "OLLAMA_LOCAL=%XIA_ROOT%\models\ollama\bin"
set "OLLAMA_DEFAULT=%LOCALAPPDATA%\Programs\Ollama"
if exist "%OLLAMA_LOCAL%\ollama.exe" (
    set "PATH=%OLLAMA_LOCAL%;%PATH%"
) else if exist "%OLLAMA_DEFAULT%\ollama.exe" (
    set "PATH=%OLLAMA_DEFAULT%;%PATH%"
)

where ollama >nul 2>&1
if !errorlevel! equ 0 (
    echo   [OK] Ollama is installed.
    goto :step5_server
)

echo   [!] Ollama not found on this machine.

if exist "%XIA_OLLAMA_INSTALLER%" (
    echo   [OK] Offline installer found: installers\OllamaSetup.exe
    echo   [..] Installing silently (no internet required)...
    goto :do_install_ollama
)

echo   [!] Offline installer not found in installers\ folder.
echo   [..] Attempting download from ollama.com...
echo.

curl --progress-bar -L -o "%XIA_OLLAMA_INSTALLER%" "%OLLAMA_DOWNLOAD_URL%"
if !errorlevel! neq 0 (
    del /f /q "%XIA_OLLAMA_INSTALLER%" >nul 2>&1
    echo.
    echo  ================================================================
    echo   [OFFLINE] Cannot install Ollama automatically.
    echo.
    echo   Option A - Copy installer to SSD ^(Recommended^):
    echo     1. On a machine with internet, download:
    echo        https://ollama.com/download/OllamaSetup.exe
    echo     2. Place it here:
    echo        %XIA_OLLAMA_INSTALLER%
    echo     3. Re-run run.bat
    echo.
    echo   Option B - Install Ollama manually:
    echo     1. Install from https://ollama.com
    echo     2. Re-run run.bat
    echo  ================================================================
    echo.
    pause >nul
    exit /b 1
)
echo   [OK] Download complete. Cached for offline use.

:do_install_ollama
echo   [..] Running installer, please wait (this can take a moment)...
start /wait "" "%XIA_OLLAMA_INSTALLER%" /S

:: Verify it was installed and add to path
if exist "%OLLAMA_DEFAULT%\ollama.exe" (
    set "PATH=%OLLAMA_DEFAULT%;%PATH%"
)

where ollama >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo   [ERROR] Ollama installed but not found in PATH.
    echo   Restart this terminal or your machine, then re-run run.bat.
    echo.
    pause >nul
    exit /b 1
)
echo   [OK] Ollama installed.

:: ================================================================
::  [5/6] OLLAMA SERVER
:: ================================================================
:step5_server
echo.
echo  [5/%TOTAL_STEPS%] Starting Ollama server...

start "" /B ollama serve >nul 2>&1

set "OLLAMA_READY=0"
for /L %%i in (1,1,15) do (
    if "!OLLAMA_READY!" == "0" (
        curl -s http://localhost:11434/api/tags >nul 2>&1
        if !errorlevel! equ 0 (
            set "OLLAMA_READY=1"
            echo   [OK] Ollama server ready ^(%%is^).
        ) else (
            ping -n 1 -w 500 127.0.0.1 >nul 2>&1
        )
    )
)

if "!OLLAMA_READY!" == "0" (
    echo   [!] Ollama slow to start - xia will retry on first request.
)

:: ================================================================
::  [6/6] LAUNCH XIA
:: ================================================================
echo.
echo  [6/%TOTAL_STEPS%] Launching xia...
echo  ================================================================
echo.

"%XIA_PYTHON%" "%XIA_ROOT%\launch.py"
set "XIA_EXIT=!errorlevel!"

echo.
if "!XIA_EXIT!" == "0" (
    echo  ================================================================
    echo   xia exited cleanly.
    echo  ================================================================
) else (
    echo  ================================================================
    echo   [ERROR] xia exited with code !XIA_EXIT!
    echo   Check logs: %XIA_ROOT%\logs\xia.log
    echo  ================================================================
    echo.
    pause >nul
)
goto :eof

:: ================================================================
::  SUBROUTINE: Locate a working system Python installation
::  Sets SYS_PYTHON variable, or leaves it empty if not found
:: ================================================================
:find_system_python
set "SYS_PYTHON="

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" --version >nul 2>&1
        if !errorlevel! equ 0 set "SYS_PYTHON=%%D\python.exe"
    )
)
if defined SYS_PYTHON exit /b 0

for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" --version >nul 2>&1
        if !errorlevel! equ 0 set "SYS_PYTHON=%%D\python.exe"
    )
)
if defined SYS_PYTHON exit /b 0

where py >nul 2>&1
if !errorlevel! equ 0 (
    py --version >nul 2>&1
    if !errorlevel! equ 0 ( set "SYS_PYTHON=py" & exit /b 0 )
)

where python >nul 2>&1
if !errorlevel! equ 0 (
    python --version >nul 2>&1
    if !errorlevel! equ 0 ( set "SYS_PYTHON=python" & exit /b 0 )
)

where python3 >nul 2>&1
if !errorlevel! equ 0 (
    python3 --version >nul 2>&1
    if !errorlevel! equ 0 ( set "SYS_PYTHON=python3" & exit /b 0 )
)

exit /b 0
