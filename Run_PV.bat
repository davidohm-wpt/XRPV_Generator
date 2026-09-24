@echo off
title WIPOTEC PV Certificate System - Launcher
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: Clean up previous run artifacts
if exist "%~dp0weasyprint_check_error.log" del /q "%~dp0weasyprint_check_error.log"

:: Read app version from VERSION.txt if present
set APP_VERSION=unknown
if exist "%~dp0VERSION.txt" (
    set /p APP_VERSION=<"%~dp0VERSION.txt"
)
title WIPOTEC PV Certificate System - Launcher (v!APP_VERSION!)
echo ===================================================
echo   WIPOTEC PV Certificate System - Version !APP_VERSION!
echo ===================================================

:: Fallback installers (only used if no portable folder is present and admin rights are available)
set PYTHON_INSTALLER=python-manager-26.3.msix
set GTK_INSTALLER=gtk3-runtime-3.24.31-2022-01-04-ts-win64.exe

:: Portable folders (preferred, no admin needed)
set PORTABLE_PYTHON=%~dp0PythonPortable\python.exe
set PORTABLE_GTK_BIN=%~dp0GTK3-Runtime\bin

set PYTHON_CMD=python
set USING_PORTABLE_PYTHON=0

echo ===================================================
echo   Checking Python...
echo ===================================================

if exist "!PORTABLE_PYTHON!" (
    echo Found portable Python next to this file - no installation needed.
    set PYTHON_CMD="!PORTABLE_PYTHON!"
    set USING_PORTABLE_PYTHON=1
) else (
    python --version >nul 2>&1
    if !errorlevel! neq 0 (
        echo Python not found! Trying to install Python automatically...
        if exist "%~dp0%PYTHON_INSTALLER%" (
            echo Installing .msix package... Please wait...
            powershell -Command "Add-AppxPackage -Path '%~dp0%PYTHON_INSTALLER%'"
            echo Python installation completed.
        ) else (
            echo [Error] Cannot find %PYTHON_INSTALLER% in the folder, and no
            echo PythonPortable folder was found next to this file either.
            echo This computer may not have permission to install Python -
            echo see PORTABLE_SETUP_GUIDE.md for a no-admin-required option.
            pause
            exit /b 1
        )
    ) else (
        echo Python is already installed. Skipping installation.
    )
)

echo ===================================================
echo   Checking GTK3 Runtime...
echo ===================================================

if exist "!PORTABLE_GTK_BIN!" (
    echo Found portable GTK3 runtime next to this file - adding it to PATH
    echo for this session ^(no installation needed^). This also includes
    echo the Visual C++ Runtime DLLs, so no admin rights are required.
    set "PATH=!PORTABLE_GTK_BIN!;!PATH!"
) else (
    if not exist "C:\Program Files\GTK3-Runtime Win64" (
        if not exist "C:\Program Files (x86)\GTK3-Runtime Win64" (
            echo GTK3 not found! Trying to install GTK3 automatically...
            if exist "%~dp0%GTK_INSTALLER%" (
                "%~dp0%GTK_INSTALLER%" /S
                echo GTK3 installation completed.
            ) else (
                echo [Error] Cannot find %GTK_INSTALLER% in the folder, and no
                echo GTK3-Runtime portable folder was found next to this file either.
                echo This computer may not have permission to install GTK3 -
                echo see PORTABLE_SETUP_GUIDE.md for a no-admin-required option.
                pause
                exit /b 1
            )
        ) else (
            echo GTK3 is already installed. Skipping installation.
        )
    ) else (
        echo GTK3 is already installed. Skipping installation.
    )
)

echo ===================================================
echo   Checking required Python packages...
echo ===================================================

