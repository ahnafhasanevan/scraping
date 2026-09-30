@echo off
REM ==========================================================================
REM  One-click runner for Windows.
REM  First run: creates a virtual environment and installs the requirements.
REM  Double-click to scrape every university, or pass arguments, e.g.:
REM      run_windows.bat --university ewu ulab --format xlsx
REM  Output: C:\Users\Hp\Downloads\Faculty Photo and Codes  (see config.py)
REM ==========================================================================
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")

if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment ...
    %PY% -m venv venv
    if errorlevel 1 goto :nopython
)
call "venv\Scripts\activate.bat"

echo Installing / checking requirements ...
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :pipfail

if "%~1"=="" (
    python main.py --all --format csv xlsx
) else (
    python main.py %*
)
echo.
pause
exit /b 0

:nopython
echo Python 3.9 or newer was not found.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
pause
exit /b 1

:pipfail
echo Installing the requirements failed. Check your internet connection and try again.
pause
exit /b 1
