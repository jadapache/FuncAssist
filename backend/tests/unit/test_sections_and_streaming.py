"""Section generation, incremental artifact splitting, cancellation helper and AI log utilities."""

import asyncio
import json
import logging

import pytest

from app.ai import logging as ai_logging
from app.ai.artifacts import ArtifactStreamSplitter, extract_artifacts, has_unclosed_artifact
from app.ai.events import AgentEvent
from app.ai.providers.base import AICompletion, AIMessage
from app.ai.section_generator import DocumentPlan, PlanSection, generate_sections_stream, plan_document
from app.ai.stream_control import StreamStopped, iterate_until_stopped


class _SectionProvider:
  """Fake main provider: fails `fail_times` times for sections whose title is in `failing`."""

  id = "mock"
  default_model = "m"

  def __init__(self, failing=(), fail_times=1, slow=(), delay=0.0):
    self.failing = set(failing)
    self.fail_times = fail_times
    self.slow = set(slow)
    self.delay = delay
    self.failures: dict[str, int] = {}
    self.calls: list[list[AIMessage]] = []
    self.cancelled: list[str] = []

  async def complete(self, messages, **kwargs):
    self.calls.append(list(messages))
    instruction = messages[-1].content
    text = instruction if isinstance(instruction, str) else instruction[0]["text"]
    title = text.split("'")[1]
    if title in self.slow:
      try:
        await asyncio.sleep(self.delay)
      except asyncio.CancelledError:
        self.cancelled.append(title)
        raise
    if title in self.failing and self.failures.get(title, 0) < self.fail_times:
      self.failures[title] = self.failures.get(title, 0) + 1
      raise RuntimeError(f"boom {title}")
    return AICompletion(text=f"Contenido de {title}", provider="mock", model="m", prompt_tokens=5, completion_tokens=7)


def _plan(*titles):
  return DocumentPlan(title="Plan QA", extension="docx", chat_intro="Listo", sections=[PlanSection(t, "") for t in titles])


async def _collect(gen):
  return [item async for item in gen]


class TestSectionGeneration:
  @pytest.mark.asyncio
  async def test_plan_event_first_and_sections_in_order(self):
    usage: dict = {}
    items = await _collect(generate_sections_stream(
      _plan("A", "B"), "sys", "ctx", _SectionProvider(), usage_sink=usage,
    ))
    assert isinstance(items[0], AgentEvent) and items[0].type == "plan"
    assert items[0].data["sections"] == ["A", "B"]
    text = "".join(i for i in items if isinstance(i, str))
    assert text.index("## A") < text.index("## B") and text.rstrip().endswith("</artifact>")
    assert usage["prompt_tokens"] == 10 and usage["llm_calls"] == 2

  @pytest.mark.asyncio
  async def test_failed_section_is_retried_once(self):
    provider = _SectionProvider(failing={"B"}, fail_times=1)
    items = await _collect(generate_sections_stream(_plan("A", "B"), "sys", "ctx", provider))
    text = "".join(i for i in items if isinstance(i, str))
    assert "Contenido de B" in text and "pendiente" not in text

  @pytest.mark.asyncio
  async def test_section_failing_twice_is_pending_and_reported_in_chat(self):
    provider = _SectionProvider(failing={"B"}, fail_times=5)
    usage: dict = {}
    items = await _collect(generate_sections_stream(_plan("A", "B"), "sys", "ctx", provider, usage_sink=usage))
    raw = "".join(i for i in items if isinstance(i, str))
    artifacts, chat = extract_artifacts(raw)
    assert "boom" not in artifacts[0].content  # errors never land in the document
    assert "Sección pendiente" in artifacts[0].content
    assert "Listo" in chat and "«B»" in chat
    assert usage["failed_sections"] == ["B"]
    statuses = [i for i in items if isinstance(i, AgentEvent) and i.type == "status"]
    assert [s.data["pending"] for s in statuses] == [False, True]

  @pytest.mark.asyncio
  async def test_history_and_images_reach_every_section(self):
    provider = _SectionProvider()
    history = [AIMessage(role="user", content="antes"), AIMessage(role="assistant", content="ok")]
    images = [{"data": "AAAA", "mime_type": "image/png"}]
    await _collect(generate_sections_stream(_plan("A"), "sys", "ctx", provider, history=history, images=images))
    sent = provider.calls[0]
    assert [m.content for m in sent[1:3]] == ["antes", "ok"]
    assert sent[-1].content[1]["image_url"]["url"] == "data:image/png;base64,AAAA"

  @pytest.mark.asyncio
  async def test_closing_the_stream_cancels_pending_sections(self):
    provider = _SectionProvider(slow={"B", "C"}, delay=5.0)
    gen = generate_sections_stream(_plan("A", "B", "C"), "sys", "ctx", provider, concurrency=3)
    assert (await gen.__anext__()).type == "plan"
    await gen.__anext__()  # chat intro + artifact opening
    assert "Contenido de A" in await gen.__anext__()  # B and C are still being written
    await asyncio.wait_for(gen.aclose(), timeout=2.0)  # would take 5 s if they were awaited
    assert sorted(provider.cancelled) == ["B", "C"]


