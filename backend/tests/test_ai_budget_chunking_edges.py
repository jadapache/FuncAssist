"""Edge cases of the token budget helpers, chunking, map-reduce, stream control and image messages."""

import asyncio
import logging
from types import SimpleNamespace

import pytest

from app.ai import budget, map_reduce
from app.ai.multimodal import user_message_with_images
from app.ai.stream_control import StreamStopped, iterate_until_stopped


# --- budget ---------------------------------------------------------------

def _no_tokenizer(monkeypatch):
  def boom(**kw):
    raise RuntimeError("no tokenizer")
  monkeypatch.setattr(budget, "token_counter", boom)


def test_count_tokens_fallback_is_at_least_one(monkeypatch):
  _no_tokenizer(monkeypatch)
  assert budget.count_tokens("m", [{"content": "ab"}]) == 1


def test_chars_per_token_never_below_one_and_never_divides_by_zero(monkeypatch):
  monkeypatch.setattr(budget, "count_tokens", lambda model, text: 100)
  assert budget.chars_per_token("m", "abcd") == 1.0
  monkeypatch.setattr(budget, "count_tokens", lambda model, text: 0)
  assert budget.chars_per_token("m", "abcd") == 4.0


def test_output_reservation_is_capped_at_half_the_window(monkeypatch):
  monkeypatch.setattr(budget, "context_window", lambda provider, model: 10_000)
  assert budget.calculate_input_budget("x", "m", reserved_output=9_000) == 10_000 - 5_000 - budget.SAFETY_MARGIN_TOKENS
  assert budget.calculate_input_budget("x", "m", reserved_output=1_000) == 10_000 - 1_000 - budget.SAFETY_MARGIN_TOKENS


# --- chunking -------------------------------------------------------------

def test_chunk_boundaries_are_inclusive():
  a, b, c, d = ("a" * 30, "b" * 30, "c" * 30, "d" * 30)
  # Each paragraph counts its two separator characters: 32 + 32 fits exactly in 64.
  assert map_reduce.split_text_into_chunks("\n\n".join([a, b, c, d]), max_chars=64) == [f"{a}\n\n{b}", f"{c}\n\n{d}"]


def test_paragraph_size_includes_its_separator():
  first, second = "a" * 31, "b" * 31
  assert map_reduce.split_text_into_chunks(f"{first}\n\n{second}", max_chars=63) == [first, second]


def test_text_exactly_at_the_limit_is_one_chunk():
  text = "a" * 30 + "\n\n" + "b" * 30
  assert map_reduce.split_text_into_chunks(text, max_chars=len(text)) == [text]


def test_paragraph_that_exactly_fills_a_chunk_is_not_split_into_sentences():
  paragraph = "Aa. Bb."
  filler = "x" * 20
  chunks = map_reduce.split_text_into_chunks(f"{filler}\n\n{paragraph}", max_chars=len(paragraph) + 2)
  assert chunks == [filler, paragraph]


def test_oversized_paragraph_is_split_on_sentences():
  paragraph = "Uno dos. Tres cuatro. Cinco seis."
  chunks = map_reduce.split_text_into_chunks(paragraph + "\n\n" + paragraph, max_chars=25)
  assert all(len(c) <= 25 for c in chunks)
  assert "Uno dos." in chunks[0]


# --- map-reduce -----------------------------------------------------------

class _Provider:
  default_model = "model-x"

  def __init__(self, id="openai", replies=None, fail=False):
    self.id = id
    self.replies = replies if replies is not None else ["S"]
    self.fail = fail
    self.calls = 0

  async def complete(self, messages, max_tokens=None):
    self.calls += 1
    if self.fail:
      raise RuntimeError("boom")
    return SimpleNamespace(text=self.replies[min(self.calls - 1, len(self.replies) - 1)])


def test_map_concurrency_depends_on_provider_and_env(monkeypatch):
  monkeypatch.delenv("AI_MAP_CONCURRENCY", raising=False)
  assert map_reduce._map_concurrency(_Provider("groq")) == 2
  assert map_reduce._map_concurrency(_Provider("openai")) == 4
  monkeypatch.setenv("AI_MAP_CONCURRENCY", "7")
  assert map_reduce._map_concurrency(_Provider("groq")) == 7


def _two_paragraphs():
  return "a" * 40 + "\n\n" + "b" * 40


@pytest.mark.asyncio
async def test_combined_summaries_exactly_at_budget_skip_the_reduce_step():
  provider = _Provider(replies=["S"])
  combined = "--- Hallazgos Parte 1 ---\nS\n\n--- Hallazgos Parte 2 ---\nS"
  result = await map_reduce.map_reduce_condense_context(_two_paragraphs(), len(combined), provider)
  assert result == combined
  assert provider.calls == 2


