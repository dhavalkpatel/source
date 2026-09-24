[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDirectory,

    [Parameter(Mandatory = $true)]
    [string]$DestinationDirectory,

    [Parameter(Mandatory = $true)]
    [bool]$CleanDestination
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $SourceDirectory -PathType Container)) {
    throw "Artifact source directory not found: $SourceDirectory"
}

$sourceRoot = (Resolve-Path -LiteralPath $SourceDirectory).Path.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $DestinationDirectory | Out-Null
$destinationRoot = (Resolve-Path -LiteralPath $DestinationDirectory).Path.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)

if ([string]::Equals($sourceRoot, $destinationRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Artifact source and destination directories must be different.'
}

$destinationWithinSource = "$sourceRoot$([System.IO.Path]::DirectorySeparatorChar)"
if ($destinationRoot.StartsWith($destinationWithinSource, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Artifact destination directory must not be inside the source directory.'
}

if ($CleanDestination) {
    Get-ChildItem -LiteralPath $destinationRoot -Force | Remove-Item -Recurse -Force
}

Get-ChildItem -LiteralPath $sourceRoot -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $destinationRoot -Recurse -Force
}

Write-Host "Staged artifact contents from $sourceRoot to $destinationRoot"