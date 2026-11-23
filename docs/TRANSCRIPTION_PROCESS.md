# Transcripción: arquitectura, contrato y operación

Referencia de `backend/app/features/transcription/**`, `backend/app/api/transcription*.py` y `frontend/src/features/transcription/**`. El plan que originó este diseño está en `docs/transcription-improvement-plan.md`.

## 1. Rutas

| Ruta | Cuándo | Dónde se ejecuta |
|---|---|---|
| **Nube** | `transcription_provider` es `groq`, `openai` o `cloud` | El navegador sube el archivo; el backend extrae el audio, recorta silencios, fragmenta, transcribe con el proveedor, limpia, diariza y guarda. |
| **Navegador** | Cualquier otro proveedor (`browser_asr`) | Whisper ONNX en un Web Worker (WebGPU o WASM) y, si se pide, identificación de interlocutores en el mismo worker (§2.1). El resultado literal se envía a `submit-client-transcription` y el backend aplica la limpieza por reglas al guardar. |

El backend no ejecuta inferencia local (ni Whisper ni pyannote).

## 2. Pipeline en la nube

```
analyze → preprocess (extraer audio, medir ruido, detectar silencios) → plan de fragmentos
       → transcribir fragmentos (concurrencia, reintentos, prompt) → unir y remapear tiempos
       → filtro de alucinaciones → limpieza (reglas / LLM) → diarización (si aplica) → guardar
       → resumen (después, no bloquea)
```

- **Silencios**: `ffmpeg silencedetect` con umbral relativo al ruido de fondo (`astats`, ruido + 6 dB, entre −50 y −25 dB). Solo se recortan silencios de más de `TRANSCRIPTION_MIN_SILENCE_S`, dejando 0,3 s de margen. Se transcriben las regiones con voz concatenadas y un **mapa de tiempos** devuelve cada marca al tiempo del audio original.
- **Fragmentos**: unos `TRANSCRIPTION_CHUNK_S` segundos de audio con voz, cortados en el límite de una región de voz cuando es posible. Cada fragmento se exporta a MP3 mono de 16 kHz y 48 kbps y se guarda en `transcriptions/<id>/chunks/` junto a su resultado (`chunk_NNN.json`). Un reintento solo pide los fragmentos sin resultado.
- **Prompt** (solo Whisper): glosario del usuario o del trabajo, más la cola **limpia** del fragmento anterior, recortado a unos 200 tokens y sin muletillas.
- **Diarización con OpenAI** (`gpt-4o-transcribe-diarize`, `response_format=diarized_json`, `chunking_strategy=auto`): el modelo transcribe y diariza a la vez. El primer fragmento se procesa solo. Después se extraen hasta 4 muestras de 2-10 s (una por hablante) y se envían como `known_speaker_names[]` / `known_speaker_references[]` en el resto de fragmentos, para mantener las mismas etiquetas. Este modelo no admite `prompt`, así que el glosario no se aplica en ese modo.
- **Sin diarización** (Groq o diarización desactivada): todos los segmentos son del hablante `S1` y `diarization = "none"`. No se inventan hablantes.

### 2.1. Diarización en el navegador

Opcional, por trabajo (casilla "Identificar interlocutores" al subir; su valor inicial es el ajuste `transcription_browser_diarization`). El audio no sale del equipo.

1. Se ejecuta tras Whisper, sobre el mismo audio sin silencios, en ventanas de 10 s.
2. `onnx-community/pyannote-segmentation-3.0` (`AutoModelForAudioFrameClassification` + `post_process_speaker_diarization`) da los turnos locales de cada ventana. Las clases 1-3 son un solo hablante; 0 (silencio) y 4-6 (solapamientos) no se usan para identificar voces.
3. Para cada hablante local con al menos 1 s de voz en la ventana, `onnx-community/wespeaker-voxceleb-resnet34-LM` calcula un vector de voz, que se normaliza.
4. Los vectores de todas las ventanas se agrupan con clustering aglomerativo de enlace medio sobre distancia coseno: umbral 0,6, máximo 8 hablantes, o exactamente el número indicado al subir.
5. Cada segmento de Whisper toma el hablante con más solapamiento; si no solapa con ninguno, el turno más cercano a menos de 2 s; si no, el del segmento anterior. Los ids se asignan por orden de aparición (`S1`, `S2`…).

Los dos modelos (unos 30 MB) se descargan la primera vez, en WASM y fp32, y quedan en caché del navegador. Si fallan la descarga o la inferencia, la transcripción se guarda igualmente con un único hablante y se muestra un aviso. El registro queda con `diarization = "browser"`. Código: `workers/diarizer.ts` (modelos) y `utils/speakerDiarization.ts` (ventanas, clustering y asignación, con pruebas).

