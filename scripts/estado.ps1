param(
  [string]$ComposeFile = $(
    if (Test-Path (Join-Path $PSScriptRoot 'compose.yaml')) {
      Join-Path $PSScriptRoot 'compose.yaml'
    } else {
      Join-Path $PSScriptRoot '..\compose.yaml'
    }
  )
)
Set-Location (Split-Path $ComposeFile -Parent); docker compose -f $ComposeFile ps; docker compose -f $ComposeFile images
