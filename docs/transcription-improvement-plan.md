# Plan de mejora: proceso de transcripción

> Estado: propuesta para revisión · Fecha: 2026-11-20
> Alcance: `backend/app/features/transcription/**`, `backend/app/api/transcription*.py`, `backend/app/schemas/transcription.py`, modelo `transcriptions`, `frontend/src/features/transcription/**`, `frontend/src/context/BackgroundJobContext.tsx`.

Revisión del código actual de las dos rutas de transcripción: en la nube (Groq u OpenAI, orquestada por el backend) y en el navegador (Whisper ONNX en un Web Worker). Cada punto incluye la evidencia, la causa, la corrección propuesta y el criterio de aceptación. Las rutas del frontend son relativas a `frontend/src/features/transcription/` salvo que se indique otra cosa.

## Estado de implementación (2026-11-21)

Implementado en el árbol de trabajo, sin commit. **Nada se ha ejecutado**: el entorno donde se escribió no tiene Python, Node ni Docker. El contrato resultante está en `docs/TRANSCRIPTION_PROCESS.md`.

| # | Estado | Dónde |
|---|---|---|
| 1 | Hecho | `errors.py` (códigos tipados), `jobs.py` (punto único de fallo y log) |
| 2 | Hecho | `user_id` + migración `core/transcription_migration.py`, `load_owned_record` en todos los endpoints y en el SSE; rutas locales solo con `TRANSCRIPTION_DESKTOP_MODE`; script `scripts/assign_transcriptions_owner.py` |
| 3 | Hecho | `chunking.py`, `media.py`, `pipeline.py` (fragmentos con reanudación) |
| 4 | Hecho | `records.py` (sesiones async), `media.py` (subprocesos async), subida en streaming con límite |
| 5 | Hecho | columnas `progress_json`/`error_code`/`started_at`/`finished_at`, `GET /jobs/active`, `interrupted` al arrancar, cola con límite |
| 6 | Hecho | cancelación de la tarea y de ffmpeg; XHR con abort; cancelación del worker del navegador |
| 7 | Hecho | `progress.py` (tramos, progreso monótono, ETA medida); etapas del worker |
| 8 | Hecho | SSE v2 con `id`/`Last-Event-ID`; `api/progressStream.ts` con reconexión y sondeo de respaldo |
| 9 | Hecho | Fase 1: diarización de OpenAI con referencias entre fragmentos; sin clave, un único hablante. Fase 2: diarización en el navegador con pyannote-segmentation-3.0 + WeSpeaker + clustering (`workers/diarizer.ts`, `utils/speakerDiarization.ts`), opcional por trabajo |
| 10 | Hecho, con una desviación | proveedor configurado respetado, reintentos, filtro de alucinaciones, glosario, `user_id` en el resumen. El modelo se valida contra una lista de modelos con segmentos, no contra el catálogo |
| 11 | Hecho | ventanas solapadas, decodificación y WAV de cualquier profundidad, VAD, worker persistente |
| 12 | Hecho | `cleanup.py`, recorte de silencios con mapa de tiempos, `text_raw`/`text`, interruptor Literal/Limpio |
| 13 | Hecho | resumen después de `complete` con `summary_status`; map-reduce en `summarizer.py` |
| 14 | Hecho | `segments.py` + `PATCH /speakers`, `PATCH /segments/{id}`, `POST .../split`; UI de edición |
| 15 | Hecho | pipeline por pasos, código muerto eliminado (`audio_analyzer.py`, compresores de ffmpeg) |
| 16 | Hecho | almacén único de trabajos, hooks divididos, componentes muertos eliminados |
| 17 | Hecho, sin verificar | pruebas nuevas en backend y frontend, `metrics.py` + `GET /stats`, documentación |

**Para verificar**
1. Frontend: `npm install`, `npm run typecheck`, `npm run lint`, `npm test`.
2. Backend (en el contenedor): `python -m pytest tests -q`.
3. Asignar las transcripciones existentes: `python -m scripts.assign_transcriptions_owner --user <id>` y después con `--apply`.
4. Prueba real con Groq (audio de más de 1 h con silencios) y con OpenAI con diarización (3 hablantes). Comprobar los parámetros de `gpt-4o-transcribe-diarize` contra la documentación vigente.

## Resumen

| # | Prioridad | Problema | Impacto |
|---|---|---|---|
| 1 | P0 | Errores del proveedor no marcan el trabajo como fallido | Trabajos atascados en "transcribiendo" para siempre |
| 2 | P0 | Transcripciones sin propietario y lectura de rutas arbitrarias del servidor | Cualquier usuario ve, descarga o borra las transcripciones de otros |
| 3 | P0 | Audios largos fallan: sin fragmentación y límite de 25 MB del proveedor | Reuniones de más de ~1 h no se pueden transcribir en la nube |
| 4 | P0 | Bloqueo del event loop | Todo el backend se congela durante subidas, compresión y accesos a BD |
| 5 | P1 | Estado de trabajos solo en memoria | Un reinicio deja trabajos huérfanos; no se ven desde otra pestaña |
| 6 | P1 | Cancelación que no cancela | Se sigue consumiendo crédito; el registro reaparece; el navegador se cuelga |
| 7 | P1 | Progreso simulado | Saltos fijos, retrocesos, minutos en 35 %, ETA inventada |
| 8 | P1 | Transporte de progreso en el frontend | SSE y sondeo duplicados, sin reconexión, fin detectado por `progress == 100` |
| 9 | P1 | Diarización falsa | Hablantes alternados por posición; el resumen inventa participantes |
| 10 | P1 | Calidad de la transcripción en la nube | Proveedor configurado ignorado, sin reintentos, alucinaciones de Whisper |
| 11 | P1 | Calidad de la ruta en navegador | Palabras cortadas cada 30 s, audio a cero en WAV no 16 bit, modelo recargado por trabajo |
| 12 | P1 | Pausas y marcadores del discurso | Silencios facturados y con alucinaciones; turnos partidos por pausas; muletillas en el texto, el resumen y los documentos |
| 13 | P2 | Resumen acoplado y con pérdida de contenido | La transcripción no está disponible hasta tener resumen; se descarta el centro de la reunión |
| 14 | P2 | Edición de hablantes limitada | Solo renombrar; mapa desactualizado tras el primer cambio |
| 15 | P2 | Estructura del backend | Envoltorios síncronos, código muerto, errores sin tipar |
| 16 | P2 | Estructura del frontend | Estado duplicado en dos contextos, hooks de 500-700 líneas, `any` |
| 17 | P2 | Pruebas, métricas y documentación | Sin cobertura de pipeline, progreso ni cancelación; documento de arquitectura desactualizado |

## Decisiones abiertas

Conviene cerrarlas antes de empezar; cada una lleva la opción recomendada.

