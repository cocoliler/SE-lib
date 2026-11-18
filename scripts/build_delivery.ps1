[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [string]$EvidenceRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $repoRoot "evidence\delivery"
}
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$commit = (& git -C $repoRoot rev-parse --short HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Cannot read Git commit"
}
$sourceZip = Join-Path $OutputDirectory "SE-lib-source-$commit.zip"
if (Test-Path -LiteralPath $sourceZip) {
    Remove-Item -LiteralPath $sourceZip -Force
}
& git -C $repoRoot archive --format=zip --output=$sourceZip HEAD
if ($LASTEXITCODE -ne 0) {
    throw "git archive failed"
}

if (-not $EvidenceRun) {
    $latest = Get-ChildItem -LiteralPath (Join-Path $repoRoot "evidence\runs") -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "summary.md") } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $latest) {
        throw "No verification run with summary.md found"
    }
    $EvidenceRun = $latest.FullName
}
if (-not (Test-Path -LiteralPath $EvidenceRun -PathType Container)) {
    throw "Evidence run not found: $EvidenceRun"
}

$staging = Join-Path $OutputDirectory ".evidence-$commit"
if (Test-Path -LiteralPath $staging) {
    $resolved = (Resolve-Path -LiteralPath $staging).Path
    if (-not $resolved.StartsWith($OutputDirectory + [IO.Path]::DirectorySeparatorChar)) {
        throw "Unsafe evidence staging path"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
New-Item -ItemType Directory -Force -Path (Join-Path $staging "logs") | Out-Null

$rootFiles = @(
    "summary.md",
    "summary.json",
    "quality-python.json",
    "quality-browser.json",
    "p0-state.json",
    "browser-spec.png",
    "browser-workflow.png",
    "browser-dark.png"
)
foreach ($name in $rootFiles) {
    $source = Join-Path $EvidenceRun $name
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $staging $name)
    }
}
$logs = Join-Path $EvidenceRun "logs"
if (Test-Path -LiteralPath $logs -PathType Container) {
    Get-ChildItem -LiteralPath $logs -File | Copy-Item -Destination (Join-Path $staging "logs")
}

$evidenceZip = Join-Path $OutputDirectory "SE-lib-evidence-$commit.zip"
if (Test-Path -LiteralPath $evidenceZip) {
    Remove-Item -LiteralPath $evidenceZip -Force
}
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $evidenceZip
$resolvedStaging = (Resolve-Path -LiteralPath $staging).Path
if (-not $resolvedStaging.StartsWith($OutputDirectory + [IO.Path]::DirectorySeparatorChar)) {
    throw "Unsafe evidence cleanup path"
}
Remove-Item -LiteralPath $resolvedStaging -Recurse -Force

$checksums = @{}
foreach ($path in @($sourceZip, $evidenceZip)) {
    $checksums[(Split-Path -Leaf $path)] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
}
$checksums | ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $OutputDirectory "checksums-$commit.json") -Encoding UTF8

Write-Host "Source package: $sourceZip"
Write-Host "Evidence package: $evidenceZip"
