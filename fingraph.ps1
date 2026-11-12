param(
    [switch]$Setup,
    [switch]$Check,
    [string]$Python,
    [string]$Prompt
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$agentRoot = Join-Path $projectRoot 'code\agent'
$localPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$localState = Join-Path $projectRoot '.fingraph'
$webProcess = $null

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "命令未完成：$Executable（退出码 $LASTEXITCODE）" }
}

Push-Location $projectRoot
try {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw '需要 Node.js 22.19 或更新版本。' }
    if ($Setup) {
        if (-not (Test-Path -LiteralPath $localPython)) {
            if (-not $Python) { $Python = (Get-Command python -ErrorAction Stop).Source }
            Invoke-Checked $Python @('-m', 'venv', (Join-Path $projectRoot '.venv'))
        }
        Invoke-Checked $localPython @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', 'code/requirements-lock.txt', '-r', 'code/requirements-agent.txt')
        $npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source
        Invoke-Checked $npmCommand @('ci', '--ignore-scripts', '--no-audit', '--no-fund', '--prefix', $agentRoot)
    }
    if (-not (Test-Path -LiteralPath $localPython)) { throw '请先运行 .\fingraph.ps1 -Setup。' }
    $env:FINGRAPH_PYTHON = $localPython
    if ($Check) {
        Invoke-Checked 'node' @((Join-Path $agentRoot 'bin\fingraph.mjs'), '--check')
        exit 0
    }
    New-Item -ItemType Directory -Path $localState -Force | Out-Null
    $portText = & $localPython -c "from dotenv import dotenv_values; v=dotenv_values('.env'); print(v.get('FINGRAPH_PORT') or '8017')"
    if ($LASTEXITCODE -ne 0) { throw '无法读取本地配置。' }
    $port = [int]$portText
    $webUrl = "http://127.0.0.1:$port"
    $healthy = $false
    try {
        $health = Invoke-RestMethod "$webUrl/api/health" -TimeoutSec 2
        $healthy = $health.status -eq 'ok' -and $health.engine -like '*NetworkX*'
    } catch { }
    if (-not $healthy) {
        $env:FINGRAPH_PORT = [string]$port
        $appPath = Join-Path $projectRoot 'code\app.py'
        $webProcess = Start-Process -FilePath $localPython -ArgumentList ('"{0}"' -f $appPath) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localState 'web.stdout.log') -RedirectStandardError (Join-Path $localState 'web.stderr.log')
        for ($attempt = 0; $attempt -lt 40; $attempt++) {
            if ($webProcess.HasExited) { throw 'Web 服务启动失败，详见 .fingraph\web.stderr.log。' }
            try {
                $health = Invoke-RestMethod "$webUrl/api/health" -TimeoutSec 1
                if ($health.status -eq 'ok') { $healthy = $true; break }
            } catch { }
            Start-Sleep -Milliseconds 250
        }
        if (-not $healthy) { throw 'Web 服务未能及时启动，详见 .fingraph\web.stderr.log。' }
    }
    Write-Host "FinGragh Agent · $webUrl · 输入 /web 打开图谱"
    $agentArguments = @((Join-Path $agentRoot 'bin\fingraph.mjs'))
    if ($Prompt) { $agentArguments += @('--print', '--no-session', $Prompt) }
    Invoke-Checked 'node' $agentArguments
} finally {
    if ($webProcess -and -not $webProcess.HasExited) { Stop-Process -Id $webProcess.Id -ErrorAction SilentlyContinue }
    Pop-Location
}
