param([string]$Payload, [string]$PayloadFile)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
if ($PayloadFile) {
    $requestBody = [System.IO.File]::ReadAllText($PayloadFile, [System.Text.Encoding]::UTF8)
} elseif ($Payload) {
    $requestBody = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Payload))
} else {
    throw 'Provide PayloadFile or Payload.'
}
opencode api experimental.generate.text --data $requestBody
exit $LASTEXITCODE
