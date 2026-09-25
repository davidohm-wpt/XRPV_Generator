@echo off
title Push to GitHub - XRPV Generator
cd /d "%~dp0"
set GIT=%~dp0PortableGit\bin\git.exe

echo ===================================================
echo   Push to GitHub - XRPV Generator
echo ===================================================
echo.

if not exist "%GIT%" (
    echo [Error] PortableGit not found.
    pause
    exit /b 1
)

echo [1/4] Pulling latest...
"%GIT%" pull --rebase origin main
echo.

echo [2/4] Staging changes...
"%GIT%" add -A
echo.

echo [3/4] Committing...
set /p COMMIT_MSG="Commit message: "
if "%COMMIT_MSG%"=="" set COMMIT_MSG=Auto-update
"%GIT%" commit -m "%COMMIT_MSG%"
echo.

echo [4/4] Pushing...
"%GIT%" push origin main
if %errorlevel% neq 0 (
    echo.
    echo [Error] Push failed. Check message above.
    pause
    exit /b 1
)

echo.
echo ===================================================
echo   SUCCESS! Pushed to GitHub.
echo ===================================================
timeout /t 3