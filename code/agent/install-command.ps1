$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$launcher = Join-Path $projectRoot 'fingraph.cmd'
$commandDir = Join-Path $env:LOCALAPPDATA 'FinGragh\bin'
$commandFile = Join-Path $commandDir 'FinGragh.cmd'
$marker = 'rem FinGragh Agent project launcher'

if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'Project launcher not found.' }
if (Test-Path -LiteralPath $commandFile) {
    $existing = [IO.File]::ReadAllText($commandFile)
    if (-not $existing.Contains($marker)) { throw "A different command already exists at $commandFile" }
}

New-Item -ItemType Directory -Path $commandDir -Force | Out-Null
$escapedLauncher = $launcher.Replace('%', '%%')
$content = "@echo off`r`n$marker`r`ncall `"$escapedLauncher`" %*`r`nexit /b %errorlevel%`r`n"
[IO.File]::WriteAllText($commandFile, $content, [Text.Encoding]::Default)

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$entries = @($userPath -split ';' | Where-Object { $_ })
$alreadyRegistered = @($entries | Where-Object {
    [string]::Equals($_.Trim('"').TrimEnd('\'), $commandDir.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)
}).Count -gt 0
if (-not $alreadyRegistered) {
    $updatedPath = if ([string]::IsNullOrEmpty($userPath)) { $commandDir } else { $userPath.TrimEnd(';') + ';' + $commandDir }
    [Environment]::SetEnvironmentVariable('Path', $updatedPath, 'User')
}
$env:Path = $commandDir + ';' + $env:Path
Write-Output "FinGragh command registered: $commandFile"
Write-Output 'Open a new terminal and run FinGragh. Pi remains installed inside this project.'
