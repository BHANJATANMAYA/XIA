@echo off
setlocal EnableDelayedExpansion
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
title xia - Starting...

REM -- Locate SSD root (always relative, drive-letter agnostic)
set "XIA_ROOT=%~dp0"
if "%XIA_ROOT:~-1%"=="\" set "XIA_ROOT=%XIA_ROOT:~0,-1%"

REM -- Key paths
set "XIA_VENV=%XIA_ROOT%\.venv"
set "XIA_PYTHON=%XIA_VENV%\Scripts\python.exe"
set "XIA_INSTALLERS=%XIA_ROOT%\installers"
set "XIA_PY_INSTALLER=%XIA_INSTALLERS%\python-3.12.4-amd64.exe"
set "XIA_OLLAMA_INSTALLER=%XIA_INSTALLERS%\OllamaSetup.exe"
set "PY_DOWNLOAD_URL=https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
set "OLLAMA_DOWNLOAD_URL=https://ollama.com/download/OllamaSetup.exe"
set "SYS_PYTHON="

REM -- Set Ollama and Cache storage paths BEFORE anything starts
set "OLLAMA_MODELS=%XIA_ROOT%\models\ollama"
set "OLLAMA_HOME=%XIA_ROOT%\models\ollama"
set "PLAYWRIGHT_BROWSERS_PATH=%XIA_ROOT%\models\playwright"
set "HF_HOME=%XIA_ROOT%\models\hf_home"
set "PIP_NO_CACHE_DIR=1"

REM -- Fast Path: If venv works, jump straight to launch.py
if exist "%XIA_PYTHON%" (
    "%XIA_PYTHON%" --version >nul 2>&1
    if !errorlevel! equ 0 (
        "%XIA_PYTHON%" "%XIA_ROOT%\launch.py"
        exit /b !errorlevel!
    )
    REM Venv exists but won't run (e.g. stale from another machine)
    rmdir /s /q "%XIA_VENV%" >nul 2>&1
)

REM -- Setup Mode Header
echo.
echo   xia  -  initial setup...
echo.

if not exist "%XIA_INSTALLERS%"    mkdir "%XIA_INSTALLERS%"
if not exist "%OLLAMA_MODELS%"     mkdir "%OLLAMA_MODELS%"

REM -- Step 1: Find or Install Python
echo   *  checking host python...

call :find_system_python
if defined SYS_PYTHON (
    echo      - found system python: !SYS_PYTHON!
    goto :build_venv
)

echo      - host python not found
echo   *  downloading python 3.12.4...
if exist "%XIA_PY_INSTALLER%" (
    echo      - using cached installers\python-3.12.4-amd64.exe
    goto :install_python
)

curl -L -o "%XIA_PY_INSTALLER%" "%PY_DOWNLOAD_URL%"
if !errorlevel! neq 0 (
    del /f /q "%XIA_PY_INSTALLER%" >nul 2>&1
    echo.
    echo   [ERROR] Cannot download Python automatically.
    echo   Please install Python 3.11+ manually and re-run run.bat.
    echo.
    pause >nul
    exit /b 1
)

:install_python
echo   *  installing python 3.12.4 (please wait)...
"%XIA_PY_INSTALLER%" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1 Include_test=0 Include_doc=0
if !errorlevel! neq 0 (
    echo.
    echo   [ERROR] Python installation failed (code: !errorlevel!).
    echo   Try running manually: %XIA_PY_INSTALLER%
    echo.
    pause >nul
    exit /b 1
)

call :find_system_python
if not defined SYS_PYTHON (
    echo.
    echo   [ERROR] Python installed but cannot be located in PATH.
    echo   Please restart this terminal window and re-run run.bat.
    echo.
    pause >nul
    exit /b 1
)

:build_venv
echo   *  building virtual environment...
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

REM -- Step 2: Handoff to launch.py
echo      - virtual environment ready
echo.
"%XIA_PYTHON%" "%XIA_ROOT%\launch.py"
exit /b !errorlevel!

REM -- Subroutine: Locate System Python
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
