@echo off
REM WIPOTEC AIO Software - starts the installer window (Setup.ps1).
cd /d "%~dp0"
if not exist "%~dp0Setup.ps1" goto :notextracted
if not exist "%~dp0XRPV_files.zip" goto :notextracted
start "" "%WINDIR%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0Setup.ps1"
exit /b 0

:notextracted
echo.
echo   The installer has to be extracted first.
echo.
echo   1. Close this window.
echo   2. Right-click the zip file you received and choose "Extract All...".
echo   3. Open the extracted folder and double-click "Install WIPOTEC AIO Software".
echo.
pause
exit /b 1
