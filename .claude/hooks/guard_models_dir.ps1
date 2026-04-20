<#
.SYNOPSIS
    PreToolUse hook: block Claude Code from editing files under ./models/.

.DESCRIPTION
    Reads the Claude Code hook payload from stdin (JSON), inspects
    tool_input.file_path, and exits 2 (blocking) with a stderr message if the
    path points inside the models/ directory. The models/ directory holds
    downloaded ONNX weights (~900 MB) that should never be hand-edited.

    Exit 0 on any other path, on parse errors, or if no file_path is present —
    this hook should never accidentally block legitimate work.
#>

$ErrorActionPreference = "Stop"

try {
    $Raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($Raw)) { exit 0 }

    $Payload = $Raw | ConvertFrom-Json

    $FilePath = $null
    if ($Payload.PSObject.Properties.Name -contains "tool_input") {
        if ($Payload.tool_input.PSObject.Properties.Name -contains "file_path") {
            $FilePath = [string]$Payload.tool_input.file_path
        }
    }
    if (-not $FilePath) { exit 0 }

    # Normalise separators and lowercase for match.
    $Normalised = $FilePath -replace "\\", "/"
    $Lower = $Normalised.ToLower()

    if ($Lower -match "(^|/)models/parakeet-tdt-0\.6b-v3(/|$)") {
        Write-Error "Blocked: ./models/parakeet-tdt-0.6b-v3/ holds downloaded ONNX model weights and must not be hand-edited. Re-run scripts/download_models.ps1 instead, or delete and re-download."
        exit 2
    }

    exit 0
}
catch {
    # Never block on hook failure — log and pass through.
    [Console]::Error.WriteLine("guard_models_dir.ps1: non-fatal error: $_")
    exit 0
}
