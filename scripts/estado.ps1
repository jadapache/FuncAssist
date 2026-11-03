param([string]$ComposeFile = (Join-Path $PSScriptRoot '..\compose.yaml'))
Set-Location (Split-Path $ComposeFile -Parent); docker compose -f $ComposeFile ps; docker compose -f $ComposeFile images
