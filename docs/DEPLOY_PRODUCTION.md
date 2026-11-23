# Despliegue de producción

## Instalación nueva

`.env` debe contener únicamente la configuración no sensible y `POSTGRES_PASSWORD` durante el bootstrap. `SECRET_KEY` y `PBKDF2_SALT` se generan fuera del repositorio.

```bash
export SECRET_KEY="$(openssl rand -hex 32)"
export PBKDF2_SALT="$(openssl rand -hex 16)"
export POSTGRES_PASSWORD="$(openssl rand -base64 32)"
docker compose up -d openbao
./scripts/openbao/bootstrap.sh
```

Distribuya las claves de recuperación de `openbao-init.txt` entre los custodios y elimine el archivo. Después, elimine también `SECRET_KEY` y `PBKDF2_SALT` del entorno de la terminal. `POSTGRES_PASSWORD` se conserva en OpenBao; puede quitarse de `.env` después del bootstrap.

## Arranque y reinicios

```bash
./scripts/deploy.sh
```

El script valida certificados, credenciales del agente y el renderizado de los tres secretos antes de iniciar PostgreSQL, backend y frontend. Si OpenBao está sellado, solicite tres claves:

```bash
./scripts/openbao/unseal.sh
./scripts/deploy.sh
```

## Instalaciones existentes

No ejecute nuevamente `bootstrap.sh`: generaría una nueva instancia de OpenBao. Añada `postgres_password` al secreto existente usando un token administrativo temporal o una operación controlada de recuperación. El valor debe ser exactamente la contraseña usada por la instancia actual de PostgreSQL.
