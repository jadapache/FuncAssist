# Base de Conocimiento — SQLite FTS5 & Almacenamiento Compartido

Documentación técnica y operativa sobre la arquitectura de la Base de Conocimiento (Knowledge Base / RAG) basada en **SQLite FTS5**, soporte para carpetas compartidas de red (UNC), migración automática desde JSON y herramientas de recuperación/integridad.

---

## 📌 1. Resumen Ejecutivo

La Base de Conocimiento gestiona la ingestión, fragmentación (*chunking*), almacenamiento e indexación de documentos corporativos (PRDs, actas de reunión, especificaciones técnicas, políticas de QA, manuales) para el motor de **Generación Aumentada por Recuperación (RAG)** de la aplicación.

### Principales capacidades:
1. **Motor de búsqueda nativo SQLite FTS5**: Reemplaza la lectura en memoria de archivos JSON por una tabla virtual FTS5 indexada con algoritmo BM25 $O(\log n)$.
2. **Normalización de diacríticos en español**: Tokenizador `unicode61 remove_diacritics 1` que permite coincidencias insensibles a tildes (ej. buscar `reunion` encuentra `reunión`).
3. **Concurrencia segura con SQLite WAL**: Modo *Write-Ahead Logging* (`PRAGMA journal_mode=WAL`) que admite múltiples lectores concurrentes y un escritor sin bloqueos ni corrupción.
4. **Almacenamiento local o en red compartida**: Configurable mediante la propiedad `knowledge_base_path` para apuntar a rutas UNC (`\\servidor\qa-mgmt\knowledge`) o unidades montadas.
5. **Migración automática e idempotente**: Conversión transparente de esquemas legados `chunks.json` y `manifest.json` hacia `knowledge.db` al iniciar la aplicación.
6. **Herramientas de recuperación y diagnóstico**: Endpoints y UI para verificar integridad, reconstruir índices FTS5 y exportar copias de seguridad en JSON.

---

## 🗄️ 2. Estructura de Almacenamiento y Esquema

La base de conocimiento se estructura bajo un directorio configurable (`LOCAL_DIR/knowledge` por defecto o ruta de red personalizada):

```
knowledge/
├── knowledge.db              ← Base de datos SQLite (tablas documents, chunks FTS5, db_meta)
├── knowledge.db-wal          ← Log de escritura WAL (temporal)
├── knowledge.db-shm          ← Shared memory WAL (temporal)
├── documents/                ← Archivos crudos subidos ({doc_id}_{safe_filename})
├── manifest.json.migrated    ← Archivo legado conservado como respaldo
└── chunks.json.migrated      ← Archivo legado conservado como respaldo
```

### Esquema SQLite (`knowledge.db`)

```sql
-- 1. Registro de documentos
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,               -- UUID del documento
    filename    TEXT NOT NULL,                  -- Nombre original del archivo
    stored_as   TEXT NOT NULL,                  -- Nombre físico en documents/
    tags        TEXT NOT NULL DEFAULT '[]',     -- Array JSON serializado
    chunk_count INTEGER NOT NULL DEFAULT 0,     -- Cantidad de fragmentos generados
    char_count  INTEGER NOT NULL DEFAULT 0,     -- Caracteres totales de texto extraído
    uploaded_at TEXT NOT NULL                   -- Timestamp ISO8601 UTC
);

-- 2. Tabla virtual FTS5 para búsqueda de texto completo y BM25
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    chunk_id,                                   -- "{doc_id}:{chunk_index}"
    document_id,                                -- UUID del documento padre
    filename,                                   -- Nombre original para matching
    tags,                                       -- Etiquetas JSON
    chunk_index,                                -- Posición ordinal
    text,                                       -- Contenido textual indexado
    uploaded_at,                                -- Timestamp ISO8601
    tokenize="unicode61 remove_diacritics 1"    -- Normalización de acentos y caracteres UTF-8
);

-- 3. Metadatos del sistema y control de migraciones
CREATE TABLE IF NOT EXISTS db_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO db_meta VALUES ('schema_version', '1');
```

---

## ⚙️ 3. Módulos y Arquitectura Backend

