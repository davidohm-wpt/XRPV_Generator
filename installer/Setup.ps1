# WIPOTEC Service Certificates - installer for a new PC.
# Shipped next to XRPV_files.zip (made by Make_NewPC_Pack.bat). Unpacks the program with a
# 0-100% progress bar, because Windows' own "Extract All" is very slow for the ~20,000 small
# files of the portable Python, GTK and Git folders and looks frozen.
# Test/silent use: Setup.ps1 -Target "C:\some\folder" -Auto [-Snapshot "C:\shots"]
param(
    [string]$Target = '',
    [switch]$Auto,
    [string]$Snapshot = ''
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.Windows.Forms.Application]::EnableVisualStyles()

$dir     = Split-Path -Parent $MyInvocation.MyCommand.Path
$payload = Join-Path $dir 'XRPV_files.zip'
$prefix  = 'XRPV Generator/'   # top folder inside XRPV_files.zip

if (-not (Test-Path $payload)) {
    [void][System.Windows.Forms.MessageBox]::Show(
        "XRPV_files.zip was not found next to the installer.`r`n`r`nRight-click the zip you received, choose ""Extract All..."", then open the extracted folder and double-click ""Install WIPOTEC Certificates"" again.",
        'WIPOTEC Certificates - Setup', 'OK', 'Warning')
    exit 1
}

# Default folder: Documents\XRPV Generator - unless Documents is synced by OneDrive
# (20,000 program files there would keep OneDrive busy), then the user folder.
if (-not $Target) {
    $docs = [Environment]::GetFolderPath('MyDocuments')
    $parent = if ($docs -and $docs -notmatch '\\OneDrive') { $docs } else { $env:USERPROFILE }
    $Target = Join-Path $parent 'XRPV Generator'
}

$teal     = [System.Drawing.Color]::FromArgb(0, 153, 153)
$tealDark = [System.Drawing.Color]::FromArgb(0, 110, 110)
$ink      = [System.Drawing.Color]::FromArgb(26, 26, 26)
$muted    = [System.Drawing.Color]::FromArgb(140, 140, 140)
$track    = [System.Drawing.Color]::FromArgb(230, 238, 238)
$okGreen  = [System.Drawing.Color]::FromArgb(30, 126, 52)
$errRed   = [System.Drawing.Color]::FromArgb(176, 42, 55)
$font     = New-Object System.Drawing.Font('Segoe UI', 10)
$fontBold = New-Object System.Drawing.Font('Segoe UI Semibold', 10)
$fontBig  = New-Object System.Drawing.Font('Segoe UI Semibold', 22)

# ---------- read the archive ----------
try {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($payload)
} catch {
    [void][System.Windows.Forms.MessageBox]::Show("XRPV_files.zip could not be opened. It may be incomplete - copy the pack again.`r`n`r`n$($_.Exception.Message)",
        'WIPOTEC Certificates - Setup', 'OK', 'Error')
    exit 1
}
$entries = @($zip.Entries | Where-Object { $_.FullName.StartsWith($prefix) -and $_.FullName.Length -gt $prefix.Length })
$files = @($entries | Where-Object { -not $_.FullName.EndsWith('/') })
$totalBytes = [long]0; foreach ($e in $files) { $totalBytes += $e.Length }
if ($totalBytes -le 0) { $totalBytes = 1 }

function Read-Entry([string]$name) {
    $e = $zip.GetEntry($prefix + $name)
    if (-not $e) { return $null }
    $r = New-Object System.IO.StreamReader($e.Open())
    try { return $r.ReadToEnd() } finally { $r.Dispose() }
}
$version = ''
try { $v = Read-Entry 'VERSION.txt'; if ($v) { $version = $v.Trim() } } catch { }