1. **Proveedor de diarización** (punto 9). Recomendado: diarización real en la nube con el modelo de diarización de OpenAI cuando haya clave de OpenAI y, sin ella, un único hablante con herramientas de edición manual. Diarización en el navegador (segmentación pyannote ONNX + embeddings de voz) como fase 2. El backend mantiene la política de cero inferencia local.
2. **Modo escritorio** (punto 2). La app se despliega como web en Docker: `pick-local-file` abre un diálogo nativo *en el servidor* y `register-local-path` registra cualquier ruta del servidor. En el frontend esa rama ya no es alcanzable. Recomendado: eliminar ambos endpoints, o dejarlos detrás de `TRANSCRIPTION_DESKTOP_MODE=true` limitados a directorios permitidos.
3. **Duración máxima admitida**. Recomendado: 4 h por archivo, configurable con `TRANSCRIPTION_MAX_DURATION_S`.
4. **Texto literal o limpio** (punto 12). Recomendado: guardar siempre los dos, mostrar el limpio por defecto con un interruptor "Literal / Limpio", y usar el limpio para resúmenes, documentos y base de conocimiento. La limpieza con LLM solo se aplica si el usuario tiene un proveedor de redacción en la nube; quien transcribe en el navegador por privacidad recibe solo la limpieza por reglas.

---

## P0: bloqueantes

### 1. Errores del proveedor no marcan el trabajo como fallido

**Evidencia**
- `service.py:421-422`: `WhisperCloudService.transcribe` se llama fuera de cualquier `try`. Si lanza `RuntimeError` (respuesta 4xx/5xx, `whisper_cloud.py:131-138`), `httpx.TimeoutException` (300 s, `whisper_cloud.py:124`) o `ValueError` (sin credenciales, `whisper_cloud.py:56`), nadie llama a `_fail_job`.
- `api/transcription.py:281-283`: la tarea en segundo plano captura la excepción con `pass`, sin registrarla en el log.
- Resultado: el estado queda en `transcribing`, 35 %, y el frontend lo muestra en curso indefinidamente.
- Lo mismo ocurre con un fallo en la diarización (`service.py:433`) o en `_persist_result`.

**Corrección propuesta**
1. Un único punto de control en el orquestador: `try/except` alrededor de todo el pipeline que, para cualquier excepción no controlada, llama a `_fail_job` con un código tipado y registra el error con `logger.exception`.
2. Errores tipados `TranscriptionError(code, user_message, retryable)`, en paralelo con `AIError`. Códigos: `file_too_large`, `unsupported_format`, `corrupt_media`, `no_credentials`, `auth_error`, `rate_limit`, `timeout`, `provider_unavailable`, `empty_result`, `cancelled`, `interrupted`, `internal`.
3. El estado de error expone `error_code`, `error` (mensaje para el usuario) y `retryable`.

**Aceptación**: una clave inválida, un 429 o un timeout del proveedor dejan el trabajo en `failed` en menos de 1 s, con un código específico, una entrada en el log y el mensaje visible en la interfaz.

**Archivos**: `features/transcription/service.py`, `whisper_cloud.py`, `api/transcription.py`, `core/exceptions.py`, `schemas/transcription.py`.

### 2. Transcripciones sin propietario y lectura de rutas arbitrarias

**Evidencia**
- `db/models.py:719-742`: la tabla `transcriptions` no tiene `user_id`.
- `api/transcription.py:464-468`: `GET /list` devuelve las transcripciones de todos los usuarios.
- `status`, `result`, `progress-stream`, `summary`, `speakers`, `save-to-knowledge` y `DELETE` aceptan cualquier id sin comprobar a quién pertenece.
- `register-local-path` (`api/transcription.py:129`, `storage.py:254-270`) acepta cualquier ruta existente del servidor con extensión de audio o vídeo. Después, la transcripción la lee y la envía a un proveedor externo.
- `pick-local-file` ejecuta un diálogo nativo de Windows en el proceso del servidor.

**Corrección propuesta**
1. Migración: columna `user_id` (indexada) en `transcriptions`. Sin excepción para administradores: los registros existentes quedan sin propietario, invisibles, hasta asignarlos con `scripts/assign_transcriptions_owner.py`.
2. Repositorio con filtro por usuario en `get/list/delete/upsert`. Dependencia `get_owned_transcription(transcription_id, current_user)` que responde 404 si el registro no es del usuario, usada en todos los endpoints por id, incluido el SSE.
3. Decisión abierta 2: eliminar `pick-local-file` y `register-local-path`, o limitarlos a `TRANSCRIPTION_LOCAL_ROOTS` con comprobación de `Path.resolve().is_relative_to(...)`.
4. `extract-audio` y `dictate`: límite de tamaño y verificación de tipo antes de procesar.

**Aceptación**: un usuario B recibe 404 en todos los endpoints con el id de una transcripción del usuario A, y no la ve en `/list`. Prueba de funcionalidad con dos usuarios.

**Archivos**: `db/models.py`, migración en `core/migration.py`, `db/repositories/transcription_repository.py`, `api/transcription.py`, `api/transcription_stream.py`, `features/transcription/storage.py`.

### 3. Audios largos: sin fragmentación

**Evidencia**
- `whisper_cloud.py:93-118` comprime a MP3 mono de 48 kbps y envía el archivo en **una** petición. OpenAI y el plan gratuito de Groq rechazan archivos de más de 25 MB, que a 48 kbps equivalen a unos 70 minutos.
- Timeout fijo de 300 s por petición (`whisper_cloud.py:124`).
- Si una petición falla, se pierde todo el trabajo: no hay resultado parcial ni reintento por partes.
- Sin fragmentos, no hay forma de informar un progreso real durante la transcripción (ver punto 7).

**Corrección propuesta**
1. Nuevo `features/transcription/chunking.py`:
   - `plan_chunks(duration_s)`: fragmentos de unos 10 min (`TRANSCRIPTION_CHUNK_S=600`) con 2 s de solapamiento.
   - Los cortes se desplazan al silencio más cercano dentro de ±15 s, usando `ffmpeg silencedetect` una sola vez sobre el audio completo.
   - `export_chunk(audio, start, end)` genera MP3 mono de 16 kHz y 48 kbps (unos 3,6 MB por fragmento).
2. Transcripción por fragmento:
   - Concurrencia `TRANSCRIPTION_CHUNK_CONCURRENCY`: 2 en Groq, por su límite de segundos de audio por hora, y 4 en OpenAI.
   - Cada fragmento se reintenta por separado (punto 10).
   - Se pasa como `prompt` la cola de texto del fragmento anterior, hasta unos 200 tokens, para mantener la continuidad de nombres y términos.
3. Unión de resultados: se desplazan las marcas de tiempo según el inicio de cada fragmento y, en la zona de solapamiento, se conserva el segmento cuyo punto medio cae en el fragmento "propietario". La deduplicación se prueba con textos repetidos.
4. Fragmentos y resultados parciales en `transcriptions/<id>/chunks/`. Un reintento del trabajo solo vuelve a pedir los fragmentos que fallaron.
5. Validación previa: duración máxima (decisión abierta 3) y error `file_too_large` con un mensaje claro.

**Aceptación**: un audio de 2 h se transcribe completo con Groq y con OpenAI, sin huecos ni duplicados en las uniones (prueba unitaria de la unión con segmentos sintéticos y prueba manual con un archivo real). Si falla un fragmento, se reintenta solo ese.

**Archivos**: `features/transcription/chunking.py` (nuevo), `whisper_cloud.py`, `service.py`, `ffmpeg_utils.py`.

### 4. Bloqueo del event loop

