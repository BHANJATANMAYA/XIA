@echo off
setlocal EnableDelayedExpansion
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
title xia - Starting...

REM -- Locate root (always relative to this .bat file, drive-letter agnostic)
set "XIA_ROOT=%~dp0"
if "%XIA_ROOT:~-1%"=="\" set "XIA_ROOT=%XIA_ROOT:~0,-1%"

REM -- Key paths
set "XIA_VENV=%XIA_ROOT%\.venv"
set "XIA_PYTHON=%XIA_VENV%\Scripts\python.exe"
set "SYS_PYTHON="

REM -- Ollama and cache storage paths (portable, no host footprint)
set "OLLAMA_MODELS=%XIA_ROOT%\models\ollama"
set "OLLAMA_HOME=%XIA_ROOT%\models\ollama"
set "PLAYWRIGHT_BROWSERS_PATH=%XIA_ROOT%\models\playwright"
set "HF_HOME=%XIA_ROOT%\models\hf_home"
set "PIP_NO_CACHE_DIR=1"

REM ============================================================
REM  FAST PATH: venv exists and all core modules import cleanly
REM ============================================================
if exist "%XIA_PYTHON%" (
    "%XIA_PYTHON%" -c "import pip, dotenv, yaml, rich, ollama" >nul 2>&1
    if !errorlevel! equ 0 (
        "%XIA_PYTHON%" "%XIA_ROOT%\launch.py"
        exit /b !errorlevel!
    )
)

REM ============================================================
REM  SETUP MODE: venv missing, broken or stale
REM ============================================================
echo.
echo   xia  -  initial setup...
echo.

if not exist "%XIA_ROOT%\models\ollama" mkdir "%XIA_ROOT%\models\ollama"

REM -- Step 1: Find system Python ------------------------------------------
echo   *  checking host python...

call :find_system_python
if defined SYS_PYTHON (
    echo      - found system python: !SYS_PYTHON!
    goto :delete_old_venv
)

echo      - host python not found
echo.
echo   [ERROR] Python 3.11+ is required but was not found on this machine.
echo   Please install Python from https://python.org and re-run run.bat.
echo.
pause >nul
exit /b 1

REM -- Step 2: Delete stale/locked venv ------------------------------------
:delete_old_venv
if not exist "%XIA_VENV%" goto :build_venv

echo   *  removing old virtual environment...
rd /s /q "%XIA_VENV%" >nul 2>&1

if exist "%XIA_VENV%" (
    echo      - retrying deletion (files may be in use)...
    timeout /t 2 /nobreak >nul
    rd /s /q "%XIA_VENV%" >nul 2>&1
)

if exist "%XIA_VENV%" (
    echo.
    echo   [ERROR] Cannot delete old .venv - files are locked by another process.
    echo   Close any terminals or programs using xia, then re-run run.bat.
    echo.
    pause >nul
    exit /b 1
)

REM -- Step 3: Build fresh venv --------------------------------------------
:build_venv
echo   *  building virtual environment...

"!SYS_PYTHON!" -m venv "%XIA_VENV%"
if !errorlevel! neq 0 (
    echo.
    echo   [ERROR] Failed to create virtual environment.
    echo   Try running run.bat as Administrator, or check that %XIA_ROOT% is writable.
    echo.
    pause >nul
    exit /b 1
)

"%XIA_PYTHON%" -c "import sys" >nul 2>&1
if !errorlevel! neq 0 (
    echo.
    echo   [ERROR] New venv is broken. Re-run run.bat to try again.
    echo.
    pause >nul
    exit /b 1
)

REM -- Step 4: Bootstrap pip (use system pip to avoid TLS cert issues) -----
echo   *  bootstrapping pip...

REM Upgrade pip inside the venv via system python (bypasses certifi path bug)
"!SYS_PYTHON!" -m pip install --quiet --upgrade pip --target "%XIA_VENV%\Lib\site-packages" >nul 2>&1
if !errorlevel! neq 0 (
    REM Fallback: use ensurepip bundled with Python
    "%XIA_PYTHON%" -m ensurepip --upgrade >nul 2>&1
)

REM -- Step 5: Handoff to launch.py ----------------------------------------
echo      - virtual environment ready
echo.
"%XIA_PYTHON%" "%XIA_ROOT%\launch.py"
exit /b !errorlevel!


REM ============================================================
REM  SUBROUTINE: Locate system Python 3.11+
REM ============================================================
:find_system_python
set "SYS_PYTHON="

REM User-installed Python (most common path on Windows)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "SYS_PYTHON=%%D\python.exe"
    )
)
if defined SYS_PYTHON exit /b 0

REM System-wide Python installs
for /d %%D in ("%ProgramFiles%\Python3*") do (
    if exist "%%D\python.exe" (
        "%%D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "SYS_PYTHON=%%D\python.exe"
    )
)
if defined SYS_PYTHON exit /b 0

REM Try py launcher
where py >nul 2>&1
if !errorlevel! equ 0 (
    py -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if !errorlevel! equ 0 ( set "SYS_PYTHON=py" & exit /b 0 )
)

REM Try python in PATH
where python >nul 2>&1
if !errorlevel! equ 0 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if !errorlevel! equ 0 ( set "SYS_PYTHON=python" & exit /b 0 )
)

REM Try python3 in PATH
where python3 >nul 2>&1
if !errorlevel! equ 0 (
    python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if !errorlevel! equ 0 ( set "SYS_PYTHON=python3" & exit /b 0 )
)

exit /b 0
