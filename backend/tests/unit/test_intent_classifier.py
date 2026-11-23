"""Fast-model intent classification: gating, label parsing, per-message cache and endpoint wiring."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.ai import intent_classifier
from app.ai.intent_classifier import classify_intent_with_model, parse_label
from app.ai.logging import summarize_logs
from app.ai.providers.base import AICompletion
from app.api import document_agent
from app.api.document_agent import (
  AgenticPromptRequest,
  classify_prompt_intent_by_rules,
  needs_model_classification,
)


class _LabelProvider:
  default_model = "fast"

  def __init__(self, reply="SEGUIMIENTO", delay=0.0):
    self.reply = reply
    self.delay = delay
    self.calls = 0

  async def complete(self, messages, **kwargs):
    self.calls += 1
    if self.delay:
      await asyncio.sleep(self.delay)
    return AICompletion(text=self.reply, provider="p", model="fast")


@pytest.fixture(autouse=True)
def _clean_cache():
  intent_classifier.clear_cache()
  yield
  intent_classifier.clear_cache()


class TestRuleDecisions:
  def test_keyword_matches_are_decided(self):
    assert classify_prompt_intent_by_rules("genera un plan de pruebas") == ("generic_plan", True)

  def test_fallthrough_is_undecided(self):
    assert classify_prompt_intent_by_rules("agrega una sección de riesgos") == ("chat", False)

  def test_questions_are_undecided_only_with_an_active_document(self):
    assert classify_prompt_intent_by_rules("¿le agregas una tabla?") == ("chat", True)
    assert classify_prompt_intent_by_rules("¿le agregas una tabla?", active_artifact_intent="generic_plan") == ("chat", False)

  def test_small_talk_never_reaches_the_model(self):
    assert not needs_model_classification("gracias", decided=False, active_artifact_intent=None)
    assert needs_model_classification("necesito una matriz de casos de prueba", decided=False, active_artifact_intent=None)
    assert needs_model_classification("gracias", decided=False, active_artifact_intent="generic_report")
    assert not needs_model_classification("genera un plan", decided=True, active_artifact_intent="generic_plan")


class TestLabelParsing:
  def test_follow_up_maps_to_the_active_intent(self):
    assert parse_label("SEGUIMIENTO", active_intent="generic_report", has_template=False) == "generic_report"
    assert parse_label("seguimiento", active_intent=None, has_template=False) is None

  def test_labels_inside_extra_text(self):
    assert parse_label("Etiqueta: PLAN.", active_intent=None, has_template=False) == "generic_plan"

  def test_template_label_requires_an_active_template(self):
    assert parse_label("PLANTILLA", active_intent=None, has_template=False) is None
    assert parse_label("PLANTILLA", active_intent=None, has_template=True) == "template_mutation"

  def test_unknown_reply_is_rejected(self):
    assert parse_label("no sé", active_intent=None, has_template=False) is None


class TestModelClassification:
  @pytest.mark.asyncio
  async def test_result_is_cached_per_message(self):
    provider = _LabelProvider("SEGUIMIENTO")
    first = await classify_intent_with_model("agrega riesgos", provider=provider, active_intent="generic_plan")
    second = await classify_intent_with_model("Agrega riesgos ", provider=provider, active_intent="generic_plan")
    assert first.intent == "generic_plan" and not first.cached
    assert second.cached and provider.calls == 1

  @pytest.mark.asyncio
  async def test_timeout_keeps_the_rules(self, monkeypatch):
    monkeypatch.setenv("AI_INTENT_CLASSIFIER_TIMEOUT_S", "0.5")
    provider = _LabelProvider(delay=2.0)
    assert await classify_intent_with_model("agrega riesgos", provider=provider, active_intent="generic_plan") is None


class TestEndpointWiring:
  @pytest.mark.asyncio
  async def test_model_overrides_undecided_rules_and_is_recorded(self):
    req = AgenticPromptRequest(query="agrega una sección de riesgos al plan")
    provider = _LabelProvider("SEGUIMIENTO")
    with patch.object(document_agent, "resolve_provider", return_value=provider):
      intent, info = await document_agent._resolve_intent(req, "u1", "generic_plan")
    assert intent == "generic_plan"
    assert info["intent_source"] == "model" and info["intent_rules"] == "chat"

  @pytest.mark.asyncio
  async def test_decided_messages_skip_the_model(self):
    req = AgenticPromptRequest(query="genera un plan de pruebas")
    with patch.object(document_agent, "resolve_provider") as resolve:
      intent, info = await document_agent._resolve_intent(req, "u1", None)
    assert intent == "generic_plan" and info == {"intent_source": "rules"}
    resolve.assert_not_called()

  @pytest.mark.asyncio
  async def test_classifier_can_be_disabled(self, monkeypatch):
    monkeypatch.setenv("AI_LLM_INTENT_CLASSIFIER", "off")
    req = AgenticPromptRequest(query="agrega una sección de riesgos al plan")
    with patch.object(document_agent, "resolve_provider") as resolve:
      intent, _ = await document_agent._resolve_intent(req, "u1", "generic_plan")
    assert intent == "chat"
    resolve.assert_not_called()


class TestStatsBreakdowns:
  def test_protocol_and_intent_source_distribution(self):
    stats = summarize_logs([
      {"protocol": "v2", "intent_source": "rules"},
      {"protocol": "v1", "intent_source": "model"},
      {"protocol": "v2", "intent_source": "model_cache"},
    ])
    assert stats["protocols"] == {"v2": 2, "v1": 1}
    assert stats["intent_sources"] == {"rules": 1, "model": 1, "model_cache": 1}