**Evidencia**
- `storage.py:454-478, 501-521, 524-542, 582-605`: cada acceso a BD crea un `ThreadPoolExecutor`, ejecuta `asyncio.run` en otro hilo y espera con `.result()` **dentro** del event loop. Cada lectura o escritura bloquea todas las peticiones del servidor, abre una conexión en otro loop y no comparte la sesión ni la transacción de la petición.
- `whisper_cloud.py:112`: `subprocess.run(ffmpeg ...)` síncrono dentro de una función `async`. La compresión de una reunión larga congela el servidor durante decenas de segundos.
- `api/transcription.py:166`: `await file.read()` carga el archivo completo en memoria, y nginx admite hasta 5 GB (`client_max_body_size 5192M`). `dictate` hace lo mismo.

**Corrección propuesta**
1. `storage.py` pasa a funciones `async` que reciben el repositorio; los endpoints lo obtienen con `Depends` y la sesión con ámbito de función (como en el chat). El pipeline en segundo plano abre su propia sesión con `get_db()` en cada paso de persistencia.
2. Todas las llamadas a ffmpeg o ffprobe con `asyncio.create_subprocess_exec`, con timeout y cancelables (también sirven para el progreso del punto 7).
3. Subida en streaming: escribir `UploadFile` a disco en bloques de 1 MB con `aiofiles` o `to_thread` y cortar al superar `TRANSCRIPTION_MAX_UPLOAD_MB` (por defecto 2048) con 413. Calcular el hash en el mismo recorrido.

**Aceptación**: durante la transcripción de un audio largo, `GET /api/health` responde en menos de 100 ms. La subida de un archivo de 1 GB no aumenta la memoria del proceso en más de unos 20 MB.

**Archivos**: `features/transcription/storage.py`, `whisper_cloud.py`, `ffmpeg_utils.py`, `audio_analyzer.py`, `api/transcription.py`, `api/deps.py`.

---

## P1: importantes

### 5. Estado de trabajos solo en memoria

**Evidencia**
- `service.py:40-41` (`_ACTIVE_JOBS`, `_CANCELLED_JOBS`), `storage.py:431-451` (`_ACTIVE_JOBS_CACHE`) y `transcription_stream.py:23-25`: el progreso vive solo en diccionarios del proceso.
- Tras un reinicio o despliegue, un trabajo en curso desaparece. El frontend lo restaura desde `localStorage` y, en `GET /status`, recibe 404 o un "completado" falso si existe el registro (`service.py:107-118`).
- No hay un endpoint que liste los trabajos activos del usuario, así que otra pestaña u otro dispositivo no los ve.
- Ningún límite de concurrencia: varias subidas lanzan varios pipelines a la vez.

**Corrección propuesta**
1. Persistir el estado en la fila de `transcriptions`: `status` (`queued`, `preprocessing`, `transcribing`, `diarizing`, `summarizing`, `complete`, `failed`, `cancelled`, `interrupted`), `progress_json` (último evento), `error_code`, `started_at` y `finished_at`. El diccionario en memoria queda solo como caché para el SSE.
2. Al arrancar, los trabajos en estado no terminal pasan a `interrupted` con `retryable=true`. El botón "Reintentar" reanuda desde los fragmentos ya hechos (punto 3).
3. `GET /transcription/jobs/active`: trabajos no terminales del usuario. El frontend lo usa al iniciar sesión en lugar de confiar en `localStorage`.
4. `TRANSCRIPTION_MAX_CONCURRENT_JOBS` (por defecto 2) con un semáforo; los demás trabajos quedan en `queued` con su posición.
5. Documentar el supuesto de un solo worker de uvicorn: el pub/sub del SSE es de proceso. Con varios workers habría que usar `LISTEN/NOTIFY` de Postgres; queda fuera de este plan.

**Aceptación**: si se reinicia el backend a mitad de un trabajo, al recargar el trabajo aparece como "Interrumpido" con la opción de reintentar, y el reintento no vuelve a transcribir los fragmentos ya completados.

**Archivos**: `db/models.py`, migración, `service.py`, `storage.py`, `api/transcription.py`, `main.py` (arranque), `context/TranscriptionContext.tsx`.

### 6. Cancelación que no cancela

**Evidencia**
- **Servidor**:
  - `service.py:121-134` solo añade el id a `_CANCELLED_JOBS` y borra el registro. El pipeline no lo consulta después del inicio (`service.py:186-187`), sigue llamando al proveedor y al final `_persist_result` vuelve a crear el registro (`service.py:486`).
  - No se guarda ninguna referencia a la tarea, así que no puede cancelarse.
- **Subida**: el `AbortController` se crea (`hooks/useTranscriptionPipeline.ts:353`), pero su `signal` no llega a `fetch`.
- **Navegador**:
  - Cancelar llama a `worker.terminate()` desde el gestor de streams (`hooks/useTranscriptionStreamManager.ts:88-90`). Un worker terminado no emite `message` ni `error`, así que la promesa de `providers/BrowserAsrProvider.ts:72-104` nunca se resuelve y `isUploading` queda en `true`.
  - El proveedor es un singleton que termina el worker anterior al empezar otro trabajo (`:66`), lo que cuelga el primero.
- `cancelledJobsRef` no se limpia al regenerar (`useTranscriptionPipeline.ts:422-475`): un trabajo cancelado y regenerado no muestra progreso.

**Corrección propuesta**
1. Registro de trabajos en el servicio: `transcription_id → asyncio.Task`. `cancel` llama a `task.cancel()`; el pipeline captura `CancelledError` en el orquestador, mata el subproceso de ffmpeg en curso, cierra las peticiones HTTP y marca `cancelled`.
2. Cancelar no borra la transcripción: la deja en `cancelled`, borra los temporales y el usuario la elimina si quiere. Así se evita que vuelva a aparecer.
3. Frontend: pasar `signal` a la subida (con XHR, ver punto 8) y, en el navegador, cancelar mediante el propio proveedor: `browserAsrProvider.cancel(jobId)` rechaza la promesa pendiente antes de terminar el worker.
4. Limpiar `cancelledJobsRef` al regenerar o reintentar.

**Aceptación**: tras cancelar en cualquier fase, no hay más peticiones al proveedor (comprobar en el log), la interfaz vuelve al estado inicial en menos de 1 s, el registro queda como `cancelled` y no reaparece como completado.

**Archivos**: `service.py`, `api/transcription.py`, `hooks/useTranscriptionPipeline.ts`, `hooks/useTranscriptionStreamManager.ts`, `providers/BrowserAsrProvider.ts`, `context/BackgroundJobContext.tsx`.

### 7. Progreso simulado

**Evidencia**
- **Servidor**:
  - Porcentajes fijos: 0, 15 (`service.py:361`), 35 (`service.py:414`) y 100. Durante la llamada al proveedor, que puede durar minutos, el progreso se queda en 35 %.
  - La ETA es un texto fijo (`_format_eta(30)`, `_format_eta(20)`).
  - No hay etapas `diarizing` ni `summarizing`, aunque el esquema las declara (`schemas/transcription.py:39`), y el resumen automático ocurre antes del 100 %.
- **Frontend, ruta de subida**: 5 → 20 → 15, así que el progreso retrocede (`useTranscriptionPipeline.ts:190, 225, 249`).
- **Frontend, ruta del navegador**:
  - El worker emite 10 y 20 fijos, y la descarga del modelo se etiqueta como `transcribing` (`workers/transcription.worker.ts:102, 150`).
  - Al terminar salta a 92 % "Registrando…" y espera el resumen sin más actualizaciones (`utils/clientTranscription.ts:136-161`).
