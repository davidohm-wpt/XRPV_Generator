' WIPOTEC AIO Software - opens the splash launcher without a console window.
' If PowerShell cannot be used, it falls back to Run_PV.bat (the classic console start).
Option Explicit
Dim sh, fso, dir, ps, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
ps = sh.ExpandEnvironmentStrings("%WINDIR%") & "\System32\WindowsPowerShell\v1.0\powershell.exe"
If fso.FileExists(ps) And fso.FileExists(dir & "\Launcher.ps1") Then
    On Error Resume Next
    rc = sh.Run("""" & ps & """ -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & dir & "\Launcher.ps1""", 0, False)
    If Err.Number <> 0 Then
        Err.Clear
        sh.Run """" & dir & "\Run_PV.bat""", 1, False
    End If
Else
    sh.Run """" & dir & "\Run_PV.bat""", 1, False
End If