# ---------- window ----------
$form = New-Object System.Windows.Forms.Form
$form.Text = 'WIPOTEC Certificates - Setup'
$form.FormBorderStyle = 'FixedSingle'
$form.MaximizeBox = $false
$form.StartPosition = 'CenterScreen'
$form.ClientSize = New-Object System.Drawing.Size(500, 330)
$form.BackColor = [System.Drawing.Color]::White
try {
    $ico = $zip.GetEntry($prefix + 'wipotec2.ico')
    if ($ico) { $ms = New-Object System.IO.MemoryStream; $s = $ico.Open(); $s.CopyTo($ms); $s.Dispose(); $ms.Position = 0; $form.Icon = New-Object System.Drawing.Icon($ms) }
} catch { }

$bar = New-Object System.Windows.Forms.Panel
$bar.SetBounds(0, 0, 500, 5); $bar.BackColor = $teal
$form.Controls.Add($bar)

$logo = New-Object System.Windows.Forms.PictureBox
$logo.SetBounds(28, 24, 170, 38); $logo.SizeMode = 'Zoom'
try {
    $m = [regex]::Match((Read-Entry 'assets.py'), 'LOGO_HEADER_URI\s*=\s*"data:image/png;base64,([A-Za-z0-9+/=]+)"')
    $bytes = [Convert]::FromBase64String($m.Groups[1].Value)
    $logo.Image = [System.Drawing.Image]::FromStream((New-Object System.IO.MemoryStream(, $bytes)))
} catch {
    $logo.Visible = $false
    $t = New-Object System.Windows.Forms.Label
    $t.Text = 'WIPOTEC'; $t.Font = New-Object System.Drawing.Font('Segoe UI Semibold', 18); $t.ForeColor = $ink
    $t.SetBounds(26, 22, 200, 40); $form.Controls.Add($t)
}
$form.Controls.Add($logo)

$ver = New-Object System.Windows.Forms.Label
$ver.Text = $(if ($version) { "v$version" } else { '' }); $ver.Font = $font; $ver.ForeColor = $tealDark; $ver.TextAlign = 'MiddleRight'
$ver.SetBounds(350, 28, 122, 24)
$form.Controls.Add($ver)

$title = New-Object System.Windows.Forms.Label
$title.Text = 'Install Service Certificates'; $title.Font = New-Object System.Drawing.Font('Segoe UI', 12); $title.ForeColor = $ink
$title.SetBounds(28, 70, 440, 26)
$form.Controls.Add($title)

$lblFolder = New-Object System.Windows.Forms.Label
$lblFolder.Text = 'Install to:'; $lblFolder.Font = $font; $lblFolder.ForeColor = $muted
$lblFolder.SetBounds(28, 108, 440, 20)
$form.Controls.Add($lblFolder)

$txtFolder = New-Object System.Windows.Forms.TextBox
$txtFolder.Text = $Target; $txtFolder.Font = $font; $txtFolder.ReadOnly = $true; $txtFolder.BackColor = [System.Drawing.Color]::White
$txtFolder.SetBounds(28, 130, 340, 26)
$form.Controls.Add($txtFolder)

$btnBrowse = New-Object System.Windows.Forms.Button
$btnBrowse.Text = 'Change...'; $btnBrowse.Font = $font; $btnBrowse.SetBounds(376, 129, 96, 28)
$form.Controls.Add($btnBrowse)

$pct = New-Object System.Windows.Forms.Label
$pct.Font = $fontBig; $pct.ForeColor = $teal; $pct.Text = ''
$pct.SetBounds(26, 166, 200, 44)
$form.Controls.Add($pct)

$status = New-Object System.Windows.Forms.Label
$status.Font = $font; $status.ForeColor = $muted
$status.Text = ('{0:N0} files, {1:N0} MB. Needs about {2:N0} MB of free disk space.' -f $files.Count, ($totalBytes / 1MB), ($totalBytes / 1MB + 50))
$status.SetBounds(28, 214, 444, 22)
$form.Controls.Add($status)