- La ETA del navegador aplica dos suavizados (`utils/etaCalculator.ts:44-66`) y solo cubre la decodificación.

**Corrección propuesta**
1. Contrato de etapas único, compartido entre backend y frontend. Cada etapa tiene un tramo del porcentaje global y su propio progreso real:

| Etapa | Tramo | Fuente del progreso |
|---|---|---|
| `uploading` | 0-10 | bytes enviados (cliente, XHR `upload.onprogress`) |
| `preprocessing` | 10-20 | `ffmpeg -progress pipe:1` (`out_time_ms / duración`) |
| `transcribing` | 20-80 | fragmentos completados / total, ponderado por duración |
| `cleaning` | 80-85 | segmentos procesados / total (punto 12) |
| `diarizing` | 85-92 | inicio/fin (o fragmentos, si se diariza por fragmento) |
| `summarizing` | 92-99 | inicio/fin; no bloquea la transcripción (punto 13) |
| `complete` / `failed` / `cancelled` / `interrupted` | 100 / — | terminal |

2. Evento de progreso v2: `{seq, stage, stage_progress, progress, eta_seconds, chunks_done, chunks_total, message, error_code, error, retryable}`. `progress` nunca disminuye, porque el servidor aplica `max`.
3. La ETA sale de la velocidad medida (segundos de audio por segundo en los fragmentos completados) y de la duración restante. Solo se envía cuando hay al menos un fragmento terminado; antes, "calculando…".
4. Navegador: etapas `model_download` (con el progreso de descarga de transformers.js en bytes), `decoding` y `transcribing` (por ventanas). El resumen pasa a ser una etapa propia con su indicador o se lanza después de mostrar la transcripción.
5. Los textos de cada etapa se definen una sola vez (`utils/transcriptionStages.ts`); se elimina la copia de `components/ActiveTranscriptionItem.tsx:24-33`.

**Aceptación**: en una reunión de 1 h, el porcentaje avanza al menos cada 30 s, nunca retrocede, y la ETA tras el primer fragmento está dentro de ±30 % del tiempo real. Las pruebas unitarias del cálculo de tramos y de la ETA pasan.

**Archivos**: `service.py`, `ffmpeg_utils.py`, `schemas/transcription.py`, `api/transcription_stream.py`, `utils/transcriptionStages.ts`, `utils/etaCalculator.ts`, `workers/transcription.worker.ts`, `utils/clientTranscription.ts`, `hooks/useTranscriptionPipeline.ts`.

### 8. Transporte de progreso en el frontend

**Evidencia**
- `hooks/useTranscriptionStreamManager.ts:215-288`: abre el SSE **y** además consulta `GET /status` cada 2,5 s aunque el SSE funcione, así que cada actualización se procesa dos veces y `refreshTranscriptions` puede ejecutarse dos veces al terminar.
- **Reconexión**:
  - `onerror` descarta el `EventSource` sin reabrirlo (`:235-240`).
  - `hooks/useTranscriptionProgress.ts` tiene reconexión con backoff pero no se usa.
- **Detección de estados**:
  - `isDone = stage === 'complete' || progress === 100` (`:167`).
  - Todo estado no terminal se convierte en `transcribing` (`:169`).
  - Un trabajo se descarta si el mensaje contiene "no encontrado" (`:147`).
- **Sondeo**:
  - El intervalo conserva el `processJobPayload` del primer render (`:254`).
  - Las iteraciones asíncronas pueden solaparse.
  - Al cerrar sesión no se cierra ni el SSE ni el intervalo (`:216`).
- El JWT viaja en la query del SSE (`api/transcriptionApi.ts:87-91`) y queda en los logs de nginx.
- Un trabajo guardado en estado `uploading` se restaura, pero se excluye del SSE y del sondeo (`utils/transcriptionStorage.ts:13`), así que queda atascado para siempre.
- `localStorage` guarda en cada tick los `live_segments` crecientes (`context/TranscriptionContext.tsx:182-184`), con riesgo de agotar la cuota.

**Corrección propuesta**
1. SSE con `fetch` y lector de streams, reutilizando `SseFrameParser` de `features/chat/api/sseV2.ts`. El token va en la cabecera `Authorization`, igual que en el chat.
2. Eventos con nombre (`event: progress | segment | done | error`) e `id: seq`. Al reconectar se envía `Last-Event-ID` y el servidor responde con el último estado. Reconexión con backoff (1, 2, 4… hasta 30 s).
3. El sondeo solo se activa como respaldo cuando el SSE falla N veces seguidas, con referencias estables y sin solapamiento.
4. El fin se detecta solo por la etapa terminal. Los estados del frontend son los mismos que los del contrato del punto 7.
5. `localStorage` guarda solo `{id, title, kind, startedAt}`; el estado real se pide a `GET /jobs/active` (punto 5). Los segmentos en vivo no se guardan.
6. Los segmentos en vivo llegan como eventos `segment` incrementales, no como el array completo en cada actualización. Lo mismo para el worker del navegador, que hoy reenvía todo el array por fragmento.

**Aceptación**: con el SSE abierto no hay peticiones de sondeo. Al cortar la red 10 s, el progreso se recupera solo. Tras cerrar sesión no quedan conexiones ni intervalos abiertos. Pruebas con vitest del gestor de streams (fin, reconexión, error, cancelación).

**Archivos**: `hooks/useTranscriptionStreamManager.ts`, `api/transcriptionApi.ts`, `api/transcription_stream.py`, `utils/transcriptionStorage.ts`, `context/TranscriptionContext.tsx`; se elimina `hooks/useTranscriptionProgress.ts`.

### 9. Diarización falsa

**Evidencia**
- `whisper_cloud.py:162` asigna `Participante {(idx % 2) + 1}`, alternando por posición del segmento.
- `service.py:57` crea `SpeakerDiarization()` sin token, así que pyannote nunca se carga (y la política de cero inferencia local lo excluye). Siempre se usa `_heuristic_diarization` (`diarization.py:77-99`), que alterna entre **dos** hablantes ante pausas de más de 1,2 s o cada tercer segmento largo.
- El frontend presenta esas etiquetas como hablantes reales, y el resumen las convierte en `participants`.
- La ruta del navegador fija `Participante 1` (`workers/transcription.worker.ts:200, 209`). `enable_diarization: true` está fijado en cuatro sitios del frontend, sin interruptor ni número de hablantes.

**Corrección propuesta** (decisión abierta 1)
1. **No inventar hablantes.** Sin diarización real, todos los segmentos se marcan con un único hablante y `diarization: "none"` en el registro; la interfaz muestra "Hablantes sin identificar" y ofrece las herramientas del punto 14. Se eliminan la alternancia `idx % 2` y la heurística.
2. **Diarización en la nube** (`DiarizationProvider` con implementaciones intercambiables):
   - OpenAI: modelo de transcripción con diarización (`gpt-4o-transcribe-diarize`, formato de respuesta diarizado). **Antes de implementar, confirmar en la documentación actual de OpenAI** los parámetros (`response_format`, `chunking_strategy`, referencias de voz conocidas) y los límites de duración y tamaño.
   - Con fragmentación (punto 3), las etiquetas de cada fragmento son independientes. Se reconcilian pasando como referencias de voz muestras de 3-10 s de cada hablante del primer fragmento; si el proveedor no lo admite, se usa un único fragmento hasta el límite permitido.
   - Groq no ofrece diarización: con Groq, la transcripción sigue en Groq y el resultado es `diarization: "none"`, salvo que el usuario elija OpenAI para diarizar.
