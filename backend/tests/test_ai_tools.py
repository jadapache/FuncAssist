"""Agent tool registry and the permission checks of default tools."""

from types import SimpleNamespace

import pytest

from app.ai.tools import registry as reg
from app.ai.tools.registry import Tool, ToolContext


def test_registry_and_schema():
  names = {t.name for t in reg.list_tools()}
  assert {"search_knowledge", "read_document", "create_artifact"} <= names
  assert reg.get_tool("nope") is None
  assert reg.get_tool("create_artifact").read_only is False
  schema = {s["function"]["name"]: s for s in reg.get_tools_openai_schema()}
  assert schema["read_document"]["type"] == "function"
  assert schema["read_document"]["function"]["parameters"]["required"] == ["document_id"]


def test_register_custom_tool():
  async def h(args, ctx):
    return "ok"
  reg.register_tool(Tool("tmp_tool", "d", {}, h))
  try:
    assert reg.get_tool("tmp_tool").handler is h
  finally:
    reg._TOOL_REGISTRY.pop("tmp_tool", None)


@pytest.mark.asyncio
async def test_search_knowledge_permissions(monkeypatch):
  calls = []

  async def fake_assemble(query, sources, user_id):
    calls.append((query, sources, user_id))
    if query == "vacío":
      return SimpleNamespace(is_empty=True, chunks=[])
    chunks = [SimpleNamespace(id=f"c{i}", source_label="Wiki", text="t" * 900) for i in range(7)]
    return SimpleNamespace(is_empty=False, chunks=chunks)

  monkeypatch.setattr(reg, "assemble_context", fake_assemble)
  ctx = ToolContext(user_id="u", allowed_sources=["wiki", "jira"])
  h = reg._search_knowledge
  assert await h({}, ctx) == "[Error]: Query vacía"
  assert "No hay fuentes" in await h({"query": "q"}, ToolContext())
  assert "Fuentes no permitidas" in await h({"query": "q", "sources": ["secret"]}, ctx)
  assert "No se encontró" in await h({"query": "vacío"}, ctx)
  out = await h({"query": "q", "sources": ["jira", "secret", 3]}, ctx)
  assert calls[-1] == ("q", ["jira"], "u")
  assert out.count("[Chunk ID:") == 5 and "t" * 801 not in out
  await h({"query": "q"}, ctx)
  assert calls[-1][1] == ["wiki", "jira"]


@pytest.mark.asyncio
async def test_read_document_permissions(monkeypatch):
  monkeypatch.setattr(reg, "chunks_from_documents",
                      lambda ids: [] if ids == ["empty"] else [SimpleNamespace(text="x" * 1500)] * 4)
  ctx = ToolContext(allowed_document_ids=["d1", "empty"])
  assert await reg._read_document({}, ctx) == "[Error]: document_id requerido"
  assert "no disponible" in await reg._read_document({"document_id": "other"}, ctx)
  assert "no contiene texto" in await reg._read_document({"document_id": "empty"}, ctx)
  out = await reg._read_document({"document_id": "d1"}, ctx)
  assert out.startswith("[Documento d1]:\n") and len(out) == len("[Documento d1]:\n") + 2000


@pytest.mark.asyncio
async def test_create_artifact_collects():
  ctx = ToolContext()
  assert await reg._create_artifact({"content": "  "}, ctx) == "[Error]: content vacío"
  out = await reg._create_artifact({"title": "T", "extension": ".md", "content": "# hi"}, ctx)
  assert "'T.md'" in out
  assert ctx.artifacts == [{"title": "T", "extension": "md", "content": "# hi"}]
