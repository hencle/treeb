@echo off
setlocal

REM Define paths (good practice even in minimal scripts)
set "VENV_DIR=.venv"
set "VENV_PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP_EXE=%VENV_DIR%\Scripts\pip.exe"
set "REQUIREMENTS_FILE=requirements.txt"

echo --- Treeb Setup ---

REM Check for system Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH. Please install Python 3.7+
    pause
    exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist "%VENV_PYTHON_EXE%" (
    echo Creating virtual environment in "%VENV_DIR%"...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Activating virtual environment and installing/checking dependencies...
REM Using explicit paths for pip is generally more robust than relying on activate alone
REM Attempt to upgrade pip (silently)
"%VENV_PYTHON_EXE%" -m pip install --upgrade pip >nul 2>&1

REM Install requirements
"%VENV_PIP_EXE%" install -r "%REQUIREMENTS_FILE%"
if errorlevel 1 (
    echo ERROR: Failed to install dependencies from %REQUIREMENTS_FILE%.
    pause
    exit /b 1
)

echo --- Starting Treeb Application (http://127.0.0.1:5000) ---
"%VENV_PYTHON_EXE%" app.py
if errorlevel 1 (
    echo ERROR: Failed to start Treeb application.
)

echo.
pause
endlocal