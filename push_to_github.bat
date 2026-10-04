@echo off
REM Push Discord Bot to GitHub
REM Usage: push_to_github.bat https://github.com/YOUR_USERNAME/discord-bot.git

echo.
echo 🚀 Discord Bot GitHub Push Script
echo ==================================
echo.

REM Check if repo URL provided
if "%1"=="" (
    echo ❌ No GitHub URL provided!
    echo.
    echo Usage: push_to_github.bat https://github.com/YOUR_USERNAME/discord-bot.git
    echo.
    echo Steps:
    echo 1. Create repo at https://github.com/new
    echo 2. Copy the repo URL (https://github.com/YOUR_USERNAME/discord-bot.git)
    echo 3. Run this script with that URL
    echo.
    pause
    exit /b 1
)

set REPO_URL=%1

echo Repository URL: %REPO_URL%
echo.

REM Check if git is installed
git --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Git is not installed!
    echo.
    echo Install Git from: https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)

REM Initialize git
echo Initializing git repository...
if not exist .git (
    call git init
    echo ✅ Git initialized
) else (
    echo ✅ Git already initialized
)

REM Configure git (first time setup)
git config user.name "Discord Bot User" >nul 2>&1
git config user.email "bot@discord.local" >nul 2>&1

REM Add all files
echo Adding files...
call git add .
echo ✅ Files added

REM Create commit
echo Creating commit...
call git commit -m "Discord bot: Initial commit with activity tracking, fun replies, and daily throwback" >nul 2>&1
if errorlevel 1 (
    echo ⚠️  (No new changes to commit)
) else (
    echo ✅ Commit created
)

REM Check if remote already exists
for /f %%i in ('git remote') do if "%%i"=="origin" (
    echo Removing existing remote...
    call git remote remove origin
)

REM Add remote
echo Adding remote...
call git remote add origin %REPO_URL%
echo ✅ Remote added

REM Ensure main branch
echo Checking branch...
git rev-parse --verify main >nul 2>&1
if errorlevel 1 (
    echo Renaming branch to main...
    call git branch -M main
    echo ✅ Branch set to main
) else (
    echo ✅ Main branch exists
)

REM Push to GitHub
echo.
echo Pushing to GitHub...
echo (You may be prompted for authentication)
echo.

call git push -u origin main

if errorlevel 1 (
    echo.
    echo ❌ Failed to push to GitHub
    echo.
    echo Common issues:
    echo - Authentication failed: Check your GitHub credentials
    echo - Repository URL wrong: Verify the URL
    echo - Remote already exists: Run "git remote -v" to check
    echo.
    pause
    exit /b 1
) else (
    echo.
    echo ✅ Successfully pushed to GitHub!
    echo.
    echo Your repository: %REPO_URL%
    echo.
    echo Next steps:
    echo 1. Go to Railway.app
    echo 2. Create new project
    echo 3. Deploy from GitHub repo
    echo 4. Follow SETUP_RAILWAY.md
    echo.
    pause
)
