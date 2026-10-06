# CI/CD Pipeline & Guía de Releases Desktop (Tauri)

Guía completa para el manejo, mantenimiento y publicación de versiones del sistema **QA Project MGMT** utilizando **GitHub Actions** y **Tauri**.

---

## 🏗️ Arquitectura de CI/CD y Distribución

```
GitHub Actions Workflows:
├── On Pull Request (main / develop):
│   └── PR Checks (linting Python & Frontend, typecheck TypeScript, pytest backend)
│
├── On Push (main / develop):
│   ├── Test Suite (Python + Frontend)
│   ├── Build Frontend (Vite bundle)
│   └── Build Tauri Desktop (Instaladores Windows)
│
└── On Tag Push (v*.*.*):
    └── Automated GitHub Release (Publicación de .msi, .exe, notas de versión)

App de Escritorio (Cliente):
├── Inicio / Cada 6 horas:
│   └── Comprueba actualizaciones contra GitHub Releases
└── Si hay nueva versión:
    └── Notificación interactiva → Descarga → Instalación → Reinicio automático
```

---

## ⚙️ 1. Flujos de Trabajo en GitHub Actions

Los flujos de trabajo están ubicados en `.github/workflows/`:

### 1.1 Flujo Principal: `.github/workflows/ci-cd.yml`
Se ejecuta en `push` a ramas `main` y `develop`, y en la creación de etiquetas de versión `v*`.

* **Fase 1: Tests & Typechecks (`test`)**
  - Configura Node.js 20 y Python 3.11.
  - Instala dependencias y ejecuta la suite de pruebas backend con `pytest` y generación de cobertura XML.
  - Valida tipos de TypeScript en el Frontend (`npm run typecheck --prefix frontend`).
  - Ejecuta el linter del frontend (`npm run lint --prefix frontend`).
* **Fase 2: Compilación Frontend (`build`)**
  - Genera el bundle de producción de Vite (`npm run build --prefix frontend`).
  - Almacena los artefactos `dist/` temporalmente.
* **Fase 3: Compilación Desktop Windows (`build-tauri`)**
  - Entorno `windows-latest` con toolchain de Rust (`x86_64-pc-windows-msvc`).
  - Instalación silenciosa de **WebView2 Runtime**.
  - Cacheo de dependencias de Rust con `rust-cache`.
  - Empaquetado con Tauri CLI (`npx @tauri-apps/cli build`), generando instaladores `.msi` y `.exe` (NSIS).
* **Fase 4: Publicación de Release (`release`)**
  - Se activa únicamente ante tags `v*` (ej. `v0.2.0`).
  - Genera notas de versión automáticas y adjunta los instaladores compilados a la GitHub Release.

### 1.2 Verificación de Pull Requests: `.github/workflows/pr-checks.yml`
Se activa en cualquier Pull Request hacia `main` o `develop`.
- Valida estándares de código Python con `flake8` y `black`.
- Verifica tipos en TypeScript (`tsc -b`).
- Ejecuta los tests unitarios e integrados de backend.
- Comprueba que la compilación de frontend termine sin errores.

---

## 🔐 2. Configuración de Secretos y Llaves de Firma

Para habilitar la firma de paquetes y auto-actualizaciones seguras en Tauri:

### 2.1 Generar Par de Llaves (Configuración inicial única)
Ejecuta en tu terminal local:
```bash
# Generar llaves privada y pública
npx @tauri-apps/cli signer generate -w ~/.tauri/qa_mgmt.key
```
El comando generará:
1. **Clave privada**: Guardada en `~/.tauri/qa_mgmt.key` (con contraseña).
2. **Clave pública**: Cadena de texto mostrada en la terminal.

### 2.2 Configurar GitHub Secrets
En el repositorio de GitHub:
1. Ve a **Settings** → **Secrets and variables** → **Actions**.
2. Añade los siguientes secretos:
   - `TAURI_PRIVATE_KEY`: Contenido de la clave privada (`~/.tauri/qa_mgmt.key`).
   - `TAURI_KEY_PASSWORD`: Contraseña asignada al generar la clave.
   - `CODECOV_TOKEN` *(Opcional)*: Token para métricas de cobertura de código.

### 2.3 Configurar Clave Pública en `src-tauri/tauri.conf.json`
Actualiza el valor de `pubkey` en `src-tauri/tauri.conf.json`:
```json
"plugins": {
  "updater": {
    "endpoints": [
      "https://github.com/jadapache/qa_project_mgmt/releases/latest/download/latest.json"
    ],
    "pubkey": "PEGAR_AQUI_LA_CLAVE_PUBLICA_GENERADA"
  }
}
```

---

## 🔄 3. Sistema de Auto-Actualización

El sistema cuenta con soporte reactivo integrado tanto en el cliente de escritorio como en la interfaz web:

- **Hook `useAppUpdater` (`frontend/src/hooks/useAppUpdater.ts`):**
  - Detecta si la aplicación se ejecuta dentro del runtime de Tauri.
  - Si se ejecuta en un navegador web estándar, se desactiva silenciosamente sin provocar errores en React.
  - Realiza revisiones periódicas no intrusivas en segundo plano (al iniciar y cada 6 horas).
  - Permite posponer la actualización guardando la versión descartada en `localStorage`.
- **Componente `UpdateNotification` (`frontend/src/components/UpdateNotification.tsx`):**
  - Tarjeta flotante en la esquina inferior derecha con tema adaptativo (modo claro y oscuro).
  - Permite actualizar inmediatamente con indicador visual de progreso o posponer para más tarde.
  - Al completar la instalación, relanza la aplicación de forma transparente.

---

## 🚀 4. Guía Paso a Paso para Publicar una Nueva Versión

Cuando desees liberar una nueva versión:

### Paso 1: Sincronizar versiones en el proyecto
Asegúrate de que la versión coincida en los 3 archivos principales:
1. `package.json` → `"version": "0.3.0"`
2. `frontend/package.json` → `"version": "0.3.0"`
3. `src-tauri/tauri.conf.json` → `"version": "0.3.0"`
4. `src-tauri/Cargo.toml` → `version = "0.3.0"`

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
1. Ve a la pestaña **Actions** en tu repositorio de GitHub.
2. Observa el progreso del workflow **CI/CD Pipeline - Build & Release**.
3. Una vez finalizado, los instaladores de Windows (`.msi` y `.exe`) estarán publicados en la sección **Releases** de GitHub y disponibles para auto-actualización.

---

## 🛠️ 5. Comandos Locales Útiles

```bash
# Compilar frontend
npm --prefix frontend run build

# Comprobar tipos TypeScript
npm --prefix frontend run typecheck

# Ejecutar tests de Backend
pytest backend/tests/ -v

# Compilar ejecutable de escritorio localmente (requiere Rust instalado)
npm run build:desktop
```
