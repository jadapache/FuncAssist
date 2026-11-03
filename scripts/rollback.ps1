param([Parameter(Mandatory)][string]$Version, [string]$ComposeFile = (Join-Path $PSScriptRoot '..\compose.yaml'))
$ErrorActionPreference='Stop'; $root=Split-Path $ComposeFile -Parent; Set-Location $root
$env:APP_VERSION=$Version; docker compose -f $ComposeFile pull; docker compose -f $ComposeFile up -d --remove-orphans
