# Base de Conocimiento — PostgreSQL RAG & Soporte Vectorial

Documentación técnica y operativa sobre la arquitectura de la Base de Conocimiento (Knowledge Base / RAG) basada en **PostgreSQL**, indexación léxica de texto completo en español (`tsvector` + GIN), soporte semántico vectorial (`pgvector` + HNSW), variables de entorno y herramientas de diagnóstico.

---

## 📌 1. Resumen Ejecutivo

La Base de Conocimiento gestiona la ingestión, fragmentación (*chunking*), almacenamiento e indexación de documentos corporativos (PRDs, actas de reunión, especificaciones técnicas, políticas de QA, manuales) para el motor de **Generación Aumentada por Recuperación (RAG)** de la aplicación en servidor.

### Principales capacidades:
1. **Motor Relacional y Vectorial en Servidor (PostgreSQL)**: Reemplaza SQLite FTS5 por PostgreSQL, optimizado para concurrencia multi-usuario sin problemas de bloqueos ni sobrecarga de red compartida.
2. **Normalización y Full-Text Search en Español**: Indexación nativa con `to_tsvector('spanish', text)`, índice `GIN` y ranking con `ts_rank_cd` / `websearch_to_tsquery`. Coincidencias insensibles a tildes y variantes lematizadas (ej. buscar `reunion` encuentra `reunión`).
3. **Soporte Semántico Vectorial (`pgvector`)**: Columna `embedding vector(1536)` (o adaptable), índice `HNSW` con métrica de distancia coseno (`vector_cosine_ops`) y operador `<=>`.
4. **Búsqueda RAG Híbrida**: Capacidad de recuperar contexto por coincidencia textual directa, similitud semántica de alta dimensionalidad o combinación de ambas.
5. **Administración por Variables de Entorno**: Conexión y credenciales configuradas a nivel de servidor mediante `DATABASE_URL`.
6. **Migración Automática**: Detección y migración transparente de bases SQLite o respaldos JSON preexistentes hacia PostgreSQL en el arranque.
7. **Herramientas de Diagnóstico en UI**: Panel de estado en tiempo real, verificación de integridad, reindexación y exportación de respaldos JSON.

---

## 🗄️ 2. Esquema de Base de Datos en PostgreSQL

```sql
-- 1. Extensiones requeridas
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- 2. Registro documental
CREATE TABLE IF NOT EXISTS documents (
    id          VARCHAR(64) PRIMARY KEY,               -- UUID del documento
    filename    TEXT NOT NULL,                         -- Nombre original del archivo
    stored_as   TEXT NOT NULL,                         -- Nombre físico en el almacenamiento del servidor
    tags        JSONB NOT NULL DEFAULT '[]'::jsonb,    -- Etiquetas JSONB
    chunk_count INTEGER NOT NULL DEFAULT 0,            -- Cantidad de fragmentos generados
    char_count  INTEGER NOT NULL DEFAULT 0,            -- Total de caracteres de texto extraído
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP -- Timestamp con zona horaria
);

-- 3. Fragmentos (Chunks) con Full-Text Search y Soporte Vectorial
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id     VARCHAR(128) PRIMARY KEY,             -- "{document_id}:{chunk_index}"
    document_id  VARCHAR(64) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    filename     TEXT NOT NULL,
    tags         JSONB NOT NULL DEFAULT '[]'::jsonb,
    chunk_index  INTEGER NOT NULL DEFAULT 0,
    text         TEXT NOT NULL,
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('spanish', text)) STORED,
    embedding    vector(1536),                         -- Vector de embedding (pgvector)
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. Índices para aceleración de búsqueda RAG
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin(tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tags ON chunks USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);

-- 5. Control de metadatos y migraciones
CREATE TABLE IF NOT EXISTS db_meta (
    key   VARCHAR(64) PRIMARY KEY,
    value TEXT NOT NULL
);
```

---

## ⚙️ 3. Configuración y Variables de Entorno

En el servidor (Render, Railway, Docker, Kubernetes o VM), defina en su archivo `.env` o en las variables de entorno de la plataforma la cadena de conexión centralizada:

```bash
# Conexión PostgreSQL centralizada para toda la aplicación
DATABASE_URL=postgresql://usuario:contraseña@servidor-db.host:5432/qa_mgmt
```

### Ubicación de archivos físicos:
Los archivos crudos originales subidos (PDF, Word, etc.) se custodian en el directorio del servidor:
- **Ruta fija**: `USER_DATA_DIR / "knowledge" / "documents"` (o variable `DATA_DIR` / `LOCAL_DIR`).

---

## 🌐 4. Endpoints REST API

Prefijo: `/api/knowledge`

| Método | Ruta | Descripción | Payload / Parámetros | Respuesta |
|---|---|---|---|---|
| `GET` | `/documents` | Listar todos los documentos | Ninguno | `{"documents": [...]}` |
| `POST` | `/documents` | Subir e indexar un documento | `file: UploadFile`, `tags: str` | `{"document": {...}}` |
| `POST` | `/documents/batch` | Subida por lotes | `files: list[UploadFile]`, `tags: str` | `{"documents": [...], "errors": [...]}` |
| `DELETE` | `/documents/{id}` | Eliminar documento y fragmentos en cascada | Path param `id` | `{"ok": true}` |
| `POST` | `/retrieve` | Recuperar contexto RAG relevante | `{"query": "...", "sources": ["knowledge"], "top_k": 8}` | Objeto `ContextBundle` |
| `GET` | `/db-status` | Consultar estado del motor PostgreSQL y pgvector | Ninguno | `{"engine": "postgresql", "pgvector_enabled": bool, "connected": bool, ...}` |
| `GET` | `/path` | Endpoint compatible de estado de almacenamiento | Ninguno | Objeto `KnowledgePathResponse` |
| `GET` | `/admin/integrity` | Verificar integridad de la base de datos | Ninguno | `{"ok": true, "details": [...]}` |
| `POST` | `/admin/rebuild-index` | Reconstruir índices RAG (`REINDEX TABLE chunks`) | Ninguno | `{"ok": true, "chunks_reindexed": int}` |
| `POST` | `/admin/export-json` | Exportar respaldo JSON de emergencia | Ninguno | `{"ok": true, "manifest_path": "...", "chunks_path": "..."}` |

---

## 🧪 5. Pruebas Automatizadas

Para ejecutar las pruebas del motor PostgreSQL RAG:
```bash
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_knowledge_postgres.py -v
```
