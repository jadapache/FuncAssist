# HTTPS en la red corporativa

Guía para publicar FuncAssist en un servidor interno al que los usuarios entran por la red local (por ejemplo `http://10.20.30.40:6728`).

## Por qué hace falta HTTPS

Los navegadores solo activan algunas funciones en un **contexto seguro**: páginas servidas por HTTPS o por `http://localhost`. Una dirección `http://<IP>` o `http://<nombre>` de la red **no** es un contexto seguro.

| Función | En `http://<IP>` | Qué se usa en FuncAssist |
|---|---|---|
| WebGPU | No disponible | Modelos de redacción en el navegador (WebLLM) y aceleración de Whisper |
| Web Locks | No disponible | Evitar que varias pestañas carguen el modelo a la vez |
| Cache API | No disponible | Caché de los modelos del navegador (sin ella se vuelven a descargar) |
| `navigator.clipboard`, `crypto.randomUUID` | No disponibles | Botones de copiar e identificadores. La aplicación usa alternativas compatibles con HTTP. |

Además, por HTTP las contraseñas, los tokens de sesión y las claves de API viajan sin cifrar por la red.

**Sin HTTPS sigue funcionando**: el chat y la transcripción con proveedores en el servidor o en la nube, la transcripción en el navegador (solo con la CPU, más lenta y sin caché del modelo), copiar y el resto de la aplicación. **No funcionan** los modelos de redacción en el navegador: Configuración lo indica con un aviso.

## Cómo se activa

El contenedor `frontend` (nginx) decide al arrancar:

- FuncAssist se sirve **solo por HTTPS**. En `TLS_CERT_DIR` (por defecto `./certs`, junto a `compose.yaml`) deben existir `tls.crt` y `tls.key`; si faltan, el contenedor `frontend` no arranca.
- El puerto publicado `APP_PORT` (6728) solo habla TLS. Una petición `http://<servidor>:6728` se redirige a `https://<servidor>:6728`. No se publica ningún puerto HTTP plano.

El registro del contenedor lo dice en la primera línea: `docker compose logs frontend | grep funcassist`.

### Pasos

1. Consigue el certificado (siguiente sección) en formato PEM:
   - `certs/tls.crt`: certificado del servidor **seguido de** los certificados intermedios de la CA (cadena completa).
   - `certs/tls.key`: clave privada sin contraseña.
2. En `.env`:
   ```
   APP_PORT=6728               # puerto HTTPS publicado
   FRONTEND_URL=https://funcassist.miempresa.local
   ```
3. `docker compose up -d --force-recreate frontend backend`
4. Comprueba:
   ```
   docker compose logs frontend | grep funcassist      # "HTTPS habilitado…"
   curl -kI https://<servidor>:6728/                     # 200 por HTTPS
   curl -I https://funcassist.miempresa.local/           # 200, sin errores de certificado
   ```
5. En un equipo de usuario, abre la dirección HTTPS: el candado no debe mostrar avisos. En Configuración → Modelo en este navegador debe aparecer "WebGPU activo".

**Renovación**: sustituye los dos archivos y ejecuta `docker compose restart frontend`.

`certs/` está en `.gitignore` y `.dockerignore`: la clave nunca entra en el repositorio ni en la imagen.

## De dónde sacar el certificado

El certificado debe estar firmado por una autoridad en la que confíen los equipos de los usuarios y su **SAN** (Subject Alternative Name) debe incluir exactamente el nombre (o la IP) con el que entran.

### Opción 1 (recomendada): CA corporativa

Si la empresa tiene una CA interna (por ejemplo Active Directory Certificate Services), los equipos del dominio ya confían en ella.

1. Pide a TI un nombre DNS interno para el servidor (por ejemplo `funcassist.miempresa.local`). Es preferible a la IP: el certificado no depende de que la IP cambie.
2. Genera la clave y la solicitud (CSR) en el servidor:
   ```
   openssl req -new -newkey rsa:2048 -nodes \
     -keyout certs/tls.key -out funcassist.csr \
     -subj "/CN=funcassist.miempresa.local" \
     -addext "subjectAltName=DNS:funcassist.miempresa.local,IP:10.20.30.40"
   ```
3. Envía `funcassist.csr` a TI para que la firme con la plantilla de "Servidor web".
4. Guarda el certificado devuelto, seguido de los intermedios, como `certs/tls.crt`.

### Opción 2: CA propia distribuida por GPO

Si no hay CA corporativa, se puede crear una CA solo para este servicio y distribuir su certificado raíz a los equipos por directiva de grupo (*Configuración del equipo → Directivas → Configuración de Windows → Configuración de seguridad → Directivas de clave pública → Entidades de certificación raíz de confianza*). Chrome y Edge en Windows usan ese almacén. En Firefox hay que activar `security.enterprise_roots.enabled`, también por directiva.

```
# CA (guardar ca.key fuera del servidor y con acceso restringido)
openssl req -x509 -newkey rsa:4096 -nodes -days 3650 -keyout ca.key -out ca.crt -subj "/CN=FuncAssist CA interna"
# Certificado del servidor, firmado por esa CA
openssl req -new -newkey rsa:2048 -nodes -keyout certs/tls.key -out funcassist.csr -subj "/CN=funcassist.miempresa.local"
printf "subjectAltName=DNS:funcassist.miempresa.local,IP:10.20.30.40\nextendedKeyUsage=serverAuth\n" > san.ext
openssl x509 -req -in funcassist.csr -CA ca.crt -CAkey ca.key -CAcreateserial -days 825 -sha256 -extfile san.ext -out certs/tls.crt
```

Distribuye `ca.crt` (nunca `ca.key`).

### Opción 3: dominio público y Let's Encrypt

Si la empresa tiene un dominio público, se puede usar un nombre bajo él (por ejemplo `funcassist.interno.miempresa.com`) que resuelva a la IP interna solo en el DNS corporativo, con un certificado de Let's Encrypt obtenido por el reto **DNS-01** (no necesita que el servidor sea accesible desde Internet). Ningún equipo necesita configuración, pero el certificado caduca cada 90 días y hay que automatizar la renovación (certbot o acme.sh con la API del proveedor DNS).

### Alternativa temporal (no recomendada)

Mientras llega el certificado, TI puede marcar la dirección HTTP como segura en Chrome y Edge con la directiva `OverrideSecurityRestrictionsOnInsecureOrigin` (lista de orígenes, por ejemplo `http://10.20.30.40:6728`), distribuida por GPO. Activa WebGPU en esa dirección, pero el tráfico sigue sin cifrar.

## Problemas frecuentes

| Síntoma | Causa |
|---|---|
| `NET::ERR_CERT_AUTHORITY_INVALID` | El equipo no confía en la CA que firmó el certificado (opción 2: falta la raíz en el almacén). |
| `NET::ERR_CERT_COMMON_NAME_INVALID` | El nombre o la IP con que se entra no está en el SAN del certificado. |
| El contenedor `frontend` no arranca ("no hay certificado") | Los nombres deben ser exactamente `tls.crt` y `tls.key`, no estar vacíos, y estar en `TLS_CERT_DIR`. |
| `nginx: [emerg] cannot load certificate key` | La clave tiene contraseña o no corresponde al certificado. |
| HTTPS correcto pero "WebGPU no detectado" | Aceleración por hardware desactivada en el navegador, o GPU no compatible: revisar `chrome://gpu` / `edge://gpu`. |