:: *** ใช้ runpy.run_path() เพื่อตั้ง __file__ ให้ถูกต้อง และให้ main.py
::     รัน GTK3 preload setup ก่อน import weasyprint ***
!PYTHON_CMD! -c "import runpy, sys; sys.argv=['main']; runpy.run_path('main.py', run_name='__not_main__')" >nul 2>weasyprint_check_error.log
if !errorlevel! neq 0 (
    echo Some required Python packages are missing or failed to load. Installing
    echo ^(one-time step, needs internet access, may take a minute^)...
    if "!USING_PORTABLE_PYTHON!"=="1" (
        !PYTHON_CMD! -m pip install fastapi "uvicorn[standard]" jinja2 weasyprint
    ) else (
        !PYTHON_CMD! -m pip install --user fastapi "uvicorn[standard]" jinja2 weasyprint
    )
    echo Verifying the packages can actually be loaded...
    !PYTHON_CMD! -c "import runpy, sys; sys.argv=['main']; runpy.run_path('main.py', run_name='__not_main__')" >nul 2>weasyprint_check_error.log
    if !errorlevel! neq 0 (
        echo ===================================================
        echo [Error] The Python packages are installed, but one of
        echo them failed to load ^(this is usually WeasyPrint not
        echo finding the GTK3 runtime^). The exact error is below,
        echo and was also saved to weasyprint_check_error.log in
        echo this folder - please send that file for help:
        echo ---------------------------------------------------
        type weasyprint_check_error.log
        echo ---------------------------------------------------
        pause
        exit /b 1
    )
    echo Required Python packages installed and verified successfully.
) else (
    echo Required Python packages are already installed. Skipping.
)

echo ===================================================
echo   Checking and Installing Thai Font (Sarabun)...
echo ===================================================

set FONT_DIR=%LOCALAPPDATA%\Microsoft\Windows\Fonts
if not exist "%FONT_DIR%" mkdir "%FONT_DIR%"

if exist "%~dp0Sarabun-Regular.ttf" (
    if exist "%FONT_DIR%\Sarabun-Regular.ttf" (
        echo Sarabun-Regular.ttf already exists. Skipping.
    ) else (
        echo Installing Sarabun-Regular.ttf...
        copy /y "%~dp0Sarabun-Regular.ttf" "%FONT_DIR%\" >nul
        reg add "HKCU\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts" /v "Sarabun Regular (TrueType)" /t REG_SZ /d "%FONT_DIR%\Sarabun-Regular.ttf" /f >nul
    )
)

if exist "%~dp0Sarabun-Bold.ttf" (
    if exist "%FONT_DIR%\Sarabun-Bold.ttf" (
        echo Sarabun-Bold.ttf already exists. Skipping.
    ) else (
        echo Installing Sarabun-Bold.ttf...
        copy /y "%~dp0Sarabun-Bold.ttf" "%FONT_DIR%\" >nul
        reg add "HKCU\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts" /v "Sarabun Bold (TrueType)" /t REG_SZ /d "%FONT_DIR%\Sarabun-Bold.ttf" /f >nul
    )
)

echo ===================================================
echo   Starting WIPOTEC PV Certificate System
echo ===================================================

:: Start FastAPI backend minimized, logging to pv_server.log
start /min "WIPOTEC PV Server" cmd /k !PYTHON_CMD! main.py

echo Waiting for the server to start...

set SERVER_READY=0
for /L %%i in (1,1,60) do (
    if "!SERVER_READY!"=="0" (
        powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
        if !errorlevel! equ 0 (
            set SERVER_READY=1
        ) else (
            if %%i equ 3 (
                echo Still waiting... if a Windows Firewall popup appeared asking
                echo about python.exe, click "Allow access" to continue.
            )
            if %%i equ 30 (
                echo Still waiting... this can take longer on computers with many
                echo apps installed. Please keep waiting a bit more.
            )
            timeout /t 2 /nobreak >nul
        )
    )
)

:: Open the web page in the default browser
start "" "http://127.0.0.1:8000/index.html"

echo ===================================================
if "!SERVER_READY!"=="1" (
    echo The system is ready. The server is running minimized
    echo in the taskbar as "WIPOTEC PV Server" - you normally
    echo don't need to open it. If the web page stops working,
    echo open that window from the taskbar to see the error,
    echo or close it and run this file again to restart.
) else (
    echo [Warning] The server did not respond within the timeout.
    echo Opening the page anyway, but it may show an error. Check
    echo the "WIPOTEC PV Server" window in the taskbar for details,
    echo and make sure to click "Allow access" if a Windows Firewall
    echo popup is waiting there. If you see "Uvicorn running on..."
    echo in that window, just refresh the web page - it is ready.
)
echo ===================================================
echo This window will close automatically in a few seconds.
timeout /t 6
exit /b 0