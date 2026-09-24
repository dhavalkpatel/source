[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDirectory,

    [Parameter(Mandatory = $true)]
    [string]$FilePattern,

    [Parameter(Mandatory = $true)]
    [string]$DestinationDirectory,

    [Parameter(Mandatory = $true)]
    [bool]$IncludeSymbolPackages
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $SourceDirectory -PathType Container)) {
    throw "Package source directory not found: $SourceDirectory"
}

$sourceRoot = (Resolve-Path -LiteralPath $SourceDirectory).Path
$destinationRoot = (New-Item -ItemType Directory -Force -Path $DestinationDirectory).FullName

$packages = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Filter $FilePattern |
    Where-Object {
        $parent = [System.IO.Path]::GetDirectoryName($_.FullName)
        -not [string]::Equals($parent, $destinationRoot, [System.StringComparison]::OrdinalIgnoreCase)
    } |
    Where-Object {
        $IncludeSymbolPackages -or ($_.Name -notlike '*.symbols.nupkg' -and $_.Name -notlike '*.snupkg')
    }

if ($packages.Count -eq 0) {
    $stagedPackages = Get-ChildItem -LiteralPath $destinationRoot -File -Filter $FilePattern |
        Where-Object {
            $IncludeSymbolPackages -or ($_.Name -notlike '*.symbols.nupkg' -and $_.Name -notlike '*.snupkg')
        }

    if ($stagedPackages.Count -gt 0) {
        Write-Host "NuGet packages are already staged in $destinationRoot."
        exit 0
    }

    throw "No packages matching '$FilePattern' were found under $sourceRoot."
}

foreach ($package in $packages) {
    $destination = Join-Path $destinationRoot $package.Name
    Copy-Item -LiteralPath $package.FullName -Destination $destination -Force
    Write-Host "Staged $($package.FullName) as $destination"
}