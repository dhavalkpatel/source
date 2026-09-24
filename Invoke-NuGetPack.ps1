[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$NuspecFile,

    [Parameter(Mandatory = $true)]
    [string]$Configuration,

    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,

    [Parameter(Mandatory = $true)]
    [string]$BasePath,

    [string]$BuildProperties
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $NuspecFile -PathType Leaf)) {
    throw "Nuspec file not found: $NuspecFile"
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$properties = @("Configuration=$Configuration")
if (-not [string]::IsNullOrWhiteSpace($BuildProperties)) {
    $properties += $BuildProperties.Trim(';')
}

$arguments = @(
    'pack',
    $NuspecFile,
    '-OutputDirectory', $OutputDirectory,
    '-BasePath', $BasePath,
    '-Properties', ($properties -join ';')
)

& nuget @arguments
if ($LASTEXITCODE -ne 0) {
    throw "nuget pack failed with exit code $LASTEXITCODE."
}