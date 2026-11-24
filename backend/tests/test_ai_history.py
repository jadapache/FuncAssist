"""Conversation history normalization, pruning and rolling summaries."""

from types import SimpleNamespace

import pytest

from app.ai import history
from app.ai.history import (
  _decode_store_key,
  _encode_store_key,
  _summary_key,
  format_history_as_messages,
  prune_or_summarize_history,
)
from app.ai.providers.base import AIMessage


@pytest.fixture(autouse=True)
def _clear_cache():
  history._summary_cache.clear()
  yield
  history._summary_cache.clear()


def _m(role, content):
  return AIMessage(role=role, content=content)


class _Prov:
  default_model = "fast"

  def __init__(self, reply="RESUMEN", exc=None):
    self.reply, self.exc, self.calls = reply, exc, []

  async def complete(self, messages, **kw):
    self.calls.append(messages)
    if self.exc:
      raise self.exc
    return SimpleNamespace(text=self.reply)


class _Store:
  def __init__(self, record=None, load_exc=None, save_exc=None):
    self.record, self.load_exc, self.save_exc, self.saved = record, load_exc, save_exc, []

  async def load(self):
    if self.load_exc:
      raise self.load_exc
    return self.record

  async def save(self, key, summary):
    if self.save_exc:
      raise self.save_exc
    self.saved.append((key, summary))


def test_format_history_variants():
  assert format_history_as_messages(None) == []
  msgs = format_history_as_messages("user: hola\nsigue\nassistant: qué tal\nuser: último")
  assert [(m.role, m.content) for m in msgs] == [("user", "hola\nsigue"), ("assistant", "qué tal")]
  msgs = format_history_as_messages(["sin prefijo", "bot: respuesta"])
  assert [(m.role, m.content) for m in msgs] == [("user", "sin prefijo"), ("assistant", "respuesta")]
  msgs = format_history_as_messages([
    {"role": "user", "content": "a"}, {"role": "Usuario", "content": " b "},
    {"role": "system", "content": "drop"}, {"role": "assistant", "content": ""},
    {"role": "model", "content": "ok"}, "ignored-string", {"role": "ai", "content": 5},
  ])
  assert [(m.role, m.content) for m in msgs] == [("user", "a\n\nb"), ("assistant", "ok")]


def test_store_key_roundtrip():
  assert _decode_store_key(_encode_store_key(3, "abc")) == (3, "abc")
  for bad in ("", "x:abc", "3", "3:"):
    assert _decode_store_key(bad) is None
  older = [_m("user", "a")]
  assert _summary_key("s1", older) != _summary_key("s2", older)


@pytest.mark.asyncio
async def test_prune_returns_all_when_fits(monkeypatch):
  monkeypatch.setattr(history, "count_tokens", lambda m, msgs: 1)
  msgs = [_m("user", "a"), _m("assistant", "b")]
  assert await prune_or_summarize_history([], 10, "m") == []
  assert await prune_or_summarize_history(msgs, 10, "m") == msgs


def _conv(n):
  out = []
  for i in range(n):
    out.append(_m("user", f"u{i}"))
    out.append(_m("assistant", f"a{i}"))
  return out


@pytest.mark.asyncio
async def test_prune_summarizes_older_and_caches(monkeypatch):
  monkeypatch.setattr(history, "count_tokens", lambda m, msgs: len(msgs) * 10)
  msgs = _conv(5)  # 10 messages
  prov = _Prov()
  store = _Store()
  out = await prune_or_summarize_history(msgs, 60, "m", fast_provider=prov, scope="s", store=store)
  assert out[0].content.endswith("RESUMEN") and out[1].role == "assistant"
  assert out[2:] == msgs[-6:]
  assert len(store.saved) == 1 and store.saved[0][0].startswith("4:")
  # Second call hits the in-process cache.
  out2 = await prune_or_summarize_history(msgs, 60, "m", fast_provider=prov, scope="s", store=store)
  assert out2 == out and len(prov.calls) == 1


@pytest.mark.asyncio
async def test_prune_drops_recent_pairs_when_over_budget(monkeypatch):
  monkeypatch.setattr(history, "count_tokens", lambda m, msgs: len(msgs) * 10)
  msgs = _conv(5)
  out = await prune_or_summarize_history(msgs, 25, "m")  # no provider, no store => no summary
  assert out == msgs[-2:]


@pytest.mark.asyncio
async def test_persisted_summary_reused_and_incremental(monkeypatch):
  monkeypatch.setattr(history, "count_tokens", lambda m, msgs: len(msgs) * 10)
  msgs = _conv(5)
  older = msgs[:4]
  # Exact persisted match: no model call.
  store = _Store(record=(_encode_store_key(4, _summary_key("s", older)), "PERSISTED"))
  prov = _Prov()
  out = await prune_or_summarize_history(msgs, 60, "m", fast_provider=prov, scope="s", store=store)
  assert "PERSISTED" in out[0].content and prov.calls == []

  # Shorter persisted prefix: only new turns are sent along with the previous summary.
  history._summary_cache.clear()
  store = _Store(record=(_encode_store_key(2, _summary_key("s", older[:2])), "OLD"))
  prov = _Prov(reply="NEW")
  out = await prune_or_summarize_history(msgs, 60, "m", fast_provider=prov, scope="s", store=store)
  assert "NEW" in out[0].content
  user_msg = prov.calls[0][1].content
  assert "RESUMEN ACTUAL:\nOLD" in user_msg and "u1" in user_msg and "u0" not in user_msg

  # Previous summary without provider: returned as-is.
  history._summary_cache.clear()
  out = await prune_or_summarize_history(msgs, 60, "m", scope="s", store=store)
  assert "OLD" in out[0].content


@pytest.mark.asyncio
async def test_summary_failures_fall_back(monkeypatch):
  monkeypatch.setattr(history, "count_tokens", lambda m, msgs: len(msgs) * 10)
  msgs = _conv(5)
  # Load fails, provider fails => no summary, only recent turns.
  out = await prune_or_summarize_history(
    msgs, 60, "m", fast_provider=_Prov(exc=RuntimeError("x")), store=_Store(load_exc=RuntimeError("db"))
  )
  assert out == msgs[-6:]
  # Empty summary => recent only.
  out = await prune_or_summarize_history(msgs, 60, "m", fast_provider=_Prov(reply="  "))
  assert out == msgs[-6:]
  # Save fails but summary is still used; mismatching store key ignored.
  store = _Store(record=("4:wrongdigest", "X"), save_exc=RuntimeError("db"))
  out = await prune_or_summarize_history(msgs, 60, "m", fast_provider=_Prov(reply="S"), store=store)
  assert out[0].content.endswith("S")




