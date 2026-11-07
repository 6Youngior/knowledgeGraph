# 在 docs/presentation/ 下运行；输出 FinGraph-期中汇报.pdf
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$python = 'D:/anaconda3/envs/agent/python.exe'
if (Test-Path $python) {
    & $python .\derive_research.py
    if ($LASTEXITCODE -ne 0) { throw 'derive_research.py failed' }
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python .\derive_research.py
    if ($LASTEXITCODE -ne 0) { throw 'derive_research.py failed' }
}

New-Item -ItemType Directory -Force build | Out-Null
latexmk -xelatex -interaction=nonstopmode -halt-on-error -outdir=build main.tex
if ($LASTEXITCODE -ne 0) { throw 'latexmk failed' }

Copy-Item build\main.pdf 'FinGraph-期中汇报.pdf' -Force
Write-Host "OK: $PWD\FinGraph-期中汇报.pdf"
