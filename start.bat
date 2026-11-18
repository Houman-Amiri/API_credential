@echo off
setlocal EnableExtensions
title PSN Checker - Launcher
cd /d "%~dp0"
if not defined TEMP set "TEMP=%~dp0"
set "PYTMP=%TEMP%\psn_python_path.tmp"

rem UTF-8 so the app's Persian messages are readable in the console
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"

echo.
echo ============================================================
echo   PSN Checker - one click launcher
echo ============================================================
echo.

if not exist "%~dp0bootstrap.py" (
  echo [X] bootstrap.py is missing next to start.bat
  goto :failed
)
if not exist "%~dp0PSN Checker.py" (
  echo [X] "PSN Checker.py" is missing next to start.bat
  goto :failed
)

call :detect
if not defined PYTHON (
  echo [i] No suitable Python 3.9+ with tkinter found. Installing it now...
  call :install_python
  call :detect
)
if not defined PYTHON (
  echo [X] Python 3.9+ with tkinter could not be found or installed.
  echo     Install it manually from https://www.python.org/downloads/windows/
  echo     Tick "Add python.exe to PATH" and "tcl/tk and IDLE", then run this file again.
  goto :failed
)

echo [*] Python: "%PYTHON%"
echo [*] Checking dependencies - anything missing is downloaded automatically.
echo.
"%PYTHON%" "%~dp0bootstrap.py"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [X] Launch failed - exit code %RC%. See the messages above.
  echo.
  pause
)
exit /b %RC%

:failed
echo.
echo [X] Could not start. See the messages above.
echo.
pause
exit /b 1


rem ---------------- find a usable Python -------------------------
:detect
set "PYTHON="
call :try_cmd "py -3"
call :validate
if defined PYTHON exit /b 0
call :try_cmd "python"
call :validate
if defined PYTHON exit /b 0
call :try_cmd "python3"
call :validate
if defined PYTHON exit /b 0
for %%V in (314 313 312 311 310) do (
  call :try_path "%LOCALAPPDATA%\Programs\Python\Python%%V\python.exe"
  call :validate
  if defined PYTHON exit /b 0
  call :try_path "%ProgramFiles%\Python%%V\python.exe"
  call :validate
  if defined PYTHON exit /b 0
)
exit /b 0

rem Try a command on PATH (py -3, python, python3).
:try_cmd
set "CAND="
del "%PYTMP%" >nul 2>&1
%~1 -c "import sys;print(sys.executable)" > "%PYTMP%" 2>nul
if errorlevel 1 exit /b 0
if not exist "%PYTMP%" exit /b 0
set /p CAND=<"%PYTMP%"
exit /b 0

rem Try an explicit install path (PATH is not refreshed after installing Python).
:try_path
set "CAND="
if not exist "%~1" exit /b 0
del "%PYTMP%" >nul 2>&1
"%~1" -c "import sys;print(sys.executable)" > "%PYTMP%" 2>nul
if errorlevel 1 exit /b 0
if not exist "%PYTMP%" exit /b 0
set /p CAND=<"%PYTMP%"
exit /b 0

:validate
if not defined CAND exit /b 0
if not exist "%CAND%" exit /b 0
"%CAND%" -c "import sys,tkinter;sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "PYTHON=%CAND%"
exit /b 0


rem ---------------- install Python if absent ---------------------
:install_python
where winget >nul 2>&1
if not errorlevel 1 (
  echo [*] winget found - installing Python 3.12 ...
  winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
  if not errorlevel 1 exit /b 0
)
echo [*] Downloading the official Python installer ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ErrorActionPreference='Stop'; $url='https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe'; $out=Join-Path $env:TEMP 'python-3.12.7-amd64.exe'; Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing; Start-Process -FilePath $out -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_tcltk=1 Include_pip=1 Include_launcher=1' -Wait"
exit /b 0