3. **Fase 2, navegador**: segmentación `pyannote-segmentation-3.0` en ONNX con transformers.js, seguida de embeddings de hablante y clustering aglomerativo para que las etiquetas sean consistentes entre ventanas. Opcional y detrás de un ajuste, por su coste en dispositivos sin WebGPU.
4. Opciones por trabajo en la subida: `diarize` (sí/no) y `num_speakers` o `min/max_speakers` cuando el proveedor lo admita.
5. Modelo de datos (ver punto 14): `speaker_id` estable (`S1`, `S2`…) en cada segmento y un mapa `speakers: {S1: {name, color}}` en el registro.

**Alternativas descartadas**: pyannote en el backend (contradice la política de cero inferencia local) y la asignación de hablantes por LLM solo a partir del texto (poco fiable, cuesta tokens y es difícil de verificar).

**Aceptación**: con OpenAI, una grabación de prueba de 3 personas da 3 hablantes con un error de atribución inferior al 15 % de los segmentos, medido a mano sobre 10 minutos. Sin diarización, nunca aparecen hablantes inventados. El resumen solo lista como participantes a los hablantes con nombre asignado.

**Archivos**: `features/transcription/diarization.py` (rehecho como proveedores), `whisper_cloud.py`, `service.py`, `schemas/transcription.py`, `components/UploadArea.tsx`, `hooks/useTranscriptionPipeline.ts`, `workers/transcription.worker.ts`.

### 10. Calidad de la transcripción en la nube

**Evidencia**
- `whisper_cloud.py:16-17`: `provider` vale `"groq"` por defecto y `service.py:421` no lo pasa. Con claves de Groq y OpenAI, la configuración `transcription_provider=openai` se ignora (`_resolve_credentials` usa `self.provider` antes que la configuración, `:23`).
- `:41, :46`: un modelo configurado que no contenga "whisper" (por ejemplo `gpt-4o-transcribe`) se sustituye en silencio.
- No hay reintentos ante 429 o 5xx, ni se respeta `retry-after`.
- No se usan las métricas que devuelve `verbose_json` (`no_speech_prob`, `avg_logprob`, `compression_ratio`). En español, Whisper suele alucinar en silencios con frases como "Subtítulos realizados por la comunidad de Amara.org" o repeticiones en bucle, y esas frases llegan al resumen.
- No se pasa `prompt` con vocabulario del dominio (nombres de productos, siglas, personas). `temperature` no se fija.
- `service.py:438`: el resumen automático no recibe `user_id`, así que usa el proveedor por defecto y no el del usuario.

**Corrección propuesta**
1. El proveedor y el modelo se resuelven una vez con `resolve_transcription_provider(user_id)`, que respeta la configuración y valida el modelo contra el catálogo de transcripción (`ai_models_catalog`, modo `audio_transcription`), sin filtros por subcadena.
2. Reintentos con backoff solo para errores transitorios (429, 5xx, timeout, conexión), con `retry-after`, por fragmento. Reutilizar la clasificación de `ai/providers/implementations.py` (`is_retryable_error`) o extraerla a un módulo común.
3. Filtro de alucinaciones tras la unión:
   - Descartar segmentos con `no_speech_prob > 0.6` y `avg_logprob < -1.0`.
   - Descartar segmentos con `compression_ratio > 2.4`.
   - Lista de frases conocidas (configurable).
   - Colapsar repeticiones consecutivas idénticas.
   Los segmentos descartados se registran en el log con su conteo.
4. Glosario: campo opcional `vocabulary` por usuario (en ajustes de voz) y por trabajo. Se envía como `prompt` junto con la cola del fragmento anterior, recortado a unos 200 tokens. `temperature=0`.
5. Idioma: si el usuario no lo indica, `es` por defecto y detección automática solo si se pide de forma explícita.
6. Pasar `user_id` al resumen.
7. `dictate` usa el mismo proveedor resuelto y los mismos reintentos.

**Aceptación**: con ambas claves configuradas y `transcription_provider=openai`, el log muestra OpenAI. Un audio con 2 min de silencio no produce frases de relleno. Un 429 simulado se reintenta y el trabajo termina. Pruebas unitarias del filtro de alucinaciones y de la resolución de proveedor.

**Archivos**: `whisper_cloud.py`, `service.py`, `api/transcription.py`, `ai/catalog.py`, `features/settings/components/voice/*` (glosario).

### 11. Calidad de la ruta en navegador

**Evidencia**
- `workers/transcription.worker.ts:163-238`: ventanas fijas de 30 s sin solapamiento, así que se cortan palabras en cada frontera. Si falta la marca de fin, se usa `inicio + 5`.
- `utils/audioExtractor.ts:46-92`: `parseWavPcmToFloat32` solo entiende PCM de 16 bits; otras profundidades se convierten en silencio sin aviso. Solo lee el primer canal.
- Archivos de más de 30 MB se suben completos al servidor para extraer el audio y se descarga el WAV de vuelta (`utils/audioExtractor.ts:118-179`). Eso anula la ventaja de procesar en local y duplica la transferencia.
- `providers/BrowserAsrProvider.ts:102`: el audio se copia al worker en lugar de transferirse. El worker se termina en cada trabajo, así que el modelo se vuelve a cargar cada vez.
- Las transcripciones hechas en el navegador no tienen el medio en el servidor, pero "Regenerar" siempre va al servidor (`hooks/useTranscriptionActions.ts:360`, `useTranscriptionPipeline.ts:458`) y probablemente responde 404.
- Al recargar la página se pierde el trabajo, sin aviso `beforeunload`.

**Corrección propuesta**
1. Usar el pipeline de transformers.js con `chunk_length_s: 30` y `stride_length_s: 5` y `return_timestamps: true`, o implementar el mismo solapamiento con deduplicación, en lugar de ventanas fijas.
2. Decodificar con `AudioContext.decodeAudioData` y remuestrear a 16 kHz mono con `OfflineAudioContext` para cualquier formato que el navegador soporte, mezclando todos los canales. El parser WAV queda como respaldo y admite 8/16/24/32 bits y float.
3. Más de 30 MB: probar primero `decodeAudioData` (los navegadores manejan bien cientos de MB de audio comprimido) y recurrir al servidor solo si falla, avisando de que el archivo se subirá.
4. Transferir el `ArrayBuffer` al worker (`postMessage(msg, [buffer])`). Mantener el worker vivo entre trabajos y ejecutar los trabajos en cola, uno a la vez.
5. "Regenerar" solo se ofrece si el registro tiene medio en el servidor; si no, ofrecer "Volver a transcribir subiendo el archivo".
6. `beforeunload` mientras haya un trabajo en el navegador en curso.

**Aceptación**: un audio de prueba con frases que cruzan los 30 s no pierde palabras. Un WAV de 24 bits y un MP3 estéreo se transcriben con normalidad. El segundo trabajo seguido no vuelve a descargar ni a inicializar el modelo. Pruebas con vitest del parser WAV y de la unión de ventanas.

**Archivos**: `workers/transcription.worker.ts`, `utils/audioExtractor.ts`, `providers/BrowserAsrProvider.ts`, `utils/clientTranscription.ts`, `hooks/useTranscriptionActions.ts`.

