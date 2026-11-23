"""Map-reduce context condensing and text chunking."""

from types import SimpleNamespace

import pytest

from app.ai.map_reduce import map_reduce_condense_context, resolve_input_character_budget, split_text_into_chunks


def test_character_budgets():
  assert resolve_input_character_budget("Gemini") == 800_000
  assert resolve_input_character_budget("claude") == 200_000
  assert resolve_input_character_budget("groq") == 14_000
  assert resolve_input_character_budget(None) == 15_000


def test_split_text():
  assert split_text_into_chunks("   ") == []
  assert split_text_into_chunks("short", max_chars=100) == ["short"]
  text = "\n\n".join(["a" * 30, "b" * 30, "c" * 30])
  chunks = split_text_into_chunks(text, max_chars=70)
  assert chunks == ["a" * 30 + "\n\n" + "b" * 30, "c" * 30]
  long_para = "Uno dos tres. " * 10
  chunks = split_text_into_chunks("x" * 10 + "\n\n" + long_para.strip(), max_chars=40)
  assert chunks[0] == "x" * 10
  assert all(len(c) <= 40 for c in chunks)
  assert "".join(chunks).replace(" ", "").count("Uno") == 10


class _Prov:
  id = "groq"
  default_model = "m"

  def __init__(self, map_replies, reduce_reply=None, reduce_exc=None):
    self.map_replies, self.reduce_reply, self.reduce_exc = map_replies, reduce_reply, reduce_exc
    self.calls = []

  async def complete(self, messages, max_tokens=None):
    self.calls.append(max_tokens)
    if max_tokens == 1500:
      if self.reduce_exc:
        raise self.reduce_exc
      return SimpleNamespace(text=self.reduce_reply)
    idx = int(messages[1].content.split()[1]) - 1
    reply = self.map_replies[idx % len(self.map_replies)]
    if isinstance(reply, Exception):
      raise reply
    return SimpleNamespace(text=reply)


def _big(n_paras=4, size=3000):
  return "\n\n".join(chr(65 + i) * size for i in range(n_paras))


@pytest.mark.asyncio
async def test_short_text_untouched():
  prov = _Prov(["x"])
  assert await map_reduce_condense_context("abc", 100, prov) == "abc"
  assert await map_reduce_condense_context("", 100, prov) == ""
  # Single chunk: truncated, no model calls.
  assert await map_reduce_condense_context("a" * 50, 20, prov) == "a" * 20
  assert prov.calls == []


@pytest.mark.asyncio
async def test_map_only_when_combined_fits():
  prov = _Prov(["sum", "", RuntimeError("fail")])
  text = _big(3)
  out = await map_reduce_condense_context(text, 5000, prov)
  assert "--- Hallazgos Parte 1 ---\nsum" in out
  assert "--- Extracto Parte 2 ---\n" + "B" * 1200 in out
  assert "--- Extracto Parte 3 ---" in out
  assert 1500 not in prov.calls


@pytest.mark.asyncio
async def test_reduce_paths(monkeypatch):
  monkeypatch.setenv("AI_MAP_CONCURRENCY", "1")
  text = _big(4)
  prov = _Prov(["y" * 2000], reduce_reply="FINAL")
  assert await map_reduce_condense_context(text, 3500, prov) == "FINAL"
  prov = _Prov(["y" * 2000], reduce_reply="  ")
  out = await map_reduce_condense_context(text, 3500, prov)
  assert len(out) == 3500 and out.startswith("--- Hallazgos Parte 1")
  prov = _Prov(["y" * 2000], reduce_exc=RuntimeError("x"))
  assert len(await map_reduce_condense_context(text, 3500, prov)) == 3500
