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
    Repo note: the handover cited `onnx-community/parakeet-tdt-0.6b-v3-ONNX`
    which does not exist publicly. The real ONNX mirror (same author as the
    onnx-asr library) is `istupakov/parakeet-tdt-0.6b-v3-onnx`; files live at
    the repo root, not under an `onnx/` subdirectory, and the int8 encoder
    has no `.data` sidecar (only the fp32 version does).
#>

[CmdletBinding()]
param(
    [string]$ModelDir = (Join-Path $PSScriptRoot "..\models\parakeet-tdt-0.6b-v3")
)

$ErrorActionPreference = "Stop"

$BaseUrl = "https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/resolve/main"

# Files to download. Paths are relative to $BaseUrl. Total ~670 MB for int8.
# nemo128.onnx is the mel-filterbank preprocessor; config.json carries model
# metadata. Both are required alongside the encoder/decoder + vocab.
$Files = @(
    @{ RemotePath = "encoder-model.int8.onnx";       LocalName = "encoder-model.int8.onnx" },
    @{ RemotePath = "decoder_joint-model.int8.onnx"; LocalName = "decoder_joint-model.int8.onnx" },
    @{ RemotePath = "nemo128.onnx";                  LocalName = "nemo128.onnx" },
    @{ RemotePath = "vocab.txt";                     LocalName = "vocab.txt" },
    @{ RemotePath = "config.json";                   LocalName = "config.json" }
)

# SHA-256 expected for each file. Captured from the first successful download
# on 2026-04-20; LFS-tracked entries match the Hugging Face LFS pointer oid.
# Set any value to $null or "" to skip verification for that one file.
$ExpectedSha256 = @{
    "encoder-model.int8.onnx"       = "6139d2fa7e1b086097b277c7149725edbab89cc7c7ae64b23c741be4055aff09"
    "decoder_joint-model.int8.onnx" = "eea7483ee3d1a30375daedc8ed83e3960c91b098812127a0d99d1c8977667a70"
    "nemo128.onnx"                  = "a9fde1486ebfcc08f328d75ad4610c67835fea58c73ba57e3209a6f6cf019e9f"
    "vocab.txt"                     = "d58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d"
    "config.json"                   = "666903c76b9798caf2c210afd4f6cd60b08a8dbf9800ec8d7a3bc0d2148ac466"
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