class TestPlanDocument:
  @pytest.mark.asyncio
  async def test_failures_are_logged_and_return_none(self, caplog):
    class _Failing:
      default_model = "fast"

      async def complete(self, *args, **kwargs):
        raise RuntimeError("model gone")

    with caplog.at_level(logging.WARNING, logger="app.ai.section_generator"):
      assert await plan_document("genera", "ctx", provider=_Failing()) is None
    assert sum("model gone" in r.getMessage() for r in caplog.records) == 2

  @pytest.mark.asyncio
  async def test_history_is_sent_to_the_planner(self):
    seen = []

    class _Planner:
      default_model = "fast"

      async def complete(self, messages, **kwargs):
        seen.append(messages)
        return AICompletion(
          text=json.dumps({"title": "T", "extension": "docx", "sections": [{"title": "S1"}]}),
          provider="p", model="fast",
        )

    history = [AIMessage(role="user", content="haz un plan"), AIMessage(role="assistant", content="hecho")]
    plan = await plan_document("regenera", "ctx", provider=_Planner(), history=history)
    assert plan is not None and plan.sections[0].title == "S1"
    assert [m.content for m in seen[0][1:3]] == ["haz un plan", "hecho"]


class TestArtifactStreamSplitter:
  def _run(self, chunks):
    splitter = ArtifactStreamSplitter()
    events = []
    for chunk in chunks:
      events.extend(splitter.feed(chunk))
    events.extend(splitter.close())
    return events

  def test_tags_split_across_chunks(self):
    events = self._run(["<ch", "at>Hola</chat>\n<arti", 'fact title="Plan" extension="docx">\n# A', "\nB</arti", "fact>"])
    types = [t for t, _ in events]
    assert types[0] == "delta" and "artifact_start" in types and types[-1] == "artifact_end"
    chat = "".join(d["text"] for t, d in events if t == "delta")
    body = "".join(d["text"] for t, d in events if t == "artifact_delta")
    assert chat.strip() == "Hola"
    assert body == "\n# A\nB"
    start = next(d for t, d in events if t == "artifact_start")
    assert start == {"index": 0, "title": "Plan", "extension": "docx"}
    assert events[-1][1]["truncated"] is False

  def test_unclosed_artifact_is_ended_as_truncated(self):
    events = self._run(['<artifact title="X" extension="md">texto'])
    assert events[-1][0] == "artifact_end" and events[-1][1]["truncated"] is True

  def test_plain_text_with_angle_brackets_passes_through(self):
    events = self._run(["a < b y ", "c <d>"])
    assert "".join(d["text"] for _, d in events) == "a < b y c <d>"


