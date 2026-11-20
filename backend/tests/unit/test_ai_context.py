"""Prompt context: conversation history, rolling summaries, token budgets and section generation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai import budget, history as history_mod
from app.ai.history import format_history_as_messages, prune_or_summarize_history
from app.ai.providers.base import AICompletion, AIMessage
from app.ai.section_generator import DocumentPlan, PlanSection, generate_sections_stream


def _turns(n):
  msgs = []
  for i in range(n):
    msgs.append(AIMessage(role="user", content=f"pregunta {i} " + "x" * 400))
    msgs.append(AIMessage(role="assistant", content=f"respuesta {i} " + "y" * 400))
  return msgs


def _fast(*texts):
  fast = MagicMock()
  fast.complete = AsyncMock(side_effect=[AICompletion(text=t, provider="p", model="m") for t in texts])
  return fast


class _MemoryStore:
  def __init__(self, record=None):
    self.record = record
    self.saves = 0

  async def load(self):
    return self.record

  async def save(self, key, summary):
    self.record = (key, summary)
    self.saves += 1


class TestHistoryFormatting:
  def test_parses_legacy_role_lines(self):
    msgs = format_history_as_messages(["user: hola", "assistant: qué tal", "user: bien\nmultilínea", "assistant: ok"])
    assert [m.role for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[2].content == "bien\nmultilínea"

  def test_merges_same_role_and_drops_unknown_roles(self):
    msgs = format_history_as_messages([
      {"role": "user", "content": "a"},
      {"role": "user", "content": "b"},
      {"role": "system", "content": "x"},
      {"role": "assistant", "content": "c"},
    ])
    assert [(m.role, m.content) for m in msgs] == [("user", "a\n\nb"), ("assistant", "c")]

  def test_trailing_user_turn_is_dropped(self):
    msgs = format_history_as_messages([{"role": "assistant", "content": "c"}, {"role": "user", "content": "actual"}])
    assert [m.role for m in msgs] == ["assistant"]


class TestRollingSummary:
  def setup_method(self):
    history_mod._summary_cache.clear()

  @pytest.mark.asyncio
  async def test_summary_alternates_roles_and_is_cached(self):
    fast = _fast("resumen", "no debería usarse")
    out1 = await prune_or_summarize_history(_turns(12), 1500, "gpt-4o", fast_provider=fast, scope="c1")
    out2 = await prune_or_summarize_history(_turns(12), 1500, "gpt-4o", fast_provider=fast, scope="c1")
    assert fast.complete.await_count == 1 and out1 == out2
    roles = [m.role for m in out1]
    assert roles[0] == "user" and all(a != b for a, b in zip(roles, roles[1:]))

  @pytest.mark.asyncio
  async def test_persisted_summary_survives_restart(self):
    fast = _fast("resumen v1")
    store = _MemoryStore()
    await prune_or_summarize_history(_turns(12), 1500, "gpt-4o", fast_provider=fast, scope="c1", store=store)
    history_mod._summary_cache.clear()
    out = await prune_or_summarize_history(_turns(12), 1500, "gpt-4o", fast_provider=fast, scope="c1", store=store)
    assert fast.complete.await_count == 1 and "resumen v1" in out[0].content

  @pytest.mark.asyncio
  async def test_incremental_update_sends_only_new_turns(self):
    fast = _fast("resumen v1", "resumen v2")
    store = _MemoryStore()
    await prune_or_summarize_history(_turns(12), 1500, "gpt-4o", fast_provider=fast, scope="c1", store=store)
    history_mod._summary_cache.clear()

    out = await prune_or_summarize_history(_turns(14), 1500, "gpt-4o", fast_provider=fast, scope="c1", store=store)
    prompt = fast.complete.await_args_list[1].args[0][1].content
    assert "RESUMEN ACTUAL:\nresumen v1" in prompt and "pregunta 0 " not in prompt
    assert "resumen v2" in out[0].content

  @pytest.mark.asyncio
  async def test_summary_from_another_conversation_is_ignored(self):
    foreign = _MemoryStore(record=("10:" + "0" * 64, "ajeno"))
    out = await prune_or_summarize_history(_turns(12), 1500, "gpt-4o", fast_provider=_fast("propio"), scope="c1", store=foreign)
    assert "propio" in out[0].content

  @pytest.mark.asyncio
  async def test_store_failures_do_not_break_history(self):
    store = MagicMock()
    store.load = AsyncMock(side_effect=RuntimeError("db down"))
    store.save = AsyncMock(side_effect=RuntimeError("db down"))
    out = await prune_or_summarize_history(_turns(12), 1500, "gpt-4o", fast_provider=_fast("r"), scope="c1", store=store)
    assert "r" in out[0].content


class TestTokenBudget:
  def test_groq_is_capped_by_input_rate_limit(self):
    with patch.object(budget, "load_local_catalog", return_value=[]):
      assert budget.calculate_input_budget("groq", "llama-3.3-70b-versatile", 1500) <= 6_000

  def test_requested_output_is_reserved(self):
    with patch.object(budget, "context_window", return_value=128_000):
      assert budget.calculate_input_budget("openai", "gpt-4o", 2_000) == 128_000 - 2_000 - budget.SAFETY_MARGIN_TOKENS

  @pytest.mark.asyncio
  async def test_grounded_context_drops_lowest_ranked_chunks(self):
    from app.ai.runner import _fit_bundle_to_budget

    bundle = MagicMock()
    bundle.chunks = [f"c{i}" for i in range(10)]
    bundle.to_prompt_block = lambda: " ".join(bundle.chunks)
    with patch("app.ai.runner.calculate_input_budget", return_value=100), \
         patch("app.ai.runner.count_tokens", side_effect=lambda m, t: len(t.split()) * 20 if t else 0):
      await _fit_bundle_to_budget(bundle, provider=MagicMock(id="groq", default_model="m"), max_output_tokens=100, fixed_texts=["a"])
    assert bundle.chunks == ["c0", "c1", "c2", "c3"]  # 100 budget - 20 fixed = 4 chunks of 20


class TestSectionGeneration:
  @pytest.mark.asyncio
  async def test_sections_stream_in_plan_order_and_share_cacheable_prefix(self):
    delays = {"A": 0.03, "B": 0.0, "C": 0.01}  # finish out of order

    async def fake_complete(messages, max_tokens=None):
      title = next(t for t in delays if f"'{t}'" in messages[1].content)
      await asyncio.sleep(delays[title])
      return AICompletion(text=f"cuerpo {title}", provider="p", model="m")

    prov = MagicMock()
    prov.complete = AsyncMock(side_effect=fake_complete)
    plan = DocumentPlan("Doc", "md", "", [PlanSection("A"), PlanSection("B"), PlanSection("C")])

    full = "".join([c async for c in generate_sections_stream(plan, "SYS", "CTX", prov)])

    assert full.index("## A") < full.index("## B") < full.index("## C")
    assert full.startswith("<chat>") and full.rstrip().endswith("</artifact>")
    systems = {call.args[0][0].content for call in prov.complete.await_args_list}
    assert len(systems) == 1