---

## P2: mejoras

### 12. Pausas y marcadores del discurso

**Evidencia**
- **Pausas en el audio**:
  - Ninguna de las dos rutas detecta silencios ni voz (no hay VAD).
  - En la nube se envía y factura el audio completo, incluidos los silencios.
  - En el navegador se decodifican las ventanas de 30 s aunque estén en silencio.
  - Los silencios largos son la causa principal de las frases de relleno que Whisper inventa (punto 10).
- **Pausas en el texto**:
  - El formateo de la transcripción corta el turno de un mismo hablante tras una pausa de más de 5 s (`summarizer.py:53-56`), con la misma lógica duplicada en el frontend (`hooks/useTranscriptionActions.ts:129-132`). Una persona que piensa antes de seguir aparece como varias intervenciones.
  - La heurística de diarización cambia de hablante ante pausas de más de 1,2 s (`diarization.py:91`; se elimina en el punto 9).
  - Whisper representa a veces las pausas como `...`, `…` o etiquetas como `[silencio]` o `[música]`, que llegan tal cual al texto.
- **Marcadores del discurso**:
  - No hay ningún tratamiento de muletillas ni de vacilaciones: "eh", "em", "mmm", "este…", "o sea", "digamos", "¿no?", "¿vale?", "tipo", repeticiones ("que que", "el el") y arranques fallidos ("lo- lo que").
  - Pasan sin cambios a la vista de la transcripción, al resumen, a los documentos generados (inventario, levantamiento) y a la base de conocimiento (`service.py:531-535`), donde ensucian la búsqueda.
  - Whisper imita el estilo del `prompt`: con un prompt que incluya muletillas, las conserva; sin prompt, las omite de forma irregular según el fragmento.

**Causa**
El pipeline guarda la salida del proveedor sin ninguna etapa de normalización, y la única noción de pausa es un umbral fijo en el formateo para el LLM.

**Corrección propuesta**

*A. Pausas en el audio (antes de transcribir)*
1. Detección de voz con `ffmpeg silencedetect`, en el mismo recorrido que la fragmentación del punto 3:
   - Umbral relativo al ruido de fondo, medido con `astats` sobre el propio audio (por ejemplo, ruido + 6 dB), en lugar de un valor fijo en dB.
   - Solo se recortan silencios de más de `TRANSCRIPTION_MIN_SILENCE_S` (2 s), dejando 0,3 s de margen a cada lado de la voz. Las pausas cortas forman parte del habla y no se tocan.
2. Se transcriben solo las regiones con voz, concatenadas, y se guarda un **mapa de tiempos** (`[(inicio_recortado, inicio_original, duración)]`). Las marcas de tiempo de los segmentos y de la diarización se convierten al tiempo original con ese mapa, para que la reproducción del audio siga sincronizada.
3. Navegador: VAD por energía (RMS por ventanas de 30 ms con umbral adaptativo) en el worker, que salta las ventanas sin voz. Silero VAD en ONNX queda como mejora posterior si la detección por energía falla con ruido de fondo.
4. Se registra cuánto silencio se recortó (`silence_trimmed_s`) y el ahorro estimado.

*B. Pausas en el texto*
1. Eliminar `...`, `…` y etiquetas no verbales (`[silencio]`, `[música]`, `(risas)`…) de los segmentos. Las etiquetas útiles (`[risas]`, `[inaudible]`) se pueden conservar como metadato del segmento en vez de como texto.
2. Unir segmentos consecutivos del mismo hablante separados por una pausa menor que `TRANSCRIPTION_TURN_GAP_S` (8 s) en un único turno. Se aplica en un solo sitio del backend (el turno resultante se guarda con sus segmentos de origen para conservar los tiempos) y se elimina la lógica duplicada del frontend.
3. Con diarización real (punto 9), el cambio de hablante lo decide la diarización, nunca la duración de una pausa.

*C. Marcadores del discurso (después de transcribir)*
1. Cada segmento guarda `text_raw` (literal, tal como lo devolvió el proveedor) y `text` (limpio). La versión literal nunca se modifica ni se pierde.
2. **Limpieza por reglas** (`features/transcription/cleanup.py`, siempre activa salvo `TRANSCRIPTION_CLEANUP=off`):
   - Vacilaciones puras, que nunca tienen otro significado: `e+h+`, `e+m+`, `m+h*`, `a+h+`, `u+m+`, `h+m+`, junto con las comas que las rodean.
   - Repeticiones inmediatas de una o dos palabras ("que que", "en el en el") y arranques fallidos marcados con guion ("lo- lo que").
   - Marcadores en posiciones inequívocas: al inicio del segmento seguidos de coma ("Bueno, …", "O sea, …", "Este, …") y coletillas al final (", ¿no?", ", ¿vale?", ", ¿sí?").
   - **No** se eliminan palabras con significado propio fuera de esas posiciones: "este documento", "bueno para el proyecto", "entonces el sistema", "pues sí".
   - Listas por idioma (`es`, `en`) y una lista adicional configurable por usuario en los ajustes de voz.
   - Después de limpiar: mayúscula inicial y puntuación coherentes; los segmentos que quedan vacíos se descartan del texto limpio (no del literal).
3. **Limpieza con LLM, opcional** (`TRANSCRIPTION_CLEANUP=llm`, decisión abierta 4):
   - Pasada con el modelo rápido por bloques de unos 40 segmentos, pidiendo una transcripción "limpia literal": quitar muletillas, repeticiones y arranques fallidos sin reformular, resumir ni corregir el contenido.
   - Salida estructurada por `id` de segmento, para conservar los tiempos.
   - Controles de seguridad: si un segmento limpio contiene palabras que no estaban en el original (salvo cambios de puntuación o mayúsculas) o se acorta más de un 40 %, se descarta y se usa la limpieza por reglas.
   - Errores del modelo o timeout: se usa la limpieza por reglas y el trabajo no falla.
4. Whisper: el `prompt` del punto 10 (glosario y cola del fragmento anterior) se envía siempre en estilo limpio, **sin muletillas**, para que el modelo no las reproduzca. La cola del fragmento anterior se toma de `text` limpio, no de `text_raw`.
5. Consumidores:
   - Resumen, documentos generados, exportaciones y base de conocimiento usan `text`.
   - La vista de transcripción muestra `text` por defecto, con un interruptor "Literal / Limpio".
   - La búsqueda dentro de la transcripción busca en las dos versiones.
   - Las ediciones manuales del usuario se guardan sobre `text`.
6. La ruta del navegador envía el resultado literal a `submit-client-transcription` y la limpieza por reglas se aplica en el backend al guardar, para tener una sola implementación. La limpieza con LLM solo se ejecuta en ese caso si el usuario la activó y tiene proveedor en la nube.

**Aceptación**
- **Pausas en el audio**:
  - Un audio de prueba con 5 min de silencio intercalado factura (duración enviada al proveedor) al menos 4,5 min menos que el original, sin perder ninguna frase.
  - Las marcas de tiempo coinciden con el audio original con un error inferior a 0,5 s al reproducir desde la vista.
  - No aparecen frases de relleno en los silencios recortados.
