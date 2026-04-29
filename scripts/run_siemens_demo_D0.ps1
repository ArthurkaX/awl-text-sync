#Requires -Version 5.1
<#
.SYNOPSIS
  Run demo scenario D0_smoke: native validate on classic fixture + plccheck on minimal TIA-style fixture.

.DESCRIPTION
  Does not run STEP 7 (manual). Appends a timestamped summary to docs/demo_runs/ if that folder exists.

.PARAMETER RepoRoot
  awl-text-sync repository root (default: parent of scripts/)
#>
param(
    [string] $RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
Set-Location $RepoRoot

$classic = Join-Path $RepoRoot 'tests/fixtures/classic_demo_workspace'
$tiaish = Join-Path $RepoRoot 'tests/fixtures/plccheck_demo_minimal'
$py = Join-Path $RepoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $py)) {
    $py = 'python'
}

Write-Host '=== D0_smoke: awl-text-sync validate (classic fixture) ==='
& $py -m awl_text_sync.main --workspace $classic validate
$v = $LASTEXITCODE
if ($v -ne 0) { exit $v }

Write-Host '=== D0_smoke: plccheck check (minimal TIA-style fixture) ==='
& npx --yes plccheck check $tiaish
$p = $LASTEXITCODE

Write-Host '=== D0_smoke: combined validate --plccheck-root ==='
& $py -m awl_text_sync.main --workspace $classic validate --plccheck-root $tiaish
$c = $LASTEXITCODE

$runDir = Join-Path $RepoRoot 'docs/demo_runs'
if (Test-Path -LiteralPath $runDir) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $line = @"
$stamp validate_classic=$v plccheck_alone=$p combined=$c
"@
    Add-Content -LiteralPath (Join-Path $runDir 'D0_smoke.log') -Value $line
}

if ($c -ne 0) { exit $c }
exit 0
