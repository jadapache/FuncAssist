# Despliegue en Windows

La publicación de `main` ejecuta pruebas y publica dos imágenes en GHCR: `funcassist-frontend` y `funcassist-backend`, etiquetadas como `latest` y `sha-<commit>`. El backend usa `python:3.12-slim-bookworm` y `supervisord` para mantener FastAPI bajo supervisión; Nginx sirve el frontend.

## Instalación

1. Instale Docker Desktop con WSL2 y compruebe `docker info`.
2. Cree `C:\ProgramData\FuncAssist`, copie `compose.yaml` y `.env.example` como `.env`.
3. Configure secretos fuertes en `.env` y, si el paquete es privado, haga `docker login ghcr.io` con un token que tenga únicamente `read:packages`.
4. Ejecute `docker compose pull` y `docker compose up -d`.
5. Compruebe `http://localhost:6728` y ejecute `scripts/estado.ps1`.

## Actualización y rollback

`scripts/actualizar.ps1` descarga las imágenes, recrea los servicios y conserva todos los volúmenes. Para desplegar una versión reproducible, establezca `APP_VERSION=sha-<commit>` en `.env`; para volver atrás, ejecute `scripts/rollback.ps1 -Version sha-<commit>`. No se ejecuta `down --volumes` durante una actualización.

La base de datos permanece en `postgres_data`; antes de cambios importantes realice un backup con `docker compose exec db pg_dump -U "$env:POSTGRES_USER" "$env:POSTGRES_DB" > backup.sql`. Las migraciones existentes de la aplicación se ejecutan al iniciar y no se agregan migraciones destructivas al despliegue.

`scripts/instalar.ps1` registra automáticamente una tarea de Windows Task Scheduler para el usuario actual. La tarea se ejecuta al iniciar sesión y luego cada 15 minutos (configurable con `-IntervalMinutes`). El usuario no necesita ejecutar scripts después de la instalación; el mutex global evita ejecuciones simultáneas. Docker Desktop debe estar configurado para iniciarse con Windows y el primer `.env` debe completarse durante la instalación.