- **Pausas en el texto**: una intervención con una pausa de 6 s del mismo hablante aparece como un solo turno; no queda ningún `...` ni etiqueta no verbal en `text`.
- **Marcadores**:
  - Corpus de prueba en español con al menos 50 frases reales: se eliminan las vacilaciones y las coletillas, y se conservan todos los usos con significado ("este documento", "está bueno", "entonces el sistema").
  - `text_raw` es idéntico a la salida del proveedor.
  - Con la limpieza LLM forzada a inventar palabras (prueba con modelo falso), el control de seguridad la descarta.
- Pruebas unitarias de `cleanup.py`, del mapa de tiempos y de la unión de turnos.

**Archivos**: `features/transcription/cleanup.py` (nuevo), `features/transcription/chunking.py`, `ffmpeg_utils.py`, `service.py`, `summarizer.py`, `schemas/transcription.py` (`text_raw`), `api/transcription.py`, `workers/transcription.worker.ts`, `hooks/useTranscriptionActions.ts`, `components/SegmentList.tsx`, `features/settings/components/voice/*` (lista de muletillas).

### 13. Resumen acoplado y con pérdida de contenido

**Evidencia**
- `service.py:437-442`: el resumen automático se genera antes de guardar la transcripción. Si tarda, el usuario no ve el texto, y si falla se registra como `summary=None` sin indicarlo.
- `summarizer.py:86-140`: `condense_transcript_lines` conserva el 30 % inicial, el 30 % final y una muestra del centro. En una reunión larga se pierden las decisiones intermedias.
- `summarizer.py:296`: `max_tokens=2000` fijo.
- En el navegador, el resumen se genera dos veces con código casi idéntico (`utils/clientTranscription.ts:56` y `hooks/useTranscriptionActions.ts:393-440`).

**Corrección propuesta**
1. Guardar y marcar `complete` la transcripción en cuanto termina la diarización. El resumen pasa a ser una etapa posterior (`summary_status: pending | running | done | failed`) con su propio evento SSE, y su fallo no afecta a la transcripción.
2. Sustituir la condensación por cabeza y cola por el map-reduce de `ai/map_reduce.py` (tier rápido para los fragmentos, principal para la reducción) cuando la transcripción supere el presupuesto de entrada. `max_tokens` sale de `ai/policies.py` (nueva entrada `transcript_summary`).
3. Una sola función de resumen en el navegador.

**Aceptación**: la transcripción es visible en cuanto termina la transcripción, sin esperar al resumen. En una reunión de 2 h, el resumen menciona decisiones tomadas a mitad de la reunión (comprobación manual con una grabación de referencia).

**Archivos**: `service.py`, `summarizer.py`, `ai/policies.py`, `api/transcription.py`, `utils/clientTranscription.ts`, `hooks/useTranscriptionActions.ts`.

### 14. Edición de hablantes limitada

**Evidencia**
- `components/SpeakerManager.tsx` solo permite renombrar. No se puede reasignar un segmento, dividirlo ni fusionar hablantes, salvo escribiendo dos veces el mismo nombre.
- `speakerMap` solo se reconstruye al cargar (`hooks/useTranscriptionActions.ts:268-273`), no tras renombrar (`:476-486`), así que el segundo renombrado envía claves antiguas. Cancelar no deshace las ediciones.
- El renombrado reescribe todos los segmentos y regenera `text` en el backend (`storage.py:554-579`).
- Los colores salen de un hash del nombre en 6 grupos (`:162-169`): hay colisiones y el color cambia al renombrar.
- Las marcas de "importante" se guardan por índice del array, solo en estado local, y se desplazan cuando llega el resultado final.

**Corrección propuesta**
1. Modelo de datos:
   - Cada segmento tiene un `id` estable y un `speaker_id`.
   - El registro tiene `speakers: {S1: {name, color_index}}`.
   - Renombrar actualiza solo el mapa. Fusionar reasigna el `speaker_id` de los segmentos y elimina la entrada.
   - Migración de los registros existentes: un `speaker_id` por cada nombre distinto.
2. API: `PATCH /transcription/{id}/speakers` (renombrar, fusionar), `PATCH /transcription/{id}/segments/{seg_id}` (cambiar hablante, editar texto) y `POST .../segments/{seg_id}/split`.
3. UI: menú por segmento ("Asignar a…", "Nuevo hablante", "Dividir aquí"), fusión desde SpeakerManager, color por `color_index` y marcas persistidas por `segment.id`.
4. El resumen y las exportaciones usan los nombres del mapa.

**Aceptación**: renombrar dos veces seguidas, fusionar y reasignar funcionan sin recargar y persisten. Los colores son estables tras renombrar. Pruebas de funcionalidad del backend para cada operación.

**Archivos**: `schemas/transcription.py`, `storage.py`, `api/transcription.py`, `components/SpeakerManager.tsx`, `components/SegmentList.tsx`, `hooks/useTranscriptionActions.ts`.

### 15. Estructura del backend

**Evidencia**
- `api/transcription.py:36-65`: ocho funciones que solo reenvían a `storage`, con imports intercalados entre definiciones.
- Código sin uso:
  - `ffmpeg_utils.compress_audio_opus` y `convert_to_format`.
  - `audio_analyzer.get_audio_properties`.
  - `storage.cleanup_old_files`, que además borraría las carpetas con más de 24 h, incluidas las transcripciones guardadas.
  - `SpeakerDiarization.rename_speakers`.
  - `WhisperCloudService.estimate_cost`.
  - `get_or_create_progress_queue` (solo para pruebas).
- `_validate_transcription_result` instancia otro `AudioAnalyzer` y vuelve a ejecutar ffprobe.
- `_enrich_record_metadata` inventa tamaños (`1.2 MB` fijo, `duración × 16000`).
- Mezcla de logs con f-strings y con `%s`.

**Corrección propuesta**
1. Dividir el pipeline en pasos pequeños con un contexto compartido (`JobContext`: ids, usuario, rutas, duración, proveedor, emisor de progreso): `analyze → extract → chunk → transcribe → merge → filter → diarize → persist → summarize`. El orquestador gestiona el progreso, la cancelación y los errores en un único sitio.
2. `storage.py` queda solo para el disco; la persistencia pasa por el repositorio (punto 4).
3. Eliminar el código muerto, salvo `estimate_cost`, que pasa a usarse en las métricas (punto 17). Tamaño real del medio o vacío, nunca inventado.
4. Nuevo `TRANSCRIPTION_MEDIA_TTL_DAYS` opcional para borrar solo los medios (no los registros) de transcripciones completadas antiguas.

**Aceptación**: `service.py` no supera unas 250 líneas, cada paso tiene su prueba unitaria y no queda código muerto (`vulture`, o revisión con `grep`).

**Archivos**: `features/transcription/*`, `api/transcription.py`.

### 16. Estructura del frontend

**Evidencia**
- **Estado de trabajos en dos sitios**:
  - `activeJobs` en `TranscriptionContext` y `jobsMap` en `BackgroundJobContext`, sincronizados con unas nueve llamadas casi idénticas a `addOrUpdateJob` (`useTranscriptionPipeline.ts:82, 124, 160, 196, 258, 317, 441`, entre otras).
  - Dos `cancelledJobsRef` distintos.
  - Los trabajos terminados nunca salen de `activeJobs`.
  - Los trabajos del navegador se identifican por `model_info === 'Whisper Web (Client)'`, pero el worker sobrescribe ese valor.
