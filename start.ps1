param([string]$Python = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $Python) {
    $knownPython = 'D:\anaconda3\envs\agent\python.exe'
    if (Test-Path -LiteralPath $knownPython) { $Python = $knownPython }
    else { $Python = (Get-Command python -ErrorAction Stop).Source }
}
Write-Host 'FinGraph: http://127.0.0.1:8000  (Ctrl+C to stop)'
& $Python (Join-Path $PSScriptRoot 'code\app.py')
exit $LASTEXITCODE
