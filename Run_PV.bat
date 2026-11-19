@echo off
title WIPOTEC PV Certificate System - Launcher
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: ============================================================
:: Auto-update source code from GitHub
:: ============================================================
:: ใช้ git pull เพื่อดึงเฉพาะไฟล์ที่เปลี่ยน (เร็วมาก)
:: ไฟล์ที่ถูก ignore (PythonPortable, GTK3-Runtime) จะไม่ถูกลบ
:: ============================================================

set GIT_EXE=%~dp0PortableGit\bin\git.exe
set GITHUB_REPO=https://github.com/davidohm-wpt/XRPV_Generator.git
set GITHUB_BRANCH=main

if exist "!GIT_EXE!" (
    echo ===================================================
    echo   Checking for updates from GitHub...
    echo ===================================================

    if exist "%~dp0.git" (
        :: มี .git อยู่แล้ว → pull (ดึงเฉพาะที่เปลี่ยน)
        REM Safety: "reset --hard" would silently wipe local work, so the update is
        REM skipped when there are uncommitted edits, unpushed commits, or another
        REM branch is checked out - for example while testing a fix before pushing it.
        pushd "%~dp0"
        "!GIT_EXE!" fetch origin !GITHUB_BRANCH! >nul 2>&1
        if !errorlevel! neq 0 (
            echo [Warning] Cannot reach GitHub - using local files.
        ) else (
            set LOCAL_CHANGES=
            set CUR_BRANCH=
            set AHEAD=0
            for /f "delims=" %%L in ('PortableGit\bin\git.exe status --porcelain -uno 2^>nul') do set LOCAL_CHANGES=1
            for /f "delims=" %%B in ('PortableGit\bin\git.exe rev-parse --abbrev-ref HEAD 2^>nul') do set CUR_BRANCH=%%B
            for /f "delims=" %%N in ('PortableGit\bin\git.exe rev-list --count origin/%GITHUB_BRANCH%..HEAD 2^>nul') do set AHEAD=%%N
            REM Checked from least to most important - the last match is the one shown.
            set SKIP_REASON=
            if not "!AHEAD!"=="0" set SKIP_REASON=there are !AHEAD! local commit[s] not pushed to GitHub yet
            if not "!CUR_BRANCH!"=="%GITHUB_BRANCH%" set SKIP_REASON=branch "!CUR_BRANCH!" is checked out, not %GITHUB_BRANCH%
            if defined LOCAL_CHANGES set SKIP_REASON=there are local file changes that are not committed
            if defined SKIP_REASON (
                echo [Update skipped] !SKIP_REASON!.
                echo                  Using local files so your work is not overwritten.
                echo                  Push your work - or discard it - to get updates again.
            ) else (
                "!GIT_EXE!" reset --hard origin/!GITHUB_BRANCH! >nul 2>&1
                if !errorlevel! neq 0 (
                    echo [Warning] git reset failed - using local files.
                ) else (
                    echo Update completed.
                )
            )
        )
        popd
    ) else (
        :: ยังไม่มี .git → clone (ครั้งแรก)
        echo First time setup - downloading source from GitHub...
        pushd "%~dp0"
        "!GIT_EXE!" init >nul 2>&1
        "!GIT_EXE!" remote add origin "!GITHUB_REPO!" >nul 2>&1
        "!GIT_EXE!" fetch origin !GITHUB_BRANCH! >nul 2>&1
        if !errorlevel! neq 0 (
            echo [Error] Cannot reach GitHub - will use local files.
        ) else (
            "!GIT_EXE!" checkout -f !GITHUB_BRANCH! >nul 2>&1
            if !errorlevel! neq 0 (
                "!GIT_EXE!" checkout -f -b !GITHUB_BRANCH! origin/!GITHUB_BRANCH! >nul 2>&1
            )
            echo Initial download completed.
        )
        popd
    )
) else (
    echo ===================================================
    echo   [Info] PortableGit not found - skipping GitHub update.
    echo   Expected at: %~dp0PortableGit\bin\git.exe
    echo ===================================================
)