@pytest.mark.asyncio
async def test_empty_summary_is_logged_with_its_position_and_falls_back_to_an_excerpt(caplog):
  provider = _Provider(replies=[""])
  with caplog.at_level(logging.WARNING):
    result = await map_reduce.map_reduce_condense_context(_two_paragraphs(), 60, provider)
  assert "--- Extracto Parte 1 ---" in result
  assert any("chunk 1/2" in r.getMessage() and "empty summary" in r.getMessage() for r in caplog.records)
  assert any("chunk 2/2" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_failed_chunk_is_logged_with_traceback_and_model(caplog):
  provider = _Provider(fail=True)
  with caplog.at_level(logging.WARNING):
    await map_reduce.map_reduce_condense_context(_two_paragraphs(), 60, provider)
  failures = [r for r in caplog.records if "failed with model" in r.getMessage() and "chunk" in r.getMessage()]
  assert {"chunk 1/2" in r.getMessage() for r in failures} == {True, False}
  assert all("model-x" in r.getMessage() and r.exc_info for r in failures)


@pytest.mark.asyncio
async def test_failed_reduce_is_logged_with_traceback_and_truncates(caplog):
  class _MapOkReduceFails(_Provider):
    async def complete(self, messages, max_tokens=None):
      if messages[0].content.startswith("Sintetiza"):
        raise RuntimeError("reduce boom")
      return SimpleNamespace(text="S" * 80)

  with caplog.at_level(logging.WARNING):
    result = await map_reduce.map_reduce_condense_context(_two_paragraphs(), 60, _MapOkReduceFails())
  assert len(result) == 60
  record = next(r for r in caplog.records if "final synthesis failed" in r.getMessage())
  assert "model-x" in record.getMessage() and record.exc_info


# --- stream control -------------------------------------------------------

async def _numbers():
  for n in range(3):
    yield n


@pytest.mark.asyncio
async def test_finished_stream_does_not_log_a_cancellation(caplog):
  async def never():
    return None

  with caplog.at_level(logging.INFO):
    assert [n async for n in iterate_until_stopped(_numbers(), never)] == [0, 1, 2]
  assert not any("Stopping generation task" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_stopped_stream_logs_the_cancellation(caplog):
  async def slow():
    await asyncio.sleep(10)
    yield 1

  async def stop():
    return "cancelled"

  with caplog.at_level(logging.INFO), pytest.raises(StreamStopped):
    async for _ in iterate_until_stopped(slow(), stop, poll_s=0.01):
      pass
  assert any("Stopping generation task" in r.getMessage() for r in caplog.records)


# --- image messages -------------------------------------------------------

def test_message_without_images_is_plain_text():
  assert user_message_with_images("hola", None).content == "hola"
  assert user_message_with_images("hola", []).content == "hola"


def test_image_url_prefers_data_then_data_url_and_keeps_data_uris():
  message = user_message_with_images("t", [{"data": "AA"}, {"dataUrl": "BB"}, {"data": "data:image/gif;base64,CC", "dataUrl": "DD"}])
  assert [p["image_url"]["url"] for p in message.content[1:]] == [
    "data:image/png;base64,AA", "data:image/png;base64,BB", "data:image/gif;base64,CC",
  ]


def test_image_mime_type_prefers_mime_type_over_type():
  message = user_message_with_images("t", [{"data": "AA", "mime_type": "image/webp", "type": "image/gif"}, {"data": "BB", "type": "image/gif"}])
  assert [p["image_url"]["url"] for p in message.content[1:]] == ["data:image/webp;base64,AA", "data:image/gif;base64,BB"]


def test_images_without_data_are_kept_by_default_and_skipped_on_request():
  images = [{}, {"data": "AA"}]
  assert len(user_message_with_images("t", images).content) == 3
  assert len(user_message_with_images("t", images, skip_empty=False).content) == 3
  skipped = user_message_with_images("t", images, skip_empty=True).content
  assert [p["type"] for p in skipped] == ["text", "image_url"]
  assert user_message_with_images("t", [{"dataUrl": "BB"}], skip_empty=True).content[1]["image_url"]["url"].endswith("BB")


# --- round 3: remaining boundary cases -------------------------------------

def test_sentences_share_a_chunk_until_it_is_full():
  chunker = map_reduce._Chunker(25)
  map_reduce._add_sentences(chunker, "Uno dos. Tres cuatro. Cinco seis.")
  chunker.flush("\n\n")
  assert chunker.chunks == ["Uno dos. Tres cuatro.", "Cinco seis."]


@pytest.mark.asyncio
async def test_failed_chunks_are_logged_with_their_own_number(caplog):
  provider = _Provider(fail=True)
  with caplog.at_level(logging.WARNING):
    await map_reduce.map_reduce_condense_context(_two_paragraphs(), 60, provider)
  messages = [r.getMessage() for r in caplog.records if "failed with model" in r.getMessage() and "chunk" in r.getMessage()]
  assert any("chunk 1/2" in m for m in messages) and any("chunk 2/2" in m for m in messages)
  assert not any("chunk 0/2" in m for m in messages)
