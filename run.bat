@echo off
REM Discord Bot Runner Script for Windows

echo.
echo 🤖 Discord Bot Launcher
echo ================================
echo.

REM Check if .env file exists
if not exist ".env" (
    echo ❌ .env file not found!
    echo.
    echo Please copy .env.example to .env and configure it:
    echo   copy .env.example .env
    echo   notepad .env
    echo.
    pause
    exit /b 1
)

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found!
    echo.
    echo Please install Python 3.8 or higher from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

REM Check if venv exists, create if not
if not exist "venv" (
    echo Creating Python virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo ❌ Failed to create virtual environment
        pause
        exit /b 1
    )
)

REM Activate venv
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install/update dependencies
echo Installing dependencies...
pip install -q -r requirements.txt

if errorlevel 1 (
    echo ❌ Failed to install dependencies
    pause
    exit /b 1
)

REM Run the bot
echo.
echo ✅ Starting bot...
echo Press Ctrl+C to stop
echo.

python -m bot.main

pause
