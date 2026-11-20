"""Agent loop and tools: permission boundaries, context propagation and user isolation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.agent import run_agent
from app.ai.providers.base import AICompletion, AIMessage, ToolCall
from app.ai.request_types import GroundedFeatureRequest, SimpleFeatureRequest
from app.ai.runner import run_grounded_request, run_simple_feature
from app.ai.tools.registry import ToolContext, get_tool


class TestToolPermissions:
  @pytest.mark.asyncio
  async def test_search_rejects_sources_outside_allowlist(self):
    with patch("app.ai.tools.registry.assemble_context", new=AsyncMock()) as assemble:
      out = await get_tool("search_knowledge").handler(
        {"query": "q", "sources": ["jira"]}, ToolContext(allowed_sources=["knowledge"])
      )
    assert out.startswith("[Error]")
    assemble.assert_not_called()

  @pytest.mark.asyncio
  async def test_search_is_scoped_to_user_and_allowed_sources(self):
    bundle = MagicMock(is_empty=True)
    with patch("app.ai.tools.registry.assemble_context", new=AsyncMock(return_value=bundle)) as assemble:
      await get_tool("search_knowledge").handler(
        {"query": "q", "sources": ["knowledge", "jira"]},
        ToolContext(user_id="u1", allowed_sources=["knowledge"]),
      )
    assemble.assert_awaited_once_with(query="q", sources=["knowledge"], user_id="u1")

  @pytest.mark.asyncio
  async def test_read_document_requires_attached_document(self):
    with patch("app.ai.tools.registry.chunks_from_documents") as loader:
      out = await get_tool("read_document").handler({"document_id": "other"}, ToolContext(allowed_document_ids=["mine"]))
    assert out.startswith("[Error]")
    loader.assert_not_called()


class TestAgentLoop:
  @pytest.mark.asyncio
  async def test_receives_full_context_and_delivers_artifacts(self):
    provider = MagicMock(id="mock")
    provider.complete = AsyncMock(side_effect=[
      AICompletion(
        text="",
        provider="mock",
        model="m",
        tool_calls=[ToolCall(id="a1", name="create_artifact", arguments={"title": "Plan", "extension": "md", "content": "# Hola"})],
      ),
      AICompletion(text="Listo.", provider="mock", model="m"),
    ])
    initial = [
      AIMessage(role="system", content="sys"),
      AIMessage(role="system", content="DOCUMENTOS: ..."),
      AIMessage(role="user", content=[{"type": "text", "text": "q"}, {"type": "image_url", "image_url": {"url": "data:x"}}]),
    ]

    events = [ev async for ev in run_agent(messages=initial, provider=provider, ctx=ToolContext(), max_iters=3)]

    assert provider.complete.await_args_list[0].args[0][:3] == initial
    types = [e.type for e in events]
    assert types.index("artifact_start") < types.index("artifact_delta") < types.index("artifact_end")
    assert next(e for e in events if e.type == "artifact_delta").data["text"] == "# Hola"
    assert types[-1] == "done"

  @pytest.mark.asyncio
  async def test_last_iteration_keeps_tools_declared(self):
    provider = MagicMock(id="mock")
    provider.complete = AsyncMock(return_value=AICompletion(
      text="", provider="mock", model="m",
      tool_calls=[ToolCall(id="x", name="search_knowledge", arguments={"query": "q"})],
    ))
    with patch("app.ai.tools.registry.assemble_context", new=AsyncMock(return_value=MagicMock(is_empty=True))):
      _ = [ev async for ev in run_agent(
        messages=[AIMessage(role="user", content="q")],
        provider=provider,
        ctx=ToolContext(allowed_sources=["knowledge"]),
        max_iters=2,
      )]
    last = provider.complete.await_args_list[-1].kwargs
    assert last["tools"] and last["tool_choice"] == "none"


class TestUserIsolation:
  @pytest.mark.asyncio
  async def test_feature_runners_propagate_user_id(self):
    with patch("app.ai.runner.run_grounded_feature", new_callable=AsyncMock, return_value={"ok": True}) as grounded:
      await run_simple_feature(SimpleFeatureRequest(feature="f", query="q", user_id="u1"))
      assert grounded.call_args.kwargs["user_id"] == "u1"
      await run_grounded_request(GroundedFeatureRequest(feature="f", query="q", sources=["knowledge"], user_id="u2"))
      assert grounded.call_args.kwargs["user_id"] == "u2"
