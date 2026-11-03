param(
  [string]$InstallDir = "$env:ProgramData\FuncAssist",
  [int]$IntervalMinutes = 15
)
$ErrorActionPreference = 'Stop'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Instale Docker Desktop antes de continuar.' }
docker info | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop debe estar iniciado antes de instalar FuncAssist.' }

New-Item -ItemType Directory -Force $InstallDir | Out-Null
Copy-Item (Join-Path $PSScriptRoot '..\compose.yaml') $InstallDir -Force
Copy-Item (Join-Path $PSScriptRoot 'actualizar.ps1') $InstallDir -Force
Copy-Item (Join-Path $PSScriptRoot 'estado.ps1') $InstallDir -Force

$envExample = Join-Path $InstallDir '.env.example'
if (-not (Test-Path $envExample)) { Copy-Item (Join-Path $PSScriptRoot '..\.env.example') $envExample }
$envFile = Join-Path $InstallDir '.env'
if (-not (Test-Path $envFile)) {
  Copy-Item $envExample $envFile
  Write-Warning "Configure los secretos en $envFile antes de iniciar la aplicación."
}

$taskName = 'FuncAssist - actualización automática'
$updater = Join-Path $InstallDir 'actualizar.ps1'
$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$updater`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$repeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($trigger, $repeat) -Principal $principal -Force | Out-Null

Write-Host "Tarea '$taskName' instalada. Las actualizaciones se comprobarán cada $IntervalMinutes minutos."
Write-Host "Configure $envFile y ejecute: docker compose --env-file $envFile -f $InstallDir\compose.yaml up -d"
