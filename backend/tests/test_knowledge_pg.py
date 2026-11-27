"""Knowledge base against a real PostgreSQL with pgvector: the SQL is what these tests pin down."""

import os
import uuid
from urllib.parse import quote

import pytest

from app.context import knowledge, knowledge_migration

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is not set")

DIM = 1536


def _vector(*head):
  return [float(x) for x in head] + [0.0] * (DIM - len(head))


@pytest.fixture
def kn(tmp_path, monkeypatch):
  import psycopg

  base = os.environ["TEST_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
  schema = f"kn_{uuid.uuid4().hex[:10]}"
  with psycopg.connect(base, autocommit=True) as admin:
    admin.execute("CREATE EXTENSION IF NOT EXISTS vector")
    admin.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    admin.execute(f"CREATE SCHEMA {schema}")
  options = quote(f"-csearch_path={schema},public", safe="")
  monkeypatch.setenv("DATABASE_URL", f"{base}?options={options}")
  monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", tmp_path / "kb")
  monkeypatch.setattr(knowledge, "KNOWLEDGE_RAW_UPLOADS_DIR", tmp_path / "kb" / "documents")
  monkeypatch.setattr(knowledge_migration, "KNOWLEDGE_DIR", tmp_path / "kb")
  monkeypatch.setattr(knowledge, "_SCHEMA_INITIALIZED", False)
  monkeypatch.setattr(knowledge, "_PGVECTOR_AVAILABLE", None)
  yield knowledge
  with psycopg.connect(base, autocommit=True) as admin:
    admin.execute(f"DROP SCHEMA {schema} CASCADE")


def _ingest(kn, name, text, tags=None, embeddings=None):
  return kn.ingest_document(filename=name, raw=text.encode(), tags=tags, embeddings=embeddings)


# --- documents round trip -----------------------------------------------------

def test_ingest_list_load_and_delete_round_trip(kn):
  doc = _ingest(kn, "a.txt", "hola mundo", tags=["x"])
  assert doc["chunk_count"] == 1 and doc["char_count"] == 10 and doc["tags"] == ["x"]
  listed = kn.list_documents()
  assert [d["id"] for d in listed] == [doc["id"]]
  assert listed[0]["tags"] == ["x"] and listed[0]["stored_as"] == doc["stored_as"]
  chunk = kn.load_chunks()[0]
  assert chunk["id"] == f"{doc['id']}:0" and chunk["text"] == "hola mundo" and chunk["index"] == 0
  assert (kn.get_knowledge_documents_dir() / doc["stored_as"]).exists()
  assert kn.delete_document(doc["id"]) is True
  assert kn.list_documents() == [] and kn.load_chunks() == []
  assert not (kn.get_knowledge_documents_dir() / doc["stored_as"]).exists()
  assert kn.delete_document(doc["id"]) is False


def test_documents_are_listed_newest_first(kn):
  first = _ingest(kn, "a.txt", "uno")
  second = _ingest(kn, "b.txt", "dos")
  assert [d["id"] for d in kn.list_documents()] == [second["id"], first["id"]]


def test_chunks_of_several_documents_are_fetched_in_order_and_capped(kn):
  a = _ingest(kn, "a.txt", "alfa " * 400)
  b = _ingest(kn, "b.txt", "beta")
  assert kn.get_chunks_for_documents([]) == []
  chunks = kn.get_chunks_for_documents([a["id"], b["id"]])
  keys = [(c["document_id"], c["index"]) for c in chunks]
  assert keys == sorted(keys) and len(chunks) == a["chunk_count"] + 1
  assert {c["filename"] for c in chunks} == {"a.txt", "b.txt"}
  assert len(kn.get_chunks_for_documents([a["id"], b["id"]], max_chunks=2)) == 2
  assert [c["filename"] for c in kn.get_chunks_for_documents([b["id"]])] == ["b.txt"]


def test_failed_ingest_rolls_back_the_whole_document(kn):
  with pytest.raises(Exception):
    _ingest(kn, "a.txt", "hola", embeddings=[[1.0, 2.0]])
  assert kn.list_documents() == []


# --- full text search ---------------------------------------------------------

def test_fts_matches_ignoring_accents_and_ranks_by_relevance(kn):
  _ingest(kn, "a.txt", "La canción del pescador")
  _ingest(kn, "b.txt", "Receta de cocina sin relación")
  hits = kn.search_chunks_fts("cancion pescador")
  assert [h["filename"] for h in hits] == ["a.txt"]
  assert isinstance(hits[0]["score"], float) and hits[0]["score"] > 0
  assert set(hits[0]) == {"id", "document_id", "filename", "tags", "index", "text", "uploaded_at", "score"}


def test_fts_falls_back_to_a_plain_query_when_the_web_query_matches_nothing(kn):
  _ingest(kn, "a.txt", "perro gato")
  assert kn.search_chunks_fts("perro -gato") != []


def test_fts_without_matches_returns_nothing(kn):
  _ingest(kn, "a.txt", "perro gato")
  assert kn.search_chunks_fts("elefante") == []


def test_fts_filters_by_tag_case_insensitively_and_applies_top_k_after_filtering(kn):
  for i in range(3):
    _ingest(kn, f"n{i}.txt", "informe anual", tags=["otro"])
  _ingest(kn, "t1.txt", "informe anual", tags=["Legal"])
  _ingest(kn, "t2.txt", "informe anual", tags=["legal"])
  hits = kn.search_chunks_fts("informe", top_k=2, tags=["LEGAL"])
  assert sorted(h["filename"] for h in hits) == ["t1.txt", "t2.txt"]
  assert len(kn.search_chunks_fts("informe", top_k=3)) == 3


def test_fts_with_an_empty_query_lists_chunks_optionally_by_tag(kn):
  _ingest(kn, "a.txt", "uno", tags=["x"])
  _ingest(kn, "b.txt", "dos", tags=["y"])
  assert len(kn.search_chunks_fts("  ")) == 2
  assert len(kn.search_chunks_fts("", top_k=1)) == 1
  assert [c["filename"] for c in kn.search_chunks_fts("", tags=["Y"])] == ["b.txt"]
  assert "score" not in kn.search_chunks_fts("")[0]


def test_fts_returns_nothing_and_logs_when_the_query_fails(kn, caplog):
  _ingest(kn, "a.txt", "uno")
  with kn._db() as conn:
    conn.cursor().execute("DROP TABLE chunks")
  assert kn.search_chunks_fts("uno") == []
  assert any("PostgreSQL FTS error" in r.getMessage() for r in caplog.records)


# --- vector search ------------------------------------------------------------

def test_vector_search_orders_by_cosine_similarity(kn):
  text = "x" * 2000
  _ingest(kn, "near.txt", "cerca", embeddings=[_vector(1, 0)])
  _ingest(kn, "far.txt", "lejos", embeddings=[_vector(0, 1)])
  _ingest(kn, "none.txt", "sin vector")
  hits = kn.search_chunks_vector(_vector(1, 0.1))
  assert [h["filename"] for h in hits] == ["near.txt", "far.txt"]
  assert hits[0]["score"] > hits[1]["score"] and 0.9 < hits[0]["score"] <= 1.0
  assert len(kn.search_chunks_vector(_vector(1, 0.1), top_k=1)) == 1
  assert text  # keep the long literal used by the tag test below out of the way


def test_vector_search_filters_by_tag(kn):
  _ingest(kn, "a.txt", "uno", tags=["Legal"], embeddings=[_vector(1, 0)])
  _ingest(kn, "b.txt", "dos", tags=["otro"], embeddings=[_vector(1, 0.2)])
  hits = kn.search_chunks_vector(_vector(1, 0), tags=["legal"])
  assert [h["filename"] for h in hits] == ["a.txt"]


def test_vector_search_without_a_query_vector_returns_nothing(kn):
  assert kn.search_chunks_vector([]) == []


def test_vector_search_is_disabled_without_pgvector(kn, monkeypatch):
  _ingest(kn, "a.txt", "uno", embeddings=[_vector(1, 0)])
  monkeypatch.setattr(kn, "_PGVECTOR_AVAILABLE", False)
  assert kn.search_chunks_vector(_vector(1, 0)) == []


def test_vector_search_returns_nothing_and_logs_when_the_query_fails(kn, caplog):
  _ingest(kn, "a.txt", "uno", embeddings=[_vector(1, 0)])
  with kn._db() as conn:
    conn.cursor().execute("DROP TABLE chunks")
  assert kn.search_chunks_vector(_vector(1, 0)) == []
  assert any("Vector search query failed" in r.getMessage() for r in caplog.records)


# --- trigram search -----------------------------------------------------------

def test_trigram_search_finds_acronyms_and_ids_the_spanish_index_misses(kn):
  _ingest(kn, "a.txt", "El ticket ACME-4821 quedó pendiente")
  _ingest(kn, "b.txt", "Nada relacionado aquí")
  hits = kn.search_chunks_trigram("ACME-4821")
  assert [h["filename"] for h in hits] == ["a.txt"]
  assert 0 < hits[0]["score"] <= 1.0


def test_trigram_search_filters_by_tag_and_caps_results(kn):
  _ingest(kn, "a.txt", "ticket ACME-4821", tags=["Legal"])
  _ingest(kn, "b.txt", "ticket ACME-4821", tags=["otro"])
  assert [h["filename"] for h in kn.search_chunks_trigram("ACME-4821", tags=["legal"])] == ["a.txt"]
  assert len(kn.search_chunks_trigram("ACME-4821", top_k=1)) == 1


def test_trigram_search_ignores_blank_queries(kn):
  assert kn.search_chunks_trigram("   ") == []


def test_trigram_search_returns_nothing_and_logs_when_the_query_fails(kn, caplog):
  _ingest(kn, "a.txt", "uno")
  with kn._db() as conn:
    conn.cursor().execute("DROP TABLE chunks")
  assert kn.search_chunks_trigram("uno") == []
  assert any("Trigram search query failed" in r.getMessage() for r in caplog.records)


# --- status -------------------------------------------------------------------

def test_status_reports_counts_and_connection(kn):
  _ingest(kn, "a.txt", "uno dos")
  status = kn.get_db_status()
  assert status["connected"] is True and status["doc_count"] == 1 and status["chunk_count"] == 1
  assert status["pgvector_enabled"] is True and status["engine"] == "postgresql"
  assert status["database"] and status["host"]
  assert "error" not in status


def test_status_without_configuration_explains_why(kn, monkeypatch):
  monkeypatch.delenv("DATABASE_URL")
  status = kn.get_db_status()
  assert status["connected"] is False and "no está configurado" in status["error"]


def test_status_reports_a_failed_connection(kn, monkeypatch, caplog):
  monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:x@127.0.0.1:1/none")
  status = kn.get_db_status()
  assert status["connected"] is False and status["error"].startswith("Error al conectar")
  assert (status["host"], status["database"]) == ("127.0.0.1", "none")
  assert any("Error al consultar el estado" in r.getMessage() for r in caplog.records)


def test_documents_directory_is_created_with_its_parents(kn, monkeypatch, tmp_path):
  monkeypatch.setattr(kn, "KNOWLEDGE_RAW_UPLOADS_DIR", tmp_path / "kb" / "x" / "y")
  doc = _ingest(kn, "a.txt", "uno")
  assert (tmp_path / "kb" / "x" / "y" / doc["stored_as"]).exists()


# --- integrity and index ------------------------------------------------------

def test_integrity_detects_a_chunk_count_mismatch(kn):
  doc = _ingest(kn, "a.txt", "uno")
  assert knowledge_migration.verify_integrity()["ok"] is True
  with kn._db() as conn:
    conn.cursor().execute("UPDATE documents SET chunk_count = 5 WHERE id = %s", (doc["id"],))
  result = knowledge_migration.verify_integrity()
  assert result["ok"] is False and any("esperado 5, encontrado 1" in d for d in result["details"])


def test_rebuilding_the_index_counts_the_chunks(kn):
  _ingest(kn, "a.txt", "uno")
  assert knowledge_migration.rebuild_fts_index() == 1


# --- legacy JSON migration ----------------------------------------------------

def _write_legacy(kb_dir, manifest, chunks):
  import json

  kb_dir.mkdir(parents=True, exist_ok=True)
  if manifest is not None:
    (kb_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
  if chunks is not None:
    (kb_dir / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")


_MANIFEST = [{"id": "d1", "filename": "a.txt", "stored_as": "d1_a.txt", "tags": ["x"], "chunk_count": 2, "char_count": 9, "uploaded_at": "2024-01-01T00:00:00+00:00"}]
_CHUNKS = [
  {"id": "d1:0", "document_id": "d1", "filename": "a.txt", "index": 0, "text": "uno", "uploaded_at": "2024-01-01T00:00:00+00:00"},
  {"document_id": "d1", "text": "dos"},
]


def test_migration_moves_documents_and_chunks_and_retires_the_json_files(kn):
  kb_dir = kn.KNOWLEDGE_DIR
  _write_legacy(kb_dir, _MANIFEST, _CHUNKS)
  knowledge_migration.migrate_knowledge_if_needed()
  doc = kn.list_documents()[0]
  assert doc["id"] == "d1" and doc["tags"] == ["x"] and doc["chunk_count"] == 2
  chunks = kn.load_chunks()
  assert [(c["id"], c["text"], c["tags"], c["filename"]) for c in chunks] == [("d1:0", "uno", ["x"], "a.txt"), ("d1:1", "dos", ["x"], "a.txt")]
  assert not (kb_dir / "manifest.json").exists() and (kb_dir / "manifest.json.migrated").exists()
  assert (kb_dir / "chunks.json.migrated").exists()


def test_migration_runs_only_once(kn):
  kb_dir = kn.KNOWLEDGE_DIR
  _write_legacy(kb_dir, _MANIFEST, _CHUNKS)
  knowledge_migration.migrate_json_to_postgres_if_needed()
  _write_legacy(kb_dir, [{**_MANIFEST[0], "id": "d2"}], [])
  knowledge_migration.migrate_json_to_postgres_if_needed()
  assert [d["id"] for d in kn.list_documents()] == ["d1"]
  assert (kb_dir / "manifest.json").exists()


def test_migration_does_nothing_without_legacy_files(kn):
  knowledge_migration.migrate_json_to_postgres_if_needed()
  assert kn.list_documents() == []
  assert knowledge_migration.migrate_knowledge_if_needed() is None


def test_migration_is_skipped_when_postgres_is_not_configured(kn, monkeypatch):
  _write_legacy(kn.KNOWLEDGE_DIR, _MANIFEST, _CHUNKS)
  monkeypatch.delenv("DATABASE_URL")
  knowledge_migration.migrate_knowledge_if_needed()
  assert (kn.KNOWLEDGE_DIR / "manifest.json").exists()


def test_migration_of_empty_legacy_files_only_marks_it_done(kn):
  _write_legacy(kn.KNOWLEDGE_DIR, [], [])
  knowledge_migration.migrate_json_to_postgres_if_needed()
  with kn._db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT value FROM db_meta WHERE key = 'json_migration_done'")
    assert cur.fetchone()["value"] == "true"
  assert (kn.KNOWLEDGE_DIR / "manifest.json").exists()


def test_migration_logs_unreadable_files_and_keeps_going(kn, caplog):
  kb_dir = kn.KNOWLEDGE_DIR
  _write_legacy(kb_dir, None, _CHUNKS)
  (kb_dir / "manifest.json").write_text("{not json", encoding="utf-8")
  knowledge_migration.migrate_json_to_postgres_if_needed()
  messages = [r.getMessage() for r in caplog.records]
  assert any("Could not read manifest.json" in m for m in messages)
  assert kn.list_documents() == []


def test_unreadable_chunks_file_is_logged(kn, caplog):
  kb_dir = kn.KNOWLEDGE_DIR
  _write_legacy(kb_dir, _MANIFEST, None)
  (kb_dir / "chunks.json").write_text("{not json", encoding="utf-8")
  knowledge_migration.migrate_json_to_postgres_if_needed()
  assert any("Could not read chunks.json" in r.getMessage() for r in caplog.records)
  assert [d["id"] for d in kn.list_documents()] == ["d1"]


def test_failed_migration_is_logged_and_raised_and_leaves_the_files(kn, caplog):
  kb_dir = kn.KNOWLEDGE_DIR
  _write_legacy(kb_dir, [{**_MANIFEST[0], "tags": None, "chunk_count": "many"}], [])
  with pytest.raises(Exception):
    knowledge_migration.migrate_json_to_postgres_if_needed()
  assert any("JSON Migration failed" in r.getMessage() for r in caplog.records)
  assert (kb_dir / "manifest.json").exists() and kn.list_documents() == []


def test_export_writes_both_json_files(kn, tmp_path):
  import json

  _ingest(kn, "a.txt", "uno")
  manifest, chunks = knowledge_migration.export_to_json(tmp_path / "out")
  assert json.loads(manifest.read_text(encoding="utf-8"))[0]["filename"] == "a.txt"
  assert json.loads(chunks.read_text(encoding="utf-8"))[0]["text"] == "uno"


# --- schema bootstrap ---------------------------------------------------------

def test_schema_is_created_once_and_reused(kn):
  kn.ensure_knowledge_dirs()
  with kn._db() as conn:
    cur = conn.cursor()
    cur.execute("SELECT value FROM db_meta WHERE key = 'schema_version'")
    assert cur.fetchone()["value"] == "2"
    cur.execute("SELECT udt_name FROM information_schema.columns WHERE table_name = 'chunks' AND column_name = 'embedding' AND table_schema = current_schema()")
    assert cur.fetchone()["udt_name"] == "vector"
  assert kn._SCHEMA_INITIALIZED is True


def test_startup_survives_an_unreachable_database(kn, monkeypatch, caplog):
  monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:x@127.0.0.1:1/none")
  kn.ensure_knowledge_dirs()
  assert any("Could not connect to PostgreSQL" in r.getMessage() for r in caplog.records)


# --- round 2: defaults, schema repair and failure paths -----------------------

class _Cursor:
  """Raises for statements that mention one of `failing`, records the rest."""

  def __init__(self, failing, log):
    self.failing, self.log = failing, log

  def execute(self, sql, params=None):
    self.log.append(sql.strip().split("\n")[0])
    if any(word in sql for word in self.failing):
      raise RuntimeError("not available")

  def fetchone(self):
    return {"udt_name": "jsonb"}


class _Connection:
  def __init__(self, failing=()):
    self.log = []
    self.cursor_ = _Cursor(failing, self.log)

  def cursor(self):
    return self.cursor_

  def commit(self):
    self.log.append("commit")

  def rollback(self):
    self.log.append("rollback")


def test_missing_pgvector_is_recorded_and_the_other_extensions_still_load(monkeypatch):
  monkeypatch.setattr(knowledge, "_PGVECTOR_AVAILABLE", None)
  conn = _Connection(failing=("vector;", "unaccent"))
  knowledge._init_extensions(conn)
  assert knowledge._PGVECTOR_AVAILABLE is False
  assert any("pg_trgm" in line for line in conn.log) and conn.log.count("rollback") == 2


def test_pgvector_is_recorded_when_the_extension_loads(monkeypatch):
  monkeypatch.setattr(knowledge, "_PGVECTOR_AVAILABLE", None)
  monkeypatch.setattr(knowledge, "_register_vector_adapter", lambda conn: None)
  knowledge._init_extensions(_Connection())
  assert knowledge._PGVECTOR_AVAILABLE is True


def test_missing_trigram_extension_is_fatal(monkeypatch):
  conn = _Connection(failing=("pg_trgm",))
  with pytest.raises(RuntimeError, match="pg_trgm is required"):
    knowledge._init_extensions(conn)
  assert conn.log[-1] == "rollback"


def test_failed_adapter_registration_only_warns(monkeypatch, caplog):
  import pgvector.psycopg

  def boom(conn):
    raise RuntimeError("no adapter")

  monkeypatch.setattr(pgvector.psycopg, "register_vector", boom)
  knowledge._register_vector_adapter(object())
  assert any("Could not register pgvector" in r.getMessage() for r in caplog.records)


def test_vector_column_repair_is_skipped_without_pgvector(monkeypatch):
  monkeypatch.setattr(knowledge, "_PGVECTOR_AVAILABLE", False)
  conn = _Connection()
  knowledge._init_vector_column(conn)
  assert conn.log == []


def test_a_json_embedding_column_is_converted_to_vector(kn):
  kn.ensure_knowledge_dirs()
  with kn._db() as conn:
    conn.cursor().execute("DROP INDEX idx_chunks_embedding")
    conn.cursor().execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE jsonb USING NULL")
  with kn._db() as conn:
    kn._init_vector_column(conn)
    cur = conn.cursor()
    cur.execute("SELECT udt_name FROM information_schema.columns WHERE table_name = 'chunks' AND column_name = 'embedding' AND table_schema = current_schema()")
    assert cur.fetchone()["udt_name"] == "vector"


def test_an_existing_vector_column_keeps_its_embeddings(kn):
  _ingest(kn, "a.txt", "uno", embeddings=[_vector(1, 0)])
  with kn._db() as conn:
    kn._init_vector_column(conn)
  assert [h["filename"] for h in kn.search_chunks_vector(_vector(1, 0))] == ["a.txt"]


def test_failed_column_repair_only_warns(monkeypatch, caplog):
  monkeypatch.setattr(knowledge, "_PGVECTOR_AVAILABLE", True)
  conn = _Connection(failing=("information_schema",))
  knowledge._init_vector_column(conn)
  assert any("Could not migrate chunks embedding column" in r.getMessage() for r in caplog.records)
  assert conn.log[-1] == "rollback"


def test_a_document_with_fewer_embeddings_than_chunks_leaves_the_rest_without_one(kn):
  doc = _ingest(kn, "a.txt", "alfa " * 400, embeddings=[_vector(1, 0)])
  assert doc["chunk_count"] > 1
  assert [h["id"] for h in kn.search_chunks_vector(_vector(1, 0))] == [f"{doc['id']}:0"]


def test_deleting_a_document_whose_file_is_gone_still_removes_its_rows(kn):
  doc = _ingest(kn, "a.txt", "uno")
  (kn.get_knowledge_documents_dir() / doc["stored_as"]).unlink()
  assert kn.delete_document(doc["id"]) is True
  assert kn.list_documents() == []


def test_knowledge_directory_is_created_with_its_parents_and_tolerates_existing_ones(kn, monkeypatch, tmp_path):
  nested = tmp_path / "deep" / "er" / "kb"
  monkeypatch.setattr(kn, "KNOWLEDGE_DIR", nested)
  kn.ensure_knowledge_dirs()
  kn.ensure_knowledge_dirs()
  assert nested.is_dir()


def test_stored_tags_may_be_json_text_or_missing():
  assert knowledge._tags_of(None) == []
  assert knowledge._tags_of('["a"]') == ["a"]
  assert knowledge._tags_of(["b"]) == ["b"]


def test_searches_other_than_vector_do_not_need_pgvector(kn, monkeypatch):
  _ingest(kn, "a.txt", "informe ACME-4821")
  monkeypatch.setattr(kn, "_PGVECTOR_AVAILABLE", False)
  assert len(kn.search_chunks_fts("informe")) == 1
  assert len(kn.search_chunks_trigram("ACME-4821")) == 1


def test_searches_return_nothing_without_a_configured_database(kn, monkeypatch):
  monkeypatch.delenv("DATABASE_URL")
  assert kn.search_chunks_vector(_vector(1, 0)) == []
  assert kn.search_chunks_trigram("informe") == []


def test_status_without_configuration_has_the_default_fields(kn, monkeypatch):
  monkeypatch.delenv("DATABASE_URL")
  status = kn.get_db_status()
  assert (status["host"], status["database"], status["doc_count"], status["chunk_count"]) == ("remote", "", 0, 0)
  assert status["is_postgres"] is True and status["spanish_fts_enabled"] is True


def test_status_prefers_the_configured_host_and_falls_back_to_the_connection(kn, monkeypatch):
  from types import SimpleNamespace

  real = kn.get_settings()
  cases = [({"host": "param-host", "database": "param-db"}, "param-host", "param-db"), ({"host": "", "database": ""}, "127.0.0.1", "funcassist_test")]
  for params, host, database in cases:
    fake = SimpleNamespace(get_knowledge_db_params=lambda p=params: p, get_knowledge_db_url=real.get_knowledge_db_url)
    monkeypatch.setattr(kn, "get_settings", lambda f=fake: f)
    status = kn.get_db_status()
    assert (status["host"], status["database"], status["connected"]) == (host, database, True)


def test_migration_without_a_catalog_table_still_migrates(kn):
  kn.ensure_knowledge_dirs()
  with kn._db() as conn:
    conn.cursor().execute("DROP TABLE db_meta")
  _write_legacy(kn.KNOWLEDGE_DIR, _MANIFEST, _CHUNKS)
  knowledge_migration.migrate_json_to_postgres_if_needed()
  assert [d["id"] for d in kn.list_documents()] == ["d1"]


def test_either_legacy_file_alone_triggers_the_migration(kn):
  _write_legacy(kn.KNOWLEDGE_DIR, _MANIFEST, None)
  knowledge_migration.migrate_json_to_postgres_if_needed()
  assert [d["id"] for d in kn.list_documents()] == ["d1"]
  assert (kn.KNOWLEDGE_DIR / "manifest.json.migrated").exists()


def test_legacy_chunks_without_a_manifest_are_retired_without_inserting_anything(kn):
  _write_legacy(kn.KNOWLEDGE_DIR, None, _CHUNKS)
  knowledge_migration.migrate_json_to_postgres_if_needed()
  assert kn.list_documents() == [] and (kn.KNOWLEDGE_DIR / "chunks.json.migrated").exists()


def test_migrated_records_use_their_defaults(kn):
  legacy = [{"id": "d2", "uploaded_at": "2024-01-01T00:00:00+00:00"}]
  _write_legacy(kn.KNOWLEDGE_DIR, legacy, [{"document_id": "d2"}, {"document_id": "d2", "index": 7}])
  knowledge_migration.migrate_json_to_postgres_if_needed()
  doc = kn.list_documents()[0]
  assert (doc["filename"], doc["stored_as"], doc["tags"], doc["chunk_count"], doc["char_count"]) == ("", "", [], 2, 0)
  chunks = kn.load_chunks()
  assert [(c["id"], c["index"], c["text"], c["filename"]) for c in chunks] == [("d2:0", 0, "", ""), ("d2:7", 7, "", "")]
  assert chunks[0]["uploaded_at"].startswith("2024-01-01")


def test_export_defaults_to_the_knowledge_directory_and_keeps_accents_readable(kn):
  _ingest(kn, "a.txt", "canción")
  manifest, chunks = knowledge_migration.export_to_json()
  assert manifest.parent == kn.get_knowledge_base_dir() and "canción" in chunks.read_text(encoding="utf-8")
  knowledge_migration.export_to_json()


def test_export_creates_missing_parents(kn, tmp_path):
  manifest, _ = knowledge_migration.export_to_json(tmp_path / "a" / "b")
  assert manifest.exists()


def test_integrity_reports_a_failing_check(kn, monkeypatch):
  _ingest(kn, "a.txt", "uno")

  def failing_db():
    raise RuntimeError("down")

  monkeypatch.setattr(knowledge_migration, "_db", failing_db)
  result = knowledge_migration.verify_integrity()
  assert result["ok"] is False and any("Error en prueba de integridad: down" in d for d in result["details"])


def test_integrity_of_an_unreachable_database_reports_the_connection_error(kn, monkeypatch):
  monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:x@127.0.0.1:1/none")
  result = knowledge_migration.verify_integrity()
  assert result["ok"] is False and result["details"][0].startswith("Error de conexión a PostgreSQL: Error al conectar")