REM Progress for the splash window (Launcher.ps1). Each step writes one line such as
REM "step:python"; "ready" or "error:..." ends it. XRPV_SPLASH is set when the splash
REM window started this script hidden, so nothing may wait for a key press.
REM NOTE: keep everything ABOVE this comment byte-identical. Older copies of this file
REM read themselves line by line while "git reset" replaces them, so changing earlier
REM lines would make them continue at the wrong position.
set "XRPV_STATUS=%TEMP%\xrpv_launch_status.txt"
>"%XRPV_STATUS%" echo step:checks

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

:: Fallback installers (only used if no portable folder is present)
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
>"%XRPV_STATUS%" echo step:python

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
            >"%XRPV_STATUS%" echo error:Python was not found - the PythonPortable folder is missing.
            if not defined XRPV_SPLASH pause
            exit /b 1
        )
    ) else (
        echo Python is already installed. Skipping installation.
    )
)

echo ===================================================
echo   Checking GTK3 Runtime...
echo ===================================================
>"%XRPV_STATUS%" echo step:gtk

if exist "!PORTABLE_GTK_BIN!" (
    echo Found portable GTK3 runtime next to this file - adding it to PATH.
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
                >"%XRPV_STATUS%" echo error:The PDF engine was not found - the GTK3-Runtime folder is missing.
                if not defined XRPV_SPLASH pause
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
>"%XRPV_STATUS%" echo step:packages

!PYTHON_CMD! -c "import runpy, sys; sys.argv=['main']; runpy.run_path('main.py', run_name='__not_main__')" >nul 2>weasyprint_check_error.log
if !errorlevel! neq 0 (
    echo Some required Python packages are missing or failed to load. Installing
    echo ^(one-time step, needs internet access, may take a minute^)...
    >"%XRPV_STATUS%" echo step:installing
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
        echo them failed to load. The exact error is below:
        echo ---------------------------------------------------
        type weasyprint_check_error.log
        echo ---------------------------------------------------
        >"%XRPV_STATUS%" echo error:A required Python package failed to load - see weasyprint_check_error.log.
        if not defined XRPV_SPLASH pause
        exit /b 1
    )
    echo Required Python packages installed and verified successfully.
) else (
    echo Required Python packages are already installed. Skipping.
)

echo ===================================================
echo   Checking and Installing Font (Sarabun)...
echo ===================================================
>"%XRPV_STATUS%" echo step:font

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

REM Create/refresh a Desktop shortcut with the WIPOTEC icon (no admin needed; safe to fail).
REM It opens the splash launcher (Launch.vbs) when present, otherwise this file.
if exist "%~dp0wipotec2.ico" if exist "%~dp0Launch.vbs" (
    powershell -NoProfile -Command "try { $p = Join-Path ([Environment]::GetFolderPath('Desktop')) 'WIPOTEC Certificates.lnk'; $s = (New-Object -ComObject WScript.Shell).CreateShortcut($p); $s.TargetPath = (Join-Path $env:WINDIR 'System32\wscript.exe'); $s.Arguments = [char]34 + '%~dp0Launch.vbs' + [char]34; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0wipotec2.ico'; $s.WindowStyle = 1; $s.Description = 'WIPOTEC Service Certificates'; $s.Save() } catch { }" >nul 2>&1
) else if exist "%~dp0wipotec2.ico" (
    powershell -NoProfile -Command "try { $p = Join-Path ([Environment]::GetFolderPath('Desktop')) 'WIPOTEC Certificates.lnk'; $s = (New-Object -ComObject WScript.Shell).CreateShortcut($p); $s.TargetPath = '%~dp0Run_PV.bat'; $s.WorkingDirectory = '%~dp0'; $s.IconLocation = '%~dp0wipotec2.ico'; $s.WindowStyle = 7; $s.Description = 'WIPOTEC Service Certificates'; $s.Save() } catch { }" >nul 2>&1
)

echo ===================================================
echo   Starting WIPOTEC PV Certificate System
echo ===================================================
>"%XRPV_STATUS%" echo step:server