## 3. Etapas y progreso

| Etapa (`stage`) | Tramo de `progress` | Progreso dentro de la etapa |
|---|---|---|
| `uploading` | 0-10 | bytes enviados (solo cliente) |
| `queued` | 10 | posición en cola (`queue_position`) |
| `preprocessing` | 10-20 | `ffmpeg -progress` sobre la duración |
| `transcribing` | 20-80 | segundos de audio de los fragmentos completados / total |
| `cleaning` | 80-85 | segmentos procesados |
| `diarizing` | 85-95 | inicio/fin |
| `saving` | 95-99 | — |
| `complete` | 100 | terminal; la transcripción ya se puede ver |
| `failed` / `cancelled` / `interrupted` | — | terminal |

`progress` nunca disminuye. `eta_seconds` se calcula con la velocidad medida (segundos de audio procesados por segundo) cuando ya hay al menos un fragmento terminado; antes vale `null`.

El resumen se genera después de `complete`, con su propio estado `summary_status`: `pending`, `running`, `done`, `failed` o `skipped`.

### Objeto de progreso

```json
{
  "id": "…", "media_id": "…", "title": "…",
  "status": "transcribing",           // igual que stage (compatibilidad)
  "stage": "transcribing",
  "stage_progress": 0.42,             // 0..1 dentro de la etapa
  "progress": 45,                     // 0..100 global, monótono
  "message": "Transcribiendo fragmento 3 de 7…",
  "eta": "~4 min 10 s",               // texto (compatibilidad)
  "eta_seconds": 250,
  "chunks_done": 2, "chunks_total": 7,
  "queue_position": null,
  "error": null, "error_code": null, "retryable": false,
  "summary_status": "pending",
  "model_info": "Groq Whisper (whisper-large-v3)",
  "seq": 17,
  "timestamp": "2026-11-21T10:00:00+00:00",
  "live_segments": []                 // ya no se usa; se mantiene vacío
}
```

### Códigos de error (`error_code`)

`file_too_large`, `too_long`, `unsupported_format`, `corrupt_media`, `no_credentials`, `auth_error`, `rate_limit`, `timeout`, `provider_unavailable`, `bad_request`, `empty_result`, `cancelled`, `interrupted`, `internal`. `retryable` indica si tiene sentido ofrecer "Reintentar".

## 4. API (`/api/transcription`)

Todos los endpoints por id comprueban que la transcripción sea del usuario (404 si no lo es). No hay excepción para administradores: cada usuario ve solo las suyas. Los registros antiguos sin `user_id` no los ve nadie hasta asignarlos (§9). `GET /stats` también se limita a los trabajos del propio usuario.

| Método y ruta | Cuerpo | Respuesta |
|---|---|---|
| `POST /upload` | multipart `file`, `title`, `description`, `transcription_id?` | `{ok, media_id, transcription_id, size, entry}`. 413 si supera `TRANSCRIPTION_MAX_UPLOAD_MB`. |
| `POST /transcribe/{media_id}` | `{transcription_id?, language?, diarize?, num_speakers?, vocabulary?, cleanup?}` (`enable_diarization` se acepta como alias de `diarize`) | `{ok, status: "queued", transcription_id, media_id}` |
| `POST /retry/{id}` | — | igual que `transcribe`; reanuda desde los fragmentos ya hechos |
| `POST /cancel/{id}` | — | `{ok}`; el trabajo queda en `cancelled` (no se borra) |
| `GET /jobs/active` | — | `{jobs: [Progreso]}` del usuario, no terminales |
| `GET /status/{id}` | — | Progreso |
| `GET /progress-stream/{id}?protocol=v2` | — | SSE (ver abajo) |
| `GET /result/{id}` | — | Transcripción |
| `GET /list` | — | `{transcriptions: [...]}` del usuario |
| `DELETE /{id}` | — | `{ok}` |
| `POST /submit-client-transcription` | `{id, title, description?, language, duration_seconds, text, segments, generate_summary_now, diarization?}`. Con `diarization: "browser"` se respetan los `speaker_id` de los segmentos; si no, todo es `S1`. | `{ok, transcription, summary}` |
| `POST /generate-summary/{id}` | `{feature?, rubric_id?}` | `{ok, summary, transcription}` |
| `PUT /summary/{id}` | `{summary}` | `{ok, transcription}` |
| `PATCH /{id}/speakers` | `{rename?: {S1: "Ana"}, merge?: [{from: "S2", into: "S1"}]}` | `{ok, transcription}` |
| `PUT /speakers/{id}` | `{speaker_map: {"nombre actual": "nombre nuevo"}}` (compatibilidad) | `{ok, transcription}` |
| `PATCH /{id}/segments/{segment_id}` | `{speaker_id?, new_speaker_name?, text?, marked?}` | `{ok, transcription}` |
| `POST /{id}/segments/{segment_id}/split` | `{at: <posición de carácter en text>}` | `{ok, transcription}` |
| `POST /save-to-knowledge/{id}` | `{custom_tags}` | `{ok, document_id, message}` |
| `GET /available-models` | — | proveedores configurados |
| `GET /stats?limit=N` | — | métricas agregadas (§7) |