$trackPanel = New-Object System.Windows.Forms.Panel
$trackPanel.SetBounds(30, 242, 440, 8); $trackPanel.BackColor = $track
$fill = New-Object System.Windows.Forms.Panel
$fill.SetBounds(0, 0, 0, 8); $fill.BackColor = $teal
$trackPanel.Controls.Add($fill)
$form.Controls.Add($trackPanel)

$detail = New-Object System.Windows.Forms.Label
$detail.Font = New-Object System.Drawing.Font('Segoe UI', 9); $detail.ForeColor = $muted
$detail.SetBounds(28, 254, 444, 20)
$form.Controls.Add($detail)

$btnMain = New-Object System.Windows.Forms.Button
$btnMain.Text = 'Install'; $btnMain.Font = $fontBold; $btnMain.SetBounds(270, 284, 100, 32)
$btnMain.BackColor = $teal; $btnMain.ForeColor = [System.Drawing.Color]::White; $btnMain.FlatStyle = 'Flat'; $btnMain.FlatAppearance.BorderSize = 0
$btnClose = New-Object System.Windows.Forms.Button
$btnClose.Text = 'Cancel'; $btnClose.Font = $font; $btnClose.SetBounds(376, 284, 96, 32)
$form.Controls.Add($btnMain); $form.Controls.Add($btnClose)
$form.AcceptButton = $btnMain

# ---------- state ----------
$script:state = 'ready'   # ready | installing | done | failed
$script:idx = 0
$script:doneBytes = [long]0
$script:started = $null
$script:dest = $null