### 3.1 `backend/app/context/knowledge.py`
Módulo central de almacenamiento y búsqueda:
- **`get_knowledge_base_dir()`**: Resuelve dinámicamente la carpeta activa leyendo `knowledge_base_path` de `app.json` o usando `LOCAL_DIR / "knowledge"`.
- **`get_knowledge_db_path()`**: Devuelve la ruta absoluta a `knowledge.db`.
- **`get_knowledge_documents_dir()`**: Devuelve la carpeta de archivos físicos `documents/`.
- **`_get_connection()`**: Abre conexión SQLite configurando `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL` y `PRAGMA foreign_keys=ON` con `timeout=30`.
- **`extract_text(filename, raw)`**: Extrae texto limpio de archivos PDF (`pypdf`), DOCX (`python-docx`), HTML (`re.sub` + `unescape`) o archivos de texto plano / Markdown.
- **`chunk_text(text)`**: Divide el texto en fragmentos de `CHUNK_SIZE = 900` caracteres con `CHUNK_OVERLAP = 120` caracteres.
- **`ingest_document(filename, raw, tags)`**: Guarda el binario en `documents/`, extrae el texto, genera chunks y los almacena en `documents` y `chunks` (FTS5).
- **`delete_document(document_id)`**: Elimina atómicamente los fragmentos FTS5, el registro documental y el archivo físico en disco.
- **`list_documents()`**: Retorna la lista de documentos ordenados por fecha de subida descendente.
- **`load_chunks()`**: Carga todos los fragmentos para inspección o respaldo.
- **`get_chunks_for_documents(document_ids, max_chunks)`**: Obtiene fragmentos filtrados por IDs específicos de documentos.
- **`search_chunks_fts(query, top_k, tags)`**: Ejecuta consulta `MATCH` en FTS5, sanitizando caracteres especiales, ordenando por `bm25(chunks)` y aplicando filtros opcionales de etiquetas.

### 3.2 `backend/app/context/retrieval.py`
Orquestador de recuperación de fragmentos:
- **`search_knowledge(query, top_k, tags)`**:
  1. Intenta primero la búsqueda rápida con **SQLite FTS5**.
  2. Si la consulta es vacía o FTS5 no retorna resultados por particularidades sintácticas, recurre al motor BM25 en memoria de respaldo (`rank_bm25`).

### 3.3 `backend/app/context/knowledge_migration.py`
Módulo de migración y resiliencia:
- **`migrate_json_to_sqlite_if_needed()`**: Verifica la existencia de `manifest.json`/`chunks.json` y la ausencia de la marca `'json_migration_done'` en `db_meta`. Inserta los datos existentes en SQLite y renombra los archivos a `.json.migrated`.
- **`export_to_json(output_dir)`**: Genera copias de respaldo legibles `manifest.export.json` y `chunks.export.json`.
- **`rebuild_fts_index()`**: Ejecuta `INSERT INTO chunks(chunks) VALUES('rebuild')` para reparar o regenerar el índice invertido.
- **`verify_integrity()`**: Ejecuta `PRAGMA integrity_check`, FTS5 `integrity-check` y comprueba la concordancia de conteos entre `documents` y `chunks`.

### 3.4 `backend/app/main.py`
Ejecución en el ciclo de vida (*lifespan*):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    ...
    ensure_local_dirs()
    migrate_paths_if_needed()
    from app.context.knowledge_migration import migrate_json_to_sqlite_if_needed
    migrate_json_to_sqlite_if_needed()
    ensure_knowledge_dirs()
    ...