- **Archivos sobredimensionados**:
  - `useTranscriptionActions.ts` (708 líneas) mezcla utilidades, resumen, exportación y hablantes.
  - `useTranscriptionPipeline.ts` (483) tiene tres funciones `execute*` casi duplicadas y recibe 22 props, incluidas referencias que pertenecen al gestor de streams.
- **Código muerto**:
  - `useTranscriptionProgress` y `ActiveTranscriptionItem`.
  - `retranscribe`, `pickLocalFile` e `inspectFile` de la API.
  - La rama de ruta local (`executeServerAudioPath`).
  - `showProgressModal`.
- `any` en el pipeline, el gestor de streams, el contexto y la página. `addOrUpdateJob` está tipado como `any`.
- El valor del contexto no está memorizado, así que cada tick del SSE vuelve a renderizar todos los consumidores.
- Hay cuatro formateadores de tiempo distintos.

**Corrección propuesta**
1. Un único almacén de trabajos (reducer en `TranscriptionContext`, con `kind: 'server' | 'browser'` explícito). `BackgroundJobContext` solo lo lee para el widget flotante, mediante un adaptador, sin duplicar el estado.
2. Dividir los hooks:
   - `useJobStore` y `useServerJob` (subida y SSE).
   - `useBrowserJob` (worker).
   - `useSpeakers`, `useSummary` y `useExports`.
   - Utilidades puras en `utils/`.
3. Eliminar el código muerto, los `any` y los formateadores duplicados (un solo `utils/time.ts`). Memorizar el valor del contexto.
4. La Studio muestra el estado real: fallido con su error, cargando, sin diálogos. Hoy muestra "Completado" para un fallo (`components/TranscriptionStudio.tsx:101-111`). Los fallos del servidor también se muestran como toast.

**Aceptación**: `npm run typecheck` y `npm run lint` sin `any` en la carpeta; ningún hook supera unas 250 líneas; un SSE tick no vuelve a renderizar la lista de transcripciones (React Profiler).

**Archivos**: `context/TranscriptionContext.tsx`, `context/BackgroundJobContext.tsx`, `hooks/*`, `components/TranscriptionStudio.tsx`, `pages/TranscripcionesPage.tsx`.

### 17. Pruebas, métricas y documentación

**Evidencia**
- `backend/tests/features/test_transcription_feature.py` cubre formatos, ffprobe, subida, SSE básico y el envío del cliente. No hay pruebas de fallo del proveedor, cancelación, propiedad, fragmentación ni progreso.
- `__tests__/transcriptionFeature.test.ts` solo cubre slugs, almacenamiento, codificación WAV y condensación.
- No hay registro por trabajo de proveedor, duración, fragmentos, reintentos, tiempos por etapa ni coste.
- `docs/TRANSCRIPTION_PROCESS.md` describe endpoints eliminados o inaccesibles y no menciona progreso, cancelación ni diarización.

**Corrección propuesta**
1. Backend:
   - Proveedor falso (`httpx.MockTransport`) con éxito, 429, 500, timeout y respuesta vacía.
   - Pruebas de fallo → `failed`, cancelación en cada etapa, reanudación tras `interrupted`, propiedad entre dos usuarios, plan y unión de fragmentos, filtro de alucinaciones, contrato de progreso (monótono y con etapas) y operaciones de hablantes.
2. Frontend: pruebas del gestor de streams, el reducer de trabajos, la cancelación del proveedor del navegador, el parser WAV, la unión de ventanas, la ETA y los textos de etapa.
3. Métricas: una línea por trabajo en `USER_DATA_DIR/transcription/logs/AAAA-MM-DD.jsonl` con `provider`, `model`, `audio_s`, `chunks`, `retries`, `stage_ms`, `rtf` (tiempo de proceso / duración), `hallucinated_segments`, `silence_trimmed_s`, `fillers_removed`, `cleanup_mode`, `diarization`, `cost_estimate` y `error_code`. Endpoint de estadísticas con p50 y p95 por proveedor, siguiendo el patrón de `/api/ai/logs/stats`.
4. Reescribir `docs/TRANSCRIPTION_PROCESS.md`: rutas, contrato de etapas y eventos, variables de entorno, límites, diarización y procedimiento ante trabajos interrumpidos.

**Aceptación**: las nuevas pruebas pasan en CI; las métricas aparecen tras una transcripción real; la documentación coincide con los endpoints existentes.

---

## Orden de ejecución sugerido

| Fase | Puntos | Resultado |
|---|---|---|
| 1. Fiabilidad y seguridad | 1, 2, 4, 6 (servidor) | Ningún trabajo atascado; datos aislados por usuario; servidor sin bloqueos |
| 2. Pipeline nuevo | 3, 5, 7, 10, 12, 15 | Audios largos, reanudación, progreso real y transcripción más limpia, sin silencios ni muletillas |
| 3. Transporte y frontend | 6 (cliente), 8, 16, 11 | Estado coherente, reconexión, cancelación fiable y ruta local de calidad |
| 4. Hablantes y resumen | 9, 14, 13 | Diarización real o explícitamente ausente; edición completa; resumen sin pérdidas |
| 5. Cierre | 17 | Pruebas, métricas y documentación |

Las fases 1 y 2 cambian el contrato de progreso. Se recomienda mantener los campos actuales (`status`, `stage`, `progress`, `message`, `eta`) durante una versión, junto a los nuevos, para que las pestañas abiertas con el bundle anterior sigan funcionando (el mismo criterio que con SSE v1 en el chat).

## Variables de entorno nuevas

| Variable | Valor por defecto | Efecto |
|---|---|---|
| `TRANSCRIPTION_MAX_UPLOAD_MB` | `2048` | Tamaño máximo de subida (413 si se supera) |
| `TRANSCRIPTION_MAX_DURATION_S` | `14400` | Duración máxima admitida |
| `TRANSCRIPTION_CHUNK_S` | `600` | Duración objetivo de cada fragmento |
| `TRANSCRIPTION_CHUNK_CONCURRENCY` | `2` (Groq) / `4` | Fragmentos en paralelo |
| `TRANSCRIPTION_MAX_CONCURRENT_JOBS` | `2` | Trabajos simultáneos; el resto queda en cola |
| `TRANSCRIPTION_NUM_RETRIES` | `3` | Reintentos por fragmento ante errores transitorios |
| `TRANSCRIPTION_HALLUCINATION_FILTER` | `on` | Filtro de segmentos de relleno |
| `TRANSCRIPTION_TRIM_SILENCE` | `on` | Recorta silencios largos antes de transcribir (con mapa de tiempos) |
| `TRANSCRIPTION_MIN_SILENCE_S` | `2.0` | Duración mínima de un silencio para recortarlo |
| `TRANSCRIPTION_TURN_GAP_S` | `8` | Pausa máxima para unir segmentos del mismo hablante en un turno |
| `TRANSCRIPTION_CLEANUP` | `rules` | `off`, `rules` o `llm`: limpieza de muletillas y vacilaciones |
| `TRANSCRIPTION_DESKTOP_MODE` / `TRANSCRIPTION_LOCAL_ROOTS` | `false` / — | Solo si se conserva la vinculación de rutas locales |
| `TRANSCRIPTION_MEDIA_TTL_DAYS` | — | Borrado opcional de medios antiguos ya transcritos |
