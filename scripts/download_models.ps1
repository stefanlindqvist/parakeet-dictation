<#
.SYNOPSIS
    Download Parakeet-TDT 0.6B v3 ONNX model files from Hugging Face.

.DESCRIPTION
    Creates ./models/parakeet-tdt-0.6b-v3/ and downloads the four int8 model
    files (~900 MB total) from the onnx-community mirror. Skips files that
    already exist with non-zero size.

    After the first successful run, capture the SHA-256 of each file (printed
    below) and paste them into the $ExpectedSha256 table to enable verification
    on future runs. Verification is a no-op until that table is populated.

.NOTES
    Uses Invoke-WebRequest (built into Windows PowerShell 5.1+) so this script
    runs on a stock Windows 11 install with no external dependencies.
    Canonical design: ../parakeet-dictation-handover.md §4 + §8e.
#>

[CmdletBinding()]
param(
    [string]$ModelDir = (Join-Path $PSScriptRoot "..\models\parakeet-tdt-0.6b-v3")
)

$ErrorActionPreference = "Stop"

$BaseUrl = "https://huggingface.co/onnx-community/parakeet-tdt-0.6b-v3-ONNX/resolve/main"

# Files to download. Paths are relative to $BaseUrl.
$Files = @(
    @{ RemotePath = "onnx/encoder-model.int8.onnx";       LocalName = "encoder-model.int8.onnx" },
    @{ RemotePath = "onnx/encoder-model.int8.onnx.data";  LocalName = "encoder-model.int8.onnx.data" },
    @{ RemotePath = "onnx/decoder_joint-model.int8.onnx"; LocalName = "decoder_joint-model.int8.onnx" },
    @{ RemotePath = "vocab.txt";                          LocalName = "vocab.txt" }
)

# After first successful run, paste captured checksums here (keys = LocalName).
# Leave empty to skip verification.
$ExpectedSha256 = @{
    # "encoder-model.int8.onnx"       = "..."
    # "encoder-model.int8.onnx.data"  = "..."
    # "decoder_joint-model.int8.onnx" = "..."
    # "vocab.txt"                     = "..."
}

if (-not (Test-Path $ModelDir)) {
    Write-Host "Creating $ModelDir"
    New-Item -ItemType Directory -Path $ModelDir -Force | Out-Null
}

$TotalBytes = 0

foreach ($File in $Files) {
    $Target = Join-Path $ModelDir $File.LocalName
    $Url    = "$BaseUrl/$($File.RemotePath)?download=true"

    if ((Test-Path $Target) -and ((Get-Item $Target).Length -gt 0)) {
        Write-Host "[skip] $($File.LocalName) already exists"
    }
    else {
        Write-Host "[get ] $($File.LocalName) <- $Url"
        # Progress bar hammers performance on large downloads in PS 5.1; silence it.
        $OldProgress = $ProgressPreference
        $ProgressPreference = "SilentlyContinue"
        try {
            Invoke-WebRequest -Uri $Url -OutFile $Target -UseBasicParsing
        }
        finally {
            $ProgressPreference = $OldProgress
        }
    }

    $Size = (Get-Item $Target).Length
    $TotalBytes += $Size
    Write-Host ("       size: {0:N0} bytes" -f $Size)

    $Sha = (Get-FileHash -Path $Target -Algorithm SHA256).Hash.ToLower()
    Write-Host "       sha256: $Sha"

    if ($ExpectedSha256.ContainsKey($File.LocalName) -and $ExpectedSha256[$File.LocalName]) {
        $Expected = $ExpectedSha256[$File.LocalName].ToLower()
        if ($Sha -ne $Expected) {
            throw "SHA-256 mismatch for $($File.LocalName): got $Sha, expected $Expected"
        }
        Write-Host "       sha256 OK"
    }
}

Write-Host ""
Write-Host ("Total: {0:N2} MB in {1}" -f ($TotalBytes / 1MB), $ModelDir)
Write-Host "Done."
