param(
  [string]$InstallDir = "$env:ProgramData\FuncAssist",
  [int]$IntervalMinutes = 15
)
$ErrorActionPreference = 'Stop'

function Resolve-SourceFile([string]$FileName) {
  $candidates = @(
    (Join-Path $PSScriptRoot $FileName),
    (Join-Path $PSScriptRoot "..\$FileName"),
    (Join-Path $PSScriptRoot "scripts\$FileName")
  )
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return (Resolve-Path $candidate).Path
    }
  }
  throw "No se encontró el archivo fuente: $FileName"
}

function Copy-DeploymentFile([string]$SourcePath, [string]$TargetDir) {
  $targetPath = Join-Path $TargetDir (Split-Path $SourcePath -Leaf)
  $resolvedTarget = if (Test-Path $targetPath) { (Resolve-Path $targetPath).Path } else { $null }
  if ($SourcePath -ne $resolvedTarget) {
    Copy-Item $SourcePath $TargetDir -Force
  }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  throw 'Instale Docker Desktop antes de continuar.'
}
docker info | Out-Null
if ($LASTEXITCODE -ne 0) {
  throw 'Docker Desktop debe estar iniciado antes de instalar FuncAssist.'
}

New-Item -ItemType Directory -Force $InstallDir | Out-Null

$composeSource = Resolve-SourceFile 'compose.yaml'
$actualizarSource = Resolve-SourceFile 'actualizar.ps1'
$estadoSource = Resolve-SourceFile 'estado.ps1'
$envExampleSource = Resolve-SourceFile '.env.example'

Copy-DeploymentFile $composeSource $InstallDir
Copy-DeploymentFile $actualizarSource $InstallDir
Copy-DeploymentFile $estadoSource $InstallDir

$envExample = Join-Path $InstallDir '.env.example'
if (-not (Test-Path $envExample)) {
  Copy-DeploymentFile $envExampleSource $InstallDir
}

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
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$runLevel = if ($isAdmin) { 'Highest' } else { 'Limited' }
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel $runLevel
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($trigger, $repeat) -Principal $principal -Force | Out-Null

Write-Host "Tarea '$taskName' instalada. Las actualizaciones se comprobarán cada $IntervalMinutes minutos."
Write-Host "Configure $envFile y ejecute: docker compose --env-file $envFile -f $InstallDir\compose.yaml up -d"
