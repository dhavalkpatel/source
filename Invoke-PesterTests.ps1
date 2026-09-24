[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Path,

    [string]$Tags,

    [Parameter(Mandatory = $true)]
    [string]$ResultsFile,

    [Parameter(Mandatory = $true)]
    [version]$MinimumVersion
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$module = Get-Module -ListAvailable -Name Pester |
    Where-Object { $_.Version -ge $MinimumVersion } |
    Sort-Object Version -Descending |
    Select-Object -First 1

if ($null -eq $module) {
    throw "Pester $MinimumVersion or later is required. Install it before running this task."
}

Import-Module -Name $module.Path -Force
$pesterVersion = (Get-Module -Name Pester).Version

$resultsDirectory = Split-Path -Parent $ResultsFile
if (-not [string]::IsNullOrWhiteSpace($resultsDirectory)) {
    New-Item -ItemType Directory -Force -Path $resultsDirectory | Out-Null
}

$tagList = @($Tags -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })

if ($pesterVersion.Major -eq 4) {
    $parameters = @{
        Script = $Path
        PassThru = $true
        OutputFile = $ResultsFile
        OutputFormat = 'NUnitXml'
    }

    if ($tagList.Count -gt 0) {
        $parameters.Tag = $tagList
    }

    $result = Invoke-Pester @parameters
}
elseif ($pesterVersion.Major -eq 5) {
    $configuration = New-PesterConfiguration
    $configuration.Run.Path = $Path
    $configuration.Run.PassThru = $true
    $configuration.TestResult.Enabled = $true
    $configuration.TestResult.OutputPath = $ResultsFile
    $configuration.TestResult.OutputFormat = 'NUnitXml'

    if ($tagList.Count -gt 0) {
        $configuration.Filter.Tag = $tagList
    }

    $result = Invoke-Pester -Configuration $configuration
}
else {
    throw "Pester version $pesterVersion is unsupported. Use Pester 4.x or 5.x."
}

if ($null -eq $result) {
    throw 'Pester did not return a test result.'
}

if ($result.FailedCount -ne 0) {
    throw "Pester returned $($result.FailedCount) failed test(s)."
}