param([string]$InstallDir = "$env:ProgramData\FuncAssist", [switch]$RemoveVolumes)
Set-Location $InstallDir; docker compose down; if ($RemoveVolumes) { docker compose down --volumes }; Write-Host 'Contenedores detenidos; los volúmenes se conservaron.'