function Save-Snapshot([string]$name) {
    if (-not $Snapshot) { return }
    try {
        $bmp = New-Object System.Drawing.Bitmap($form.Width, $form.Height)
        $form.DrawToBitmap($bmp, (New-Object System.Drawing.Rectangle(0, 0, $form.Width, $form.Height)))
        $bmp.Save((Join-Path $Snapshot "$name.png"), [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
    } catch { }
}

function Set-Progress {
    $p = [Math]::Min(100, [int][Math]::Floor(100.0 * $script:doneBytes / $totalBytes))
    $pct.Text = "$p%"
    $fill.Width = [int](440 * $p / 100)
    $status.Text = ('Copying files... {0:N0} of {1:N0}' -f $script:idx, $entries.Count)
    $secs = ((Get-Date) - $script:started).TotalSeconds
    if ($secs -gt 3 -and $script:doneBytes -gt 0) {
        $left = $secs * ($totalBytes - $script:doneBytes) / $script:doneBytes
        $detail.Text = if ($left -ge 90) { 'About {0} minutes left' -f [int][Math]::Ceiling($left / 60) } elseif ($left -ge 5) { 'About {0} seconds left' -f [int]([Math]::Ceiling($left / 5) * 5) } else { 'Almost done...' }
    } else { $detail.Text = 'Please wait - this takes a few minutes.' }
}

function Show-Failed([string]$msg) {
    $script:state = 'failed'
    $timer.Stop()
    $fill.BackColor = $errRed; $pct.ForeColor = $errRed
    $status.ForeColor = $errRed; $status.Text = 'Installation failed.'
    $detail.ForeColor = $errRed; $detail.Text = $msg
    $btnMain.Visible = $false; $btnClose.Text = 'Close'
    Save-Snapshot 'failed'
    if ($Auto) { [Console]::WriteLine("FAILED: $msg"); $form.Close() }
}

function Start-Install {
    $script:dest = $txtFolder.Text.TrimEnd('\')
    try {
        $drive = New-Object System.IO.DriveInfo([System.IO.Path]::GetPathRoot($script:dest))
        if ($drive.AvailableFreeSpace -lt ($totalBytes + 50MB)) {
            [void][System.Windows.Forms.MessageBox]::Show(('Not enough free space on {0} - about {1:N0} MB is needed.' -f $drive.Name, ($totalBytes / 1MB + 50)), 'WIPOTEC Certificates - Setup', 'OK', 'Warning')
            return
        }
    } catch { }
    if (-not $Auto -and (Test-Path (Join-Path $script:dest 'Run_PV.bat'))) {
        $a = [System.Windows.Forms.MessageBox]::Show("The program is already installed in:`r`n$($script:dest)`r`n`r`nInstall again over it? Saved sign-in passwords on this PC are kept.",
            'WIPOTEC Certificates - Setup', 'YesNo', 'Question')
        if ($a -ne 'Yes') { return }
    }
    try { [void](New-Item -ItemType Directory -Force -Path $script:dest) } catch { Show-Failed "Cannot create the folder: $($_.Exception.Message)"; return }
    $script:state = 'installing'
    $script:started = Get-Date
    $btnBrowse.Enabled = $false; $btnMain.Enabled = $false; $btnMain.Visible = $false
    $title.Text = 'Installing Service Certificates'
    $txtFolder.SelectionLength = 0; $btnClose.Focus() | Out-Null
    # Windows' own tar.exe unpacks about 7x faster than unpacking file by file from here;
    # its list of written files ("x path" lines) drives the progress bar.
    $tarExe = Join-Path $env:WINDIR 'System32\tar.exe'
    if (Test-Path $tarExe) {
        try {
            $script:tarLog = Join-Path $env:TEMP ('xrpv_setup_{0}.txt' -f [guid]::NewGuid().ToString('N'))
            $script:tarPos = [long]0; $script:tarRest = ''
            $script:tar = Start-Process -FilePath $tarExe -WindowStyle Hidden -PassThru -RedirectStandardError $script:tarLog `
                -ArgumentList ('-xvf "{0}" --strip-components=1 -C "{1}"' -f $payload, $script:dest)
            $null = $script:tar.Handle   # keep the handle, otherwise ExitCode stays empty
            $script:mode = 'tar'
        } catch { $script:mode = 'net' }
    } else { $script:mode = 'net' }
    $timer.Interval = $(if ($script:mode -eq 'tar') { 200 } else { 15 })
    Set-Progress
    $timer.Start()
}

# size of every file by its path inside the program folder (for the tar progress)
$sizeOf = @{}
foreach ($e in $files) { $sizeOf[$e.FullName.Substring($prefix.Length)] = $e.Length }

function Read-TarProgress {
    try {
        $fs = New-Object System.IO.FileStream($script:tarLog, 'Open', 'Read', 'ReadWrite')
        try {
            if ($fs.Length -le $script:tarPos) { return }
            [void]$fs.Seek($script:tarPos, 'Begin')
            $buf = New-Object byte[] ($fs.Length - $script:tarPos)
            $n = $fs.Read($buf, 0, $buf.Length)
            $script:tarPos += $n
        } finally { $fs.Dispose() }
        $text = $script:tarRest + [Text.Encoding]::UTF8.GetString($buf, 0, $n)
        $lines = $text -split "`r?`n"
        $script:tarRest = $lines[-1]
        for ($i = 0; $i -lt $lines.Count - 1; $i++) {
            $l = $lines[$i]
            if ($l.StartsWith('x ')) {
                $script:idx++
                $sz = $sizeOf[$l.Substring(2)]
                if ($sz) { $script:doneBytes += $sz }
            }
        }
    } catch { }
}

function Get-TarError {
    try { return ((Get-Content $script:tarLog -ErrorAction Stop | Where-Object { $_ -and -not $_.StartsWith('x ') } | Select-Object -Last 2) -join ' ') } catch { return '' }
}

function Complete-Install {
    $timer.Stop()
    $script:state = 'done'
    $zip.Dispose()
    $pct.Text = '100%'; $pct.ForeColor = $okGreen; $fill.Width = 440; $fill.BackColor = $okGreen
    $title.Text = 'Installation complete'
    $status.ForeColor = $okGreen; $status.Text = ('Installed {0:N0} files.' -f $files.Count)
    $detail.Text = 'Click "Open now" - the first start needs internet and takes a minute.'
    $btnMain.Text = 'Open now'; $btnMain.Visible = $true; $btnMain.Enabled = $true
    $btnClose.Text = 'Close'
    $txtFolder.SelectionLength = 0; $btnMain.Focus() | Out-Null
    Save-Snapshot 'done'
    if ($Auto) { [Console]::WriteLine("OK: $($files.Count) files in $($script:dest)"); $form.Close() }
}

function Open-Program {
    $vbs = Join-Path $script:dest 'Launch.vbs'
    if (Test-Path $vbs) { Start-Process -FilePath "$env:WINDIR\System32\wscript.exe" -ArgumentList ('"' + $vbs + '"') -WorkingDirectory $script:dest }
    else { Start-Process -FilePath (Join-Path $script:dest 'Run_PV.bat') -WorkingDirectory $script:dest }
    $form.Close()
}

# Unpack in small time slices so the window stays responsive.
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 15
$script:snapTaken = $false
$timer.Add_Tick({
    if ($script:state -ne 'installing') { return }
    if ($script:mode -eq 'tar') {
        Read-TarProgress
        if ($script:tar.HasExited) {
            Read-TarProgress
            $code = $script:tar.ExitCode
            if ($code -eq 0) { $script:idx = $entries.Count; $script:doneBytes = $totalBytes; try { Remove-Item $script:tarLog -Force } catch { }; Complete-Install }
            else { Show-Failed ("Unpacking stopped (code $code). " + (Get-TarError)) }
            return
        }
        Set-Progress
        if (-not $script:snapTaken -and $script:doneBytes -gt $totalBytes * 0.4) { $script:snapTaken = $true; Save-Snapshot 'progress' }
        return
    }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        while ($script:idx -lt $entries.Count -and $sw.ElapsedMilliseconds -lt 120) {
            $e = $entries[$script:idx]
            $rel = $e.FullName.Substring($prefix.Length).Replace('/', '\')
            $path = Join-Path $script:dest $rel
            if ($e.FullName.EndsWith('/')) {
                [void][System.IO.Directory]::CreateDirectory($path)
            } else {
                [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($path))
                [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, $path, $true)
                $script:doneBytes += $e.Length
            }
            $script:idx++
        }
    } catch {
        Show-Failed ("Could not write {0}: {1}" -f $rel, $_.Exception.Message)
        return
    }
    if ($script:idx -ge $entries.Count) { Complete-Install; return }
    Set-Progress
    if (-not $script:snapTaken -and $script:doneBytes -gt $totalBytes * 0.4) { $script:snapTaken = $true; Save-Snapshot 'progress' }
})

$btnBrowse.Add_Click({
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = 'Choose where to install. A folder "XRPV Generator" is created inside it.'
    $dlg.SelectedPath = Split-Path -Parent $txtFolder.Text
    if ($dlg.ShowDialog($form) -eq 'OK') {
        $sel = $dlg.SelectedPath.TrimEnd('\')
        $txtFolder.Text = if ((Split-Path -Leaf $sel) -eq 'XRPV Generator') { $sel } else { Join-Path $sel 'XRPV Generator' }
    }
})
$btnMain.Add_Click({
    if ($script:state -eq 'ready') { Start-Install }
    elseif ($script:state -eq 'done') { Open-Program }
})
$btnClose.Add_Click({ $form.Close() })
$form.Add_FormClosing({ param($s, $e)
    if ($script:state -eq 'installing' -and -not $Auto) {
        $a = [System.Windows.Forms.MessageBox]::Show("Stop the installation?`r`nThe program will not work until you run the installer again.", 'WIPOTEC Certificates - Setup', 'YesNo', 'Warning')
        if ($a -ne 'Yes') { $e.Cancel = $true; return }
        $timer.Stop()
        if ($script:tar -and -not $script:tar.HasExited) { try { $script:tar.Kill() } catch { } }
    }
})
$form.Add_Shown({
    $form.Activate()
    Save-Snapshot 'start'
    if ($Auto) { Start-Install }
})
[void]$form.ShowDialog()
$timer.Stop()
try { $zip.Dispose() } catch { }
