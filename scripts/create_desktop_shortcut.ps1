# One-shot: create a Desktop .lnk that launches the parakeet-dictation daemon
# via ``scripts/start_dictation.ps1``. Idempotent — overwrites any existing
# shortcut with the same name.

$ErrorActionPreference = 'Stop'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Launcher = Join-Path $ProjectRoot 'scripts\start_dictation.ps1'
$PwshExe = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
if (-not $PwshExe) {
    $PwshExe = 'C:\Program Files\PowerShell\7\pwsh.exe'
}
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

$Desktop = [Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $Desktop 'Parakeet Dictation.lnk'

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PwshExe
$Shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $Launcher
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.IconLocation = ('{0},0' -f $VenvPython)
$Shortcut.Description = 'Start the local Parakeet dictation daemon (hold Ctrl+Shift+Space to dictate)'
$Shortcut.Save()

Write-Host ("Created: {0}" -f $ShortcutPath) -ForegroundColor Green
Write-Host ("Target : {0}" -f $PwshExe)
Write-Host ("Runs   : {0}" -f $Launcher)
