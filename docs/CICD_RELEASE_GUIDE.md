# CI/CD Pipeline y Guia de Releases (Web / SaaS)

Guia completa para el pipeline de integracion continua y liberacion de versiones del sistema FuncAssist utilizando GitHub Actions.

---

## 1. Arquitectura de CI/CD

```
GitHub Actions Workflows:
|-- On Pull Request (main / develop):
|   `-- PR Checks (linting Python & Frontend, typecheck TypeScript, pytest backend)
|
|-- On Push (main / develop):
|   |-- Test Suite (Python + Frontend)
|   `-- Build Frontend (Vite bundle)
|
`-- On Tag Push (v*.*.*):
    `-- Automated GitHub Release (Publicacion de paquete frontend dist y notas de version)
```

---

## 2. Flujos de Trabajo en GitHub Actions

Los flujos de trabajo estan ubicados en `.github/workflows/`:

### 2.1 Flujo Principal: `.github/workflows/ci-cd.yml`
Se ejecuta en `push` a ramas `main` y `develop`, y en la creacion de etiquetas de version `v*`.

* **Fase 1: Tests & Typechecks (`test`)**
  - Configura Node.js 24 y Python 3.11.
  - Instala dependencias y ejecuta la suite de pruebas backend con `pytest` y generacion de cobertura XML.
  - Valida tipos de TypeScript en el Frontend (`npm run typecheck --prefix frontend`).
  - Ejecuta el linter del frontend (`npm run lint --prefix frontend`).
* **Fase 2: Compilacion Frontend (`build`)**
  - Genera el bundle de produccion de Vite (`npm run build --prefix frontend`).
  - Almacena el artefacto `frontend-dist` temporalmente.
* **Fase 3: Publicacion de Release (`release`)**
  - Se activa unicamente ante tags `v*` (ej. `v0.3.0`).
  - Empaqueta el artefacto distribuible de frontend (`funcassist-frontend-dist.tar.gz`).
  - Genera notas de version automaticas y publica la release en GitHub.

### 2.2 Verificacion de Pull Requests: `.github/workflows/pr-checks.yml`
Se activa en cualquier Pull Request hacia `main` o `develop`.
- Valida estandares de codigo Python con `flake8` y `black`.
- Verifica tipos en TypeScript (`tsc -b`).
- Ejecuta los tests unitarios e integrados de backend.
- Comprueba que la compilacion de frontend termine sin errores.

---

## 3. Configuracion de Secretos en GitHub

En el repositorio de GitHub (**Settings** -> **Secrets and variables** -> **Actions**):
- `CODECOV_TOKEN` (Opcional): Token para metricas de cobertura de codigo enviadas a Codecov.
- `GITHUB_TOKEN`: Provisto automaticamente por GitHub Actions para crear la release y adjuntar artefactos.

---

## 4. Guia Paso a Paso para Publicar una Nueva Version

Cuando desees liberar una nueva version:

### Paso 1: Sincronizar versiones en el proyecto
Asegurate de que la version coincida en los archivos principales:
1. `package.json` -> `"version": "0.3.0"`
2. `frontend/package.json` -> `"version": "0.3.0"`

### Paso 2: Crear el commit y la etiqueta Git
```bash
git add .
git commit -m "chore: release v0.3.0"
git tag -a v0.3.0 -m "Release version 0.3.0"
```

### Paso 3: Enviar a GitHub
```bash
git push origin main
git push origin v0.3.0
```

### Paso 4: Monitorear el despliegue
1. Ve a la pestana **Actions** en tu repositorio de GitHub.
2. Observa el progreso del workflow **CI/CD Pipeline - Build & Release**.
3. Una vez finalizado, el artefacto web estara publicado en la seccion **Releases** de GitHub.

---

## 5. Comandos Locales Utiles

```bash
# Compilar frontend
npm --prefix frontend run build

# Comprobar tipos TypeScript
npm --prefix frontend run typecheck

# Ejecutar tests de Backend
pytest backend/tests/ -v
```