`pick-local-file`, `inspect-file` y `register-local-path` solo existen con `TRANSCRIPTION_DESKTOP_MODE=true` y aceptan rutas dentro de `TRANSCRIPTION_LOCAL_ROOTS`.

### SSE

Con `?protocol=v2`:

```
id: 17
event: progress
data: {objeto de progreso}

event: heartbeat
data: {}
```

- Al conectar se envía el último estado conocido. Con la cabecera `Last-Event-ID` también; el cliente descarta los eventos con un `seq` ya visto.
- El stream se cierra tras un estado terminal. Si el estado es `complete` y `summary_status` es `pending` o `running`, sigue abierto hasta que el resumen termina (cada cambio llega como otro evento `progress`).
- El token puede ir en `Authorization: Bearer` (recomendado, con `fetch`) o en `?token=` (compatibilidad con `EventSource`).

Sin `protocol` (v1, para pestañas con el bundle anterior), los mismos objetos llegan como frames `data:` sin nombre de evento.

### Transcripción (`GET /result/{id}`)

```json
{
  "id": "…", "slug": "…", "metadata": {"title": "…", "description": "…", "size_bytes": 123},
  "language": "es", "duration_seconds": 3600.0, "created_at": "…",
  "status": "complete", "error": null, "error_code": null,
  "source": "cloud",                   // "cloud" | "browser"
  "has_media": true,                   // hay medio en el servidor: se puede regenerar
  "diarization": "openai",             // "openai" | "browser" | "manual" | "none" | "legacy"
  "speakers": {"S1": {"name": "Ana", "color_index": 0}, "S2": {"name": "Participante 2", "color_index": 1}},
  "segments": [
    {"id": "seg_0001", "start": 0.0, "end": 4.2, "speaker_id": "S1", "speaker": "Ana",
     "text": "Revisemos el inventario.", "text_raw": "Eh, bueno, revisemos el el inventario, ¿no?",
     "tags": [], "marked": false}
  ],
  "text": "…",                         // texto limpio completo
  "turn_gap_s": 8,
  "cleanup": {"mode": "rules", "fillers_removed": 42, "hallucinations_removed": 3},
  "silence_trimmed_s": 312.5,
  "summary": {…}, "summary_status": "done",
  "saved_to_knowledge": false, "document_id": null
}
```

- `speaker` es el nombre visible, derivado de `speakers[speaker_id].name`; se mantiene en cada segmento por compatibilidad.
- **Turnos**: los segmentos se guardan sin agrupar. La interfaz y el formateo para el LLM agrupan los segmentos consecutivos del mismo `speaker_id` separados por menos de `turn_gap_s` segundos (máximo unos 600 caracteres por turno). Una pausa nunca cambia de hablante.
- Las transcripciones anteriores a este cambio se normalizan al leerlas: `id` y `speaker_id` se derivan del orden y del nombre, y `text_raw` es igual a `text`.

## 5. Limpieza de texto

- `text_raw` guarda la salida literal del proveedor y no se modifica nunca. `text` es la versión limpia; las ediciones manuales se aplican sobre `text`.
- **Reglas** (`cleanup.py`, modo `rules`):
  - Se eliminan `...`, `…` y etiquetas no verbales (`[música]`, `(risas)`…); `[risas]` e `[inaudible]` pasan a `tags`.
  - Se eliminan las vacilaciones (`eh`, `em`, `mmm`, `ah`, `uh`, `hmm`…).
  - Se eliminan las repeticiones inmediatas de una o dos palabras y los arranques fallidos con guion.
  - Los marcadores solo se eliminan en posiciones inequívocas: al inicio seguidos de coma (`Bueno, …`, `O sea, …`, `Este, …`) y como coletilla final (`…, ¿no?`).
  - Las listas son por idioma, ampliables con `transcription_fillers` del usuario.
- **LLM** (modo `llm`): bloques de unos 40 segmentos al modelo rápido con salida JSON por `id`. Se descarta la versión del modelo y se usa la de reglas si añade palabras nuevas o recorta más de un 40 %. Si el modelo falla, se usan las reglas.
- **Filtro de alucinaciones**: se descartan los segmentos con `no_speech_prob > 0.6` y `avg_logprob < -1.0`, los de `compression_ratio > 2.4`, las frases conocidas ("Subtítulos realizados por…", "Gracias por ver el vídeo"…) y las repeticiones consecutivas idénticas.