class TestArtifactHelpers:
  def test_multiple_chat_blocks_are_joined(self):
    raw = '<chat>Uno</chat><artifact title="T" extension="md">x</artifact>\n<chat>Dos</chat>'
    _, chat = extract_artifacts(raw)
    assert chat == "Uno\n\nDos"

  def test_has_unclosed_artifact(self):
    assert has_unclosed_artifact('<artifact title="T" extension="md">x')
    assert not has_unclosed_artifact('<artifact title="T" extension="md">x</artifact>')
    assert not has_unclosed_artifact("sin artefactos")


class TestIterateUntilStopped:
  @pytest.mark.asyncio
  async def test_stop_while_waiting_cancels_the_source(self):
    cleaned = asyncio.Event()

    async def slow_source():
      try:
        yield "a"
        await asyncio.sleep(10)
        yield "b"
      finally:
        cleaned.set()

    stop = {"reason": None}

    async def should_stop():
      return stop["reason"]

    received = []
    with pytest.raises(StreamStopped) as exc_info:
      async for item in iterate_until_stopped(slow_source(), should_stop, poll_s=0.01):
        received.append(item)
        stop["reason"] = "disconnected"
    assert received == ["a"] and exc_info.value.reason == "disconnected"
    assert cleaned.is_set()

  @pytest.mark.asyncio
  async def test_source_errors_propagate(self):
    async def failing():
      yield 1
      raise ValueError("bad")

    async def never():
      return None

    with pytest.raises(ValueError):
      async for _ in iterate_until_stopped(failing(), never, poll_s=0.01):
        pass


class TestAiLogs:
  def test_list_logs_reads_newest_first_across_blocks(self, tmp_path, monkeypatch):
    monkeypatch.setattr(ai_logging, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(ai_logging, "_READ_BLOCK_BYTES", 16)  # force lines to straddle blocks
    (tmp_path / "2026-11-19.jsonl").write_text(json.dumps({"n": 0}) + "\n", encoding="utf-8")
    (tmp_path / "2026-11-20.jsonl").write_text(
      "".join(json.dumps({"n": i, "pad": "x" * i}) + "\n" for i in range(1, 6)), encoding="utf-8",
    )
    assert [e["n"] for e in ai_logging.list_logs(limit=4)] == [5, 4, 3, 2]
    assert [e["n"] for e in ai_logging.list_logs(limit=10)] == [5, 4, 3, 2, 1, 0]

  def test_summarize_logs(self):
    logs = [
      {"route": "plain", "duration_ms": 100, "ttft_ms": 10, "prompt_tokens": 100, "cached_tokens": 50},
      {"route": "plain", "duration_ms": 200, "ttft_ms": 20, "prompt_tokens": 100, "fallback_used": True},
      {"route": "sections", "duration_ms": 300, "error_code": "rate_limit", "finish_reason": "length"},
      {"refused": True},
    ]
    stats = ai_logging.summarize_logs(logs)
    assert stats["p50_duration_ms"] == 200 and stats["p95_duration_ms"] == 290
    assert stats["cache_hit_rate"] == 0.25
    assert stats["fallback_rate"] == round(1 / 3, 4)
    assert stats["error_rate"] == 0.25 and stats["truncation_rate"] == 0.25
    assert stats["routes"] == {"plain": 2, "sections": 1}

  @pytest.mark.asyncio
  async def test_log_writes_are_tracked_until_done(self, tmp_path, monkeypatch):
    monkeypatch.setattr(ai_logging, "LOGS_DIR", tmp_path)
    ai_logging.log_ai_call({"feature": "f"})
    assert ai_logging._PENDING_WRITES
    await ai_logging.flush_pending_logs()
    await asyncio.sleep(0)
    assert not ai_logging._PENDING_WRITES
    assert len(ai_logging.list_logs(limit=5)) == 1
