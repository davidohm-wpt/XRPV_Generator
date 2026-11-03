@echo off
title One-time fix for Push
cd /d "%~dp0"
set GIT=%~dp0PortableGit\bin\git.exe
echo Removing the unpushed commit that contains the big .zip file...
echo (your files are NOT deleted - only the Git commit is reset)
"%GIT%" fetch origin main
"%GIT%" reset origin/main
echo.
echo Done. Now run Push.bat again.
pause
