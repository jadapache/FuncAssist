param([string]$ComposeFile = (Join-Path $PSScriptRoot '..\compose.yaml'), [switch]$Force)
$ErrorActionPreference = 'Stop'; $root = Split-Path $ComposeFile -Parent; Set-Location $root
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker no está instalado.' }
$envFile = Join-Path $root '.env'; $composeArgs = @('--env-file', $envFile, '-f', $ComposeFile)
$mutex = New-Object Threading.Mutex($false, 'Global\FuncAssistUpdate')
if (-not $mutex.WaitOne(0)) { Write-Host 'Ya hay una actualización en curso.'; exit 0 }
try {
  if (-not (Test-Path $envFile)) { throw "No existe $envFile." }
  docker compose @composeArgs pull
  if ($LASTEXITCODE -ne 0) { throw 'No fue posible descargar las imágenes.' }
  docker compose @composeArgs up -d --remove-orphans
  if ($LASTEXITCODE -ne 0) { throw 'No fue posible iniciar la nueva versión.' }
  docker compose @composeArgs ps
} finally { $mutex.ReleaseMutex(); $mutex.Dispose() }
