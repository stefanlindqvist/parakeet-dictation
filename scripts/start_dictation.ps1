# Launcher for the parakeet-dictation daemon, targeted by the Desktop shortcut
# (``scripts/create_desktop_shortcut.ps1`` generates the .lnk that calls this).
#
# The script runs the venv's Python directly — no activation — so execution
# policy is not a concern and PYTHONPATH is not polluted. On error it pauses
# so the user can read the traceback instead of the window closing instantly.

$ErrorActionPreference = 'Continue'

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "venv Python not found at $VenvPython" -ForegroundColor Red
    Write-Host "Run 'python -m venv .venv' and 'pip install -e .[dev]' first." -ForegroundColor Red
    Write-Host ""
    Write-Host "Press any key to close..." -ForegroundColor Yellow
    $null = [Console]::ReadKey($true)
    exit 1
}

Set-Location -LiteralPath $ProjectRoot

Write-Host "parakeet-dictation" -ForegroundColor Cyan
Write-Host ("Project : {0}" -f $ProjectRoot)
Write-Host ("Python  : {0}" -f $VenvPython)
Write-Host "Hotkey  : Ctrl+Shift+Space (hold to dictate, release to paste)"
Write-Host "Stop    : Ctrl+C in this window"
Write-Host ""

& $VenvPython -m parakeet_dictation
$ExitCode = $LASTEXITCODE

if ($ExitCode -ne 0) {
    Write-Host ""
    Write-Host ("Daemon exited with code {0}." -f $ExitCode) -ForegroundColor Yellow
    Write-Host "Press any key to close..." -ForegroundColor Yellow
    $null = [Console]::ReadKey($true)
}

exit $ExitCode
