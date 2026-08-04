# Gate scan wrapper (T01.1 step 1.Aa): no arguments, exact venv interpreter only.
if ($args.Count -ne 0) {
    [Console]::Error.WriteLine('ERROR' + [char]9 + 'GATE_SCAN_INVALID_ARGUMENT')
    exit 2
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$gatePython = Join-Path $repoRoot '.venv-gate\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $gatePython -PathType Leaf)) {
    [Console]::Error.WriteLine('ERROR' + [char]9 + 'GATE_SCAN_ENV_MISSING')
    exit 2
}

$env:PYTHONDONTWRITEBYTECODE = '1'
$gateScanScript = Join-Path $repoRoot 'scripts\gate_scan.py'
& $gatePython $gateScanScript
exit $LASTEXITCODE
