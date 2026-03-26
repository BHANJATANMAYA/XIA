@echo off
setlocal EnableDelayedExpansion
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
title xia - Starting...

:: ================================================================
::  xia - Offline-First Self-Bootstrapping Launcher v2.0
::
::  Works 100%% offline if installers\ folder is pre-bundled.
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

:: Locate SSD root (always relative, drive-letter agnostic)
set "XIA_ROOT=%~dp0"
if "%XIA_ROOT:~-1%"=="\" set "XIA_ROOT=%XIA_ROOT:~0,-1%"

:: Key paths
set "XIA_VENV=%XIA_ROOT%\.venv"
set "XIA_PYTHON=%XIA_VENV%\Scripts\python.exe"
set "XIA_INSTALLERS=%XIA_ROOT%\installers"
set "XIA_PY_INSTALLER=%XIA_INSTALLERS%\python-3.12.4-amd64.exe"
set "XIA_OLLAMA_INSTALLER=%XIA_INSTALLERS%\OllamaSetup.exe"
set "PY_DOWNLOAD_URL=https://www.python.org/ftp/python/3.12.4/python-3.12.4-amd64.exe"
set "OLLAMA_DOWNLOAD_URL=https://ollama.com/download/OllamaSetup.exe"
set "SYS_PYTHON="
set "TOTAL_STEPS=6"

:: Set Ollama storage paths BEFORE anything starts
:: Ollama reads these only on startup - must be set first
set "OLLAMA_MODELS=%XIA_ROOT%\models\ollama"
set "OLLAMA_HOME=%XIA_ROOT%\models\ollama"
setx OLLAMA_MODELS "%XIA_ROOT%\models\ollama" >nul 2>&1
setx OLLAMA_HOME   "%XIA_ROOT%\models\ollama" >nul 2>&1

:: Header
echo.
echo  ================================================================
echo   xia  ^|  Portable AI Agent  ^|  Offline-First Launcher v2.0
echo  ================================================================
echo   Root     : %XIA_ROOT%
echo   Models   : %OLLAMA_MODELS%
echo   Bundles  : %XIA_INSTALLERS%
echo  ================================================================
echo.

:: Ensure required folders exist
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