```

---

## 🌐 4. Endpoints REST API

Prefijo: `/api/knowledge`

| Método | Ruta | Descripción | Payload / Parámetros | Respuesta |
|---|---|---|---|---|
| `GET` | `/documents` | Listar todos los documentos | Ninguno | `{"documents": [...]}` |
| `POST` | `/documents` | Subir e indexar un documento | `file: UploadFile`, `tags: str` | `{"document": {...}}` |
| `POST` | `/documents/batch` | Subida por lotes | `files: list[UploadFile]`, `tags: str` | `{"documents": [...], "errors": [...]}` |
| `DELETE` | `/documents/{id}` | Eliminar documento y fragmentos | Path param `id` | `{"ok": true}` |
| `POST` | `/retrieve` | Recuperar contexto RAG relevante | `{"query": "...", "sources": ["knowledge"], "top_k": 8}` | Objeto `ContextBundle` |
| `GET` | `/path` | Consultar estado de la ruta de almacenamiento | Ninguno | `{"configured_path": "...", "resolved_path": "...", "is_custom": bool, "is_accessible": bool}` |
| `PUT` | `/path` | Configurar ruta local o carpeta de red | `{"path": "\\\\servidor\\qa-mgmt\\knowledge"}` | `{"ok": true, "configured_path": "...", "resolved_path": "..."}` |
| `GET` | `/admin/integrity` | Verificar integridad de SQLite y FTS5 | Ninguno | `{"ok": true, "details": [...], "db_path": "..."}` |
| `POST` | `/admin/rebuild-index` | Reconstruir el índice invertido FTS5 | Ninguno | `{"ok": true, "chunks_reindexed": int}` |
| `POST` | `/admin/export-json` | Exportar respaldo JSON de emergencia | Ninguno | `{"ok": true, "manifest_path": "...", "chunks_path": "..."}` |

---

## 💻 5. Frontend e Interfaz de Usuario

### 5.1 Configuración (`frontend/src/components/settings/KnowledgeBaseSection.tsx`)
Accesible desde **Configuración del Sistema** → Pestaña **Base de Conocimiento**:
- **Indicador de estado**: Muestra si el almacén está en modo *Almacenamiento Local* o *Carpeta de Red Conectada*, junto con el indicador de accesibilidad.
- **Selector de ruta**: Entrada para rutas UNC o rutas locales absolutas con botón de guardado y botón *Restaurar Local*.
- **Ruta física activa**: Muestra la ruta física exacta que está utilizando el motor SQLite.
- **Herramientas de diagnóstico**:
  - *Verificar Integridad*: Ejecuta pruebas de consistencia y muestra los resultados detallados en pantalla.
  - *Reconstruir Índice FTS5*: Reconstruye la estructura del índice de búsqueda.
  - *Exportar Respaldo JSON*: Genera archivos `.export.json` en la carpeta activa.

### 5.2 Biblioteca de Documentos (`frontend/src/pages/conocimiento/KnowledgePage.tsx`)
- Acceso directo en el encabezado: Botón **Configurar Motor SQLite & Red** con redirección a `/settings?tab=knowledge`.
- Soporte para subida de múltiples formatos y visualización de fragmentos indexados.

---

## 🧪 6. Pruebas Automatizadas

El archivo de pruebas [test_knowledge_sqlite_fts5.py](file:///c:/Dev/QA_MGMT/backend/tests/unit/test_knowledge_sqlite_fts5.py) valida:

1. **`test_ingest_and_list_documents`**: Ingestión y listado de documentos y fragmentos en SQLite.
2. **`test_fts5_search_and_spanish_diacritics`**: Búsqueda insensible a tildes (ej. `reunion` encuentra `reunión`).
3. **`test_search_knowledge_with_tags_and_fts5`**: Filtrado conjunto por texto y etiquetas.
4. **`test_delete_document`**: Eliminación completa en base de datos y sistema de archivos.
5. **`test_migration_json_to_sqlite`**: Migración desde archivos legados `chunks.json` y `manifest.json`, renombrado a `.migrated` e idempotencia.
6. **`test_integrity_and_rebuild_and_export`**: Verificación de integridad, reconstrucción FTS5 y exportación JSON.
7. **`test_api_knowledge_endpoints`**: Validación de todos los endpoints REST con `TestClient`.

Para ejecutar las pruebas:
```bash
uv run pytest tests/unit/test_knowledge_sqlite_fts5.py -v
```

---

## 📋 7. Guía de Operación y Recuperación

| Escenario | Acción recomendada |
|---|---|
| **Primera instalación o base de datos ausente** | `ensure_knowledge_dirs()` crea automáticamente `knowledge.db` con el esquema FTS5 en el arranque. |
| **Migración desde versión anterior con archivos JSON** | Ocurre automáticamente al iniciar el servidor. Los archivos anteriores se conservan como `*.migrated`. |
| **Mover a carpeta de red compartida** | Ir a *Configuración* → *Base de Conocimiento*, ingresar la ruta UNC (ej. `\\servidor\qa-mgmt\knowledge`), copiar la carpeta `documents/` y `knowledge.db` si se desea migrar contenido previo. |
| **Red no disponible temporalmente** | El sistema muestra estado de *No accesible*. Al restablecerse la conexión de red, la base de datos se reanuda de inmediato sin requerir reinicio del servidor. |
| **Índice de búsqueda desincronizado** | Ir a *Configuración* → *Base de Conocimiento* y hacer clic en **Reconstruir Índice FTS5** (o `POST /api/knowledge/admin/rebuild-index`). |
| **Verificación periódica** | Hacer clic en **Verificar Integridad** (o `GET /api/knowledge/admin/integrity`). |
| **Generar copia de seguridad** | Hacer clic en **Exportar Respaldo JSON** (o `POST /api/knowledge/admin/export-json`). |
