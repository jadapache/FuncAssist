"""Section-by-section document planning and generation."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.ai import section_generator as sg
from app.ai.events import AgentEvent
from app.ai.providers.base import AIMessage

PLAN_JSON = json.dumps({
  "title": "Plan de Pruebas", "extension": "docx", "chat_intro": "Listo",
  "sections": [{"title": "1. Alcance", "instructions": "x"}, {"title": "2. Riesgos"}, {"bad": 1}],
})


def test_candidate_detection():
  assert sg.is_section_generation_candidate("Generic_Plan", "")
  assert sg.is_section_generation_candidate("chat", "/plan algo")
  assert sg.is_section_generation_candidate("chat", "Por favor elabora un informe de avance")
  assert not sg.is_section_generation_candidate(None, "hola")


def test_parse_plan_json_variants():
  plan = sg._parse_plan_json(f"```json\n{PLAN_JSON}\n```")
  assert plan.title == "Plan de Pruebas" and [s.title for s in plan.sections] == ["1. Alcance", "2. Riesgos"]
  assert plan.sections[0].instructions == "x"
  assert sg._parse_plan_json(f"aquí va: {PLAN_JSON} gracias").chat_intro == "Listo"
  assert sg._parse_plan_json("no json") is None
  assert sg._parse_plan_json("[1, 2]") is None
  assert sg._parse_plan_json('{"title": "t", "extension": "md", "sections": []}') is None
  assert sg._parse_plan_json('{"extension": "md", "sections": [{"title": "a"}]}') is None
  assert sg._clean_json_response(None) == ""


def test_add_usage():
  sink = {}
  sg._add_usage(sink, SimpleNamespace(prompt_tokens=10, completion_tokens=True, cached_tokens=None, cost_usd=0.5))
  sg._add_usage(sink, SimpleNamespace(prompt_tokens=5, completion_tokens=2, cached_tokens=1, cost_usd=None))
  assert sink == {"prompt_tokens": 15, "completion_tokens": 2, "cached_tokens": 1, "cost_usd": 0.5, "llm_calls": 2}
  sg._add_usage(None, SimpleNamespace())
  sg._add_usage(sink, None)
  assert sink["llm_calls"] == 2


class _Prov:
  default_model = "m"

  def __init__(self, replies):
    self.replies = list(replies)
    self.calls = []

  async def complete(self, messages, **kw):
    self.calls.append((messages, kw))
    r = self.replies.pop(0)
    if isinstance(r, Exception):
      raise r
    return SimpleNamespace(text=r, prompt_tokens=1, completion_tokens=1, cached_tokens=0, cost_usd=0.0)


@pytest.mark.asyncio
async def test_plan_document_paths():
  assert await sg.plan_document("q", "ctx") is None
  history = [AIMessage(role="assistant", content="prev"), AIMessage(role="user", content="u"),
             AIMessage(role="assistant", content="a")]
  sink = {}
  prov = _Prov([PLAN_JSON])
  plan = await sg.plan_document("q", "ctx", provider=prov, history=history, usage_sink=sink)
  assert plan.title == "Plan de Pruebas" and sink["llm_calls"] == 1
  msgs, kw = prov.calls[0]
  assert [m.role for m in msgs] == ["system", "user", "assistant", "user"]
  assert kw["response_format"] == {"type": "json_object"}

  prov = _Prov(["basura", PLAN_JSON])
  assert (await sg.plan_document("q", "ctx", provider=prov)).title == "Plan de Pruebas"
  assert "response_format" not in prov.calls[1][1]

  prov = _Prov([RuntimeError("bad format"), "aún basura"])
  assert await sg.plan_document("q", "ctx", provider=prov) is None

  prov = _Prov([RuntimeError("a"), RuntimeError("b")])
  assert await sg.plan_document("q", "ctx", provider=prov) is None


def test_section_user_message_with_images():
  sec = sg.PlanSection("S", "i")
  assert isinstance(sg._section_user_message(sec, None).content, str)
  msg = sg._section_user_message(sec, [{"data": "data:image/png;base64,AA"}, {"dataUrl": "BB", "mime_type": "image/jpeg"}, {}])
  urls = [p["image_url"]["url"] for p in msg.content if p["type"] == "image_url"]
  assert urls == ["data:image/png;base64,AA", "data:image/jpeg;base64,BB"]


async def _collect(gen):
  return [item async for item in gen]


@pytest.mark.asyncio
async def test_generate_sections_in_order_with_pending():
  plan = sg.DocumentPlan("Doc", ".md", "", [sg.PlanSection("A"), sg.PlanSection("B")])

  class P:
    default_model = "m"

    async def complete(self, messages, **kw):
      text = messages[-1].content
      if "'A'" in text:
        await asyncio.sleep(0.01)  # A finishes after B but must still be emitted first
        return SimpleNamespace(text="contenido A", prompt_tokens=1)
      raise RuntimeError("B always fails")

  sink = {}
  items = await _collect(sg.generate_sections_stream(plan, "SYS", "CTX", P(), usage_sink=sink))
  assert isinstance(items[0], AgentEvent) and items[0].data["extension"] == "md"
  assert items[1].startswith("<chat>He elaborado") and 'extension="md"' in items[1]
  assert items[2] == "\n\n## A\ncontenido A\n"
  assert items[3].data["pending"] is False
  assert "Sección pendiente" in items[4] and items[5].data["pending"] is True
  assert items[6] == "\n</artifact>"
  assert "la sección «B»" in items[7]
  assert sink["failed_sections"] == ["B"]




@pytest.mark.asyncio
async def test_generate_sections_cancelled_early():
  plan = sg.DocumentPlan("Doc", "docx", "", [sg.PlanSection("A"), sg.PlanSection("B")])

  class Slow:
    default_model = "m"

    async def complete(self, messages, **kw):
      await asyncio.sleep(10)

  gen = sg.generate_sections_stream(plan, "S", "C", Slow())
  await gen.__anext__()
  await gen.__anext__()
  await gen.aclose()  # pending section tasks are cancelled without hanging