## 6. Ajustes por usuario (`PUT /api/ai/settings`)

| Campo | Valores |
|---|---|
| `transcription_vocabulary` | texto, hasta 1000 caracteres: nombres, siglas y términos del dominio |
| `transcription_fillers` | lista de muletillas adicionales |
| `transcription_cleanup` | `off`, `rules` (por defecto) o `llm` |
| `transcription_diarization` | `auto` (OpenAI si hay clave) u `off` |
| `transcription_browser_diarization` | `on` u `off` (por defecto): valor inicial de "Identificar interlocutores" en las transcripciones del navegador. `GET /available-models` lo expone como `browser_diarization` |

La limpieza con LLM usa el proveedor de redacción del usuario; si no tiene uno en la nube, se aplica `rules`.

## 7. Trabajos, cancelación y métricas

- El estado vive en la fila de `transcriptions` (`status`, `progress_json`, `error_code`, `started_at`, `finished_at`, `user_id`). La memoria del proceso solo se usa como caché para el SSE. Se asume **un solo worker de uvicorn**: con varios, el pub/sub del SSE no se comparte entre procesos.
- Al arrancar, los trabajos en etapas no terminales pasan a `interrupted` con `retryable=true`.
- `TRANSCRIPTION_MAX_CONCURRENT_JOBS` trabajos a la vez; el resto queda en `queued`.
- **Cancelar** cancela la tarea, mata el ffmpeg en curso, cierra las peticiones HTTP y deja el registro en `cancelled`.
- **Métricas**: una línea por trabajo en `USER_DATA_DIR/transcription/logs/AAAA-MM-DD.jsonl` con `provider`, `model`, `audio_s`, `chunks`, `retries`, `stage_ms`, `rtf`, `hallucinations_removed`, `silence_trimmed_s`, `fillers_removed`, `cleanup_mode`, `diarization`, `cost_estimate` y `error_code`. `GET /api/transcription/stats` devuelve los agregados.

## 8. Variables de entorno

| Variable | Valor por defecto | Efecto |
|---|---|---|
| `TRANSCRIPTION_MAX_UPLOAD_MB` | `2048` | Tamaño máximo de subida |
| `TRANSCRIPTION_MAX_DURATION_S` | `14400` | Duración máxima |
| `TRANSCRIPTION_CHUNK_S` | `600` | Duración objetivo por fragmento |
| `TRANSCRIPTION_CHUNK_CONCURRENCY` | `2` (Groq) / `4` | Fragmentos en paralelo |
| `TRANSCRIPTION_MAX_CONCURRENT_JOBS` | `2` | Trabajos simultáneos |
| `TRANSCRIPTION_NUM_RETRIES` | `3` | Reintentos por fragmento ante errores transitorios |
| `TRANSCRIPTION_TIMEOUT_S` | `300` | Timeout por petición al proveedor |
| `TRANSCRIPTION_HALLUCINATION_FILTER` | `on` | Filtro de alucinaciones |
| `TRANSCRIPTION_TRIM_SILENCE` | `on` | Recorte de silencios |
| `TRANSCRIPTION_MIN_SILENCE_S` | `2.0` | Silencio mínimo para recortar |
| `TRANSCRIPTION_TURN_GAP_S` | `8` | Pausa máxima dentro de un turno |
| `TRANSCRIPTION_CLEANUP` | `rules` | Limpieza por defecto si el usuario no la configura |
| `TRANSCRIPTION_DIARIZE_MODEL` | `gpt-4o-transcribe-diarize` | Modelo de diarización de OpenAI |
| `TRANSCRIPTION_DESKTOP_MODE` / `TRANSCRIPTION_LOCAL_ROOTS` | `false` / — | Vinculación de rutas locales (separadas por `;` o `,`) |
| `TRANSCRIPTION_MEDIA_TTL_DAYS` | — | Borrado de medios de transcripciones completadas más antiguas |

## 9. Operación

- **Trabajo interrumpido** (reinicio o despliegue): aparece como "Interrumpida"; "Reintentar" llama a `POST /retry/{id}` y reanuda desde los fragmentos guardados.
- **Rate limit de Groq**: baja `TRANSCRIPTION_CHUNK_CONCURRENCY` a 1.
- **Migración**: las columnas nuevas de `transcriptions` se añaden al arrancar (`app/core/transcription_migration.py`). Los registros existentes quedan con `user_id` nulo y no los ve nadie. `python -m scripts.assign_transcriptions_owner --user <id>` cuenta cuántos hay y, con `--apply`, los asigna a ese usuario.