REM Stop any server left running from an earlier launch, otherwise the new version
REM cannot start (port 8000 is already in use) and the app keeps showing the OLD pages.
REM Old versions ran it in a "WIPOTEC PV Server" window; newer ones run it hidden, so also
REM stop the Python process that listens on port 8000 (never any other program).
taskkill /f /t /fi "WINDOWTITLE eq WIPOTEC PV Server*" >nul 2>&1
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($p -and $p.ProcessName -like 'python*') { Stop-Process -Id $p.Id -Force } }" >nul 2>&1
timeout /t 1 /nobreak >nul

REM Start the server hidden: no window and nothing on the taskbar. It stops by itself once
REM every app window/page has been closed. Its output goes to server_console.log and
REM server_error.log (shown in "Show details" if it fails to start).
REM (The process ID goes through server.pid, not "for /f": the server would inherit the
REM pipe that "for /f" reads and this script would wait forever.)
set "XRPV_PY=!PYTHON_CMD!"
set "SRV_PID="
if exist server.pid del /q server.pid
powershell -NoProfile -Command "$py = $env:XRPV_PY.Trim([char]34); $env:PYTHONUTF8 = '1'; $s = Start-Process -FilePath $py -ArgumentList 'main.py' -WorkingDirectory $PWD.Path -WindowStyle Hidden -RedirectStandardOutput 'server_console.log' -RedirectStandardError 'server_error.log' -PassThru; Set-Content -Path 'server.pid' -Value $s.Id -Encoding Ascii" >nul 2>&1
if exist server.pid set /p SRV_PID=<server.pid

echo Waiting for the server to start...

set SERVER_READY=0
set SERVER_DIED=0
for /L %%i in (1,1,60) do (
    if "!SERVER_READY!!SERVER_DIED!"=="00" (
        powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
        if !errorlevel! equ 0 (
            set SERVER_READY=1
        ) else if defined SRV_PID (
            tasklist /fi "PID eq !SRV_PID!" /nh 2>nul | find "!SRV_PID!" >nul || set SERVER_DIED=1
        )
        if "!SERVER_READY!!SERVER_DIED!"=="00" (
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

REM Open the app in its own window (Microsoft Edge "app mode": no address bar or tabs,
REM own taskbar icon) with a separate profile kept outside the program folder. Falls back
REM to the normal browser when Edge is not installed, or when XRPV_USE_BROWSER=1.
REM The ?v= part makes it a new address, so a cached old home page is never shown.
set "APP_URL=http://127.0.0.1:8000/?v=!APP_VERSION!"
set "EDGE_EXE="
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "EDGE_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined EDGE_EXE if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "EDGE_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if "%XRPV_USE_BROWSER%"=="1" set "EDGE_EXE="
if not "!SERVER_READY!"=="1" (
    REM no working server: do not open an empty app window
) else if defined EDGE_EXE (
    set "APP_PROFILE=%LOCALAPPDATA%\WIPOTEC Certificates\AppWindow"
    REM --disable-extensions / --disable-sync: the app window needs no add-ons, and a new
    REM profile would otherwise sync the user's own Edge extensions and open their welcome pages.
    start "" "!EDGE_EXE!" --app="!APP_URL!" --user-data-dir="!APP_PROFILE!" --no-first-run --no-default-browser-check --disable-extensions --disable-sync --window-size=1300,900
) else (
    start "" "!APP_URL!"
)

echo ===================================================
if "!SERVER_READY!"=="1" (
    echo The system is ready. The server runs in the background and stops by
    echo itself when the app window is closed.
) else (
    echo [Error] The server did not start. Its error output:
    echo ---------------------------------------------------
    if exist server_error.log type server_error.log
    echo ---------------------------------------------------
)
echo ===================================================
if "!SERVER_READY!"=="1" (
    >"%XRPV_STATUS%" echo ready
) else if "!SERVER_DIED!"=="1" (
    >"%XRPV_STATUS%" echo error:The server stopped while starting - click Show details to see why.
) else (
    >"%XRPV_STATUS%" echo error:The server did not start in time - click Show details to see why.
)
if not "!SERVER_READY!"=="1" if not defined XRPV_SPLASH pause
if defined XRPV_SPLASH exit /b 0
echo This window will close automatically in a few seconds.
timeout /t 6
exit /b 0