#Requires -Version 5.1
<#
.SYNOPSIS
  Run plccheck against a Siemens PLC root that contains .plc.json (spike script).

.PARAMETER PlcRoot
  Directory containing .plc.json (TIA-style / Dynamic extension project layout).

.PARAMETER FetchOpenVsxVersionOnly
  If set, prints extension version from Open VSX API and exits (no plccheck).

.EXAMPLE
  .\scripts\siemens_plccheck_spike.ps1 -PlcRoot 'D:\exports\MyPlc'
#>
param(
    [Parameter(Mandatory = $false)]
    [string] $PlcRoot,
    [switch] $FetchOpenVsxVersionOnly
)

$ErrorActionPreference = 'Stop'
$openVsxLatest = 'https://open-vsx.org/api/DynamicEngineering/dynamic-siemens-language-support/latest'

if ($FetchOpenVsxVersionOnly) {
    $resp = Invoke-RestMethod -Uri $openVsxLatest -Method Get
    Write-Host "Open VSX Dynamic Siemens Language Support latest version: $($resp.version)"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($PlcRoot)) {
    Write-Error "Specify -PlcRoot (folder with .plc.json) or -FetchOpenVsxVersionOnly."
}

$root = (Resolve-Path -LiteralPath $PlcRoot).Path
$plcJson = Join-Path $root '.plc.json'
if (-not (Test-Path -LiteralPath $plcJson -PathType Leaf)) {
    Write-Error "No .plc.json at: $plcJson"
}

$plccheckCmd = Get-Command plccheck -ErrorAction SilentlyContinue
if ($plccheckCmd) {
    Write-Host "Running: plccheck check $root"
    & plccheck check $root
    exit $LASTEXITCODE
}

Write-Host "plccheck not on PATH; using: npx --yes plccheck check"
& npx --yes plccheck check $root
exit $LASTEXITCODE
