"""The document agent endpoints and helpers, checked through what they decide, build and send."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.ai.events import AgentEvent
from app.ai.runner import AgenticChatConfig
from app.api import document_agent as da
from app.core.document_agent.schema import DocumentSection
from app.schemas.artifacts import FunctionalImprovementArtifact, FunctionalInventoryArtifact


def req(**fields) -> da.AgenticPromptRequest:
  return da.AgenticPromptRequest(**fields)


def packet_json(packet: str) -> dict:
  assert packet.startswith("data: ") and packet.endswith("\n\n")
  return json.loads(packet[6:])


# -- is the message a follow-up, a question, an explicit intent ---------------------------------------

@pytest.mark.parametrize("prompt", ["", "   ", None])
def test_an_empty_message_is_not_a_follow_up(prompt):
  assert da.is_artifact_follow_up(prompt) is False


@pytest.mark.parametrize("prompt", [
  "regenera el documento", "vuelve a generar", "hazlo de nuevo", "rehaz esto", "el documento está vacío",
  "no tiene contenido", "complétalo", "completa el plan", "termina la sección", "corrige el informe",
  "continúa con el documento", "faltan secciones", "quedó cortado",
])
def test_messages_that_ask_to_redo_the_document_are_follow_ups(prompt):
  assert da.is_artifact_follow_up(prompt) is True


@pytest.mark.parametrize("prompt", ["hola", "gracias", "qué es un plan", "resume la reunión"])
def test_ordinary_messages_are_not_follow_ups(prompt):
  assert da.is_artifact_follow_up(prompt) is False


def test_the_active_intent_comes_from_the_latest_artifact():
  artifacts = [{"intent": "generic_plan"}, {"intent": "generic_report"}]
  assert da.infer_active_artifact_intent(artifacts) == "generic_report"


def test_an_artifact_without_a_known_intent_is_guessed_from_the_template_and_the_title():
  assert da.infer_active_artifact_intent([{"intent": "chat"}], template_id="t1") == "template_mutation"
  assert da.infer_active_artifact_intent([{"title": "Mi PLAN de pruebas"}]) == "generic_plan"
  assert da.infer_active_artifact_intent([{"title": "Notas"}]) == "generic_report"
  assert da.infer_active_artifact_intent([{}]) == "generic_report"


def test_a_conversation_without_artifacts_has_an_intent_only_with_a_current_document():
  assert da.infer_active_artifact_intent(None) is None
  assert da.infer_active_artifact_intent([]) is None
  assert da.infer_active_artifact_intent([], has_current_document=True) == "generic_report"
  assert da.infer_active_artifact_intent([], "t1", has_current_document=True) == "template_mutation"


@pytest.mark.parametrize("mode,expected", [
  ("plan", "generic_plan"), ("generic_plan", "generic_plan"), ("report", "generic_report"),
  ("informe", "generic_report"), ("generic_report", "generic_report"), ("chat", "chat"), ("qa", "chat"),
  ("template", "template_mutation"), ("template_mutation", "template_mutation"), ("custom_feature", "custom_feature"),
])
def test_an_explicit_mode_decides_the_intent(mode, expected):
  assert da.classify_prompt_intent_by_rules("hola", mode) == (expected, True)


@pytest.mark.parametrize("mode", ["auto", "default", None, ""])
def test_the_automatic_modes_leave_the_decision_to_the_rules(mode):
  assert da.classify_prompt_intent_by_rules("hola", mode) == ("chat", False)


@pytest.mark.parametrize("prompt,expected", [
  ("/plan algo", "generic_plan"), ("/generic_plan", "generic_plan"), ("/informe", "generic_report"),
  ("/report x", "generic_report"), ("/generic_report", "generic_report"), ("/plantilla x", "template_mutation"),
  ("/template", "template_mutation"), ("/template_mutation", "template_mutation"), ("/pregunta ¿qué?", "ask_product"),
  ("/question", "ask_product"), ("/ask", "ask_product"), ("/Otro cosa", "otro"),
])
def test_a_slash_command_decides_the_intent(prompt, expected):
  assert da.classify_prompt_intent_by_rules(prompt) == (expected, True)


def test_a_lone_slash_is_not_a_command():
  assert da.classify_prompt_intent_by_rules("/") == ("chat", False)


def test_a_follow_up_keeps_the_intent_of_the_open_document():
  assert da.classify_prompt_intent_by_rules("regenera el documento", None, None, "generic_plan") == ("generic_plan", True)
  assert da.classify_prompt_intent_by_rules("regenera", None, None, "chat") == ("chat", False)


def test_a_question_is_chat_and_undecided_while_a_document_is_open():
  assert da.classify_prompt_intent_by_rules("¿qué hora es", None, None, None) == ("chat", True)
  assert da.classify_prompt_intent_by_rules("cómo va", None, None, "generic_plan") == ("chat", False)
  assert da.classify_prompt_intent_by_rules("hola?", None, None, None) == ("chat", True)
  assert da.classify_prompt_intent_by_rules("dime algo", None, None, None) == ("chat", True)


def test_a_template_selection_turns_a_statement_into_a_template_mutation():
  assert da.classify_prompt_intent_by_rules("agrega esto", None, "t1") == ("template_mutation", True)
  assert da.classify_prompt_intent_by_rules("agrega esto", None, "  ") == ("chat", False)
  assert da.classify_prompt_intent_by_rules("¿y esto?", None, "t1") == ("chat", True)


@pytest.mark.parametrize("prompt,expected", [
  ("quiero un plan de prueba", "generic_plan"), ("elabora un plan", "generic_plan"),
  ("necesito el informe", "generic_report"), ("un resumen ejecutivo", "generic_report"),
  ("llena la plantilla", "template_mutation"), ("regenerar el documento", "template_mutation"),
])
def test_keywords_decide_the_intent(prompt, expected):
  assert da.classify_prompt_intent_by_rules(prompt) == (expected, True)


def test_classify_prompt_intent_returns_only_the_intent():
  assert da.classify_prompt_intent("/plan x") == "generic_plan"


@pytest.mark.parametrize("prompt,decided,active,expected", [
  ("cualquier cosa", True, "generic_plan", False),
  ("cualquier cosa", False, "generic_plan", True),
  ("revisa el documento", False, None, True),
  ("hola", False, None, False),
  (None, False, None, False),
])
def test_only_undecided_messages_about_a_document_go_to_the_model(prompt, decided, active, expected):
  assert da.needs_model_classification(prompt, decided, active) is expected


# -- templates ----------------------------------------------------------------------------------------

@pytest.fixture
def storage(monkeypatch):
  import app.core.template_storage as ts

  state = {"templates": [], "details": {}}
  monkeypatch.setattr(ts, "list_templates", AsyncMock(side_effect=lambda: state["templates"]))
  monkeypatch.setattr(ts, "get_template_detail", AsyncMock(side_effect=lambda i: state["details"].get(i)))
  monkeypatch.setattr(da, "_load_active_template_info", da.__dict__["_load_active_template_info"])
  return state


@pytest.mark.parametrize("detail", [None, {}, {"content": ""}, {"content": "  \n"}])
def test_a_template_without_text_has_no_content(detail):
  assert da._content_and_extension(detail) is None


@pytest.mark.parametrize("filename,extension", [("a.XLSX", "xlsx"), ("a.b.docx", "docx"), ("sin_extension", "docx"), ("", "docx")])
def test_the_extension_comes_from_the_file_name(filename, extension):
  assert da._content_and_extension({"content": " C ", "filename": filename}) == ("C", extension)
  assert da._content_and_extension({"content": "C"}) == ("C", "docx")


@pytest.mark.asyncio
async def test_the_selected_template_is_used_first(storage):
  storage["templates"] = [{"id": "other", "module": "mejoras"}]
  storage["details"] = {"t1": {"content": "elegida", "filename": "a.xlsx"}, "other": {"content": "otra"}}
  assert await da._load_active_template_info("t1") == ("elegida", "xlsx")


@pytest.mark.asyncio
async def test_without_a_usable_selection_the_templates_of_the_default_modules_come_first(storage):
  storage["templates"] = [{"id": "a", "module": "ventas"}, {"id": "b", "module": None}, {"id": "c", "module": "Requerimientos"}]
  storage["details"] = {"a": {"content": "A"}, "b": {"content": "B"}, "c": {"content": "C", "filename": "c.docx"}}
  assert await da._load_active_template_info("missing") == ("C", "docx")
  assert await da._load_active_template_info(None) == ("C", "docx")


@pytest.mark.asyncio
async def test_without_default_modules_any_template_with_text_is_used(storage):
  storage["templates"] = [{"id": "a", "module": "ventas"}, {"id": "b"}]
  storage["details"] = {"a": {"content": " "}, "b": {"content": "B"}}
  assert await da._load_active_template_info(None) == ("B", "docx")


@pytest.mark.asyncio
async def test_no_template_means_empty_content_and_the_default_extension(storage):
  assert await da._load_active_template_info(None) == ("", "docx")


# -- the request and response models ------------------------------------------------------------------

def test_the_prompt_text_prefers_the_prompt_then_the_query():
  def with_fields(prompt, query):
    request = req()
    request.prompt, request.query = prompt, query
    return request

  assert with_fields("p", "q").prompt_text == "p"
  assert with_fields(None, "q").prompt_text == "q"
  assert with_fields("", "").prompt_text == "" and with_fields(None, None).prompt_text == ""
  assert req(query="desde el cliente").prompt_text == "desde el cliente"


def test_the_document_state_falls_back_to_a_blank_document():
  assert req().doc_state.document_id == "doc-active"
  state = {"documentId": "d1", "sections": []}
  assert req(documentState=state).doc_state.document_id == "d1"


def test_the_xlsx_request_text_is_never_none():
  assert da.ExportXlsxRequest(markdown=None).text == ""
  assert da.ExportXlsxRequest(markdown="md").text == "md"


# -- attachments and validation endpoints ------------------------------------------------------------

class Upload:
  def __init__(self, filename, raw):
    self.filename = filename
    self._raw = raw

  async def read(self):
    return self._raw


@pytest.mark.asyncio
async def test_an_attachment_without_a_name_is_read_as_a_text_file(monkeypatch):
  seen = {}
  monkeypatch.setattr(da, "extract_text", lambda filename, raw: seen.update(filename=filename) or "contenido")
  result = await da.parse_chat_attachment(Upload(None, b"x"))
  assert result == {"filename": "archivo.txt", "content": "contenido", "char_count": 9}
  assert seen["filename"] == "archivo.txt"


def test_validating_needs_both_the_state_and_the_operation():
  state = {"documentId": "d"}
  operation = {"operation": "insert_text", "target": {}, "content": "x"}
  for payload in ({"state": state}, {"operation": operation}, {}, {"state": {}, "operation": operation}):
    with pytest.raises(HTTPException) as err:
      da.validate_operation(payload)
    assert err.value.status_code == 400
  assert da.validate_operation({"documentState": state, "operation": operation})["valid"] is True


# -- history ------------------------------------------------------------------------------------------

class HistoryRepo:
  def __init__(self, messages=None, fail=False):
    self.messages, self.fail, self.calls = messages or [], fail, []

  async def get_session_messages(self, *args, **kwargs):
    self.calls.append((args, kwargs))
    if self.fail:
      raise RuntimeError("db down")
    return self.messages


@pytest.mark.asyncio
async def test_the_stored_conversation_is_the_history_without_a_row_limit_and_scoped_to_the_user():
  repo = HistoryRepo([{"role": "user", "content": "hola", "id": "x"}, {"role": "assistant", "content": "ok"}])
  history = await da._resolve_chat_history(req(conversationId="c1"), repo, "u1")
  assert history == [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "ok"}]
  assert repo.calls == [(("c1",), {"limit": 0, "user_id": "u1"})]


@pytest.mark.asyncio
async def test_only_the_last_turns_with_text_from_the_user_or_the_assistant_are_kept():
  rows = [{"role": "user", "content": f"m{i}"} for i in range(70)]
  rows += [{"role": "system", "content": "s"}, {"role": "user", "content": ""}, {"role": "assistant", "content": None}]
  history = await da._resolve_chat_history(req(conversationId="c1"), HistoryRepo(rows), None)
  # The limit is applied to the stored rows before the ones without text are dropped.
  assert [m["content"] for m in history] == [f"m{i}" for i in range(13, 70)]


@pytest.mark.asyncio
async def test_a_failing_store_falls_back_to_what_the_client_sent():
  sent = [{"role": "user", "content": "del cliente"}]
  history = await da._resolve_chat_history(req(conversationId="c1", conversationHistory=sent), HistoryRepo(fail=True), None)
  assert history == sent


@pytest.mark.asyncio
async def test_an_empty_stored_conversation_falls_back_to_the_clients_history_then_the_context():
  sent = [{"role": "user", "content": "x"}]
  assert await da._resolve_chat_history(req(conversationId="c1", conversationHistory=sent), HistoryRepo(), None) == sent
  assert await da._resolve_chat_history(req(chatContext=["user: a", "assistant: b"]), HistoryRepo(), None) == ["user: a", "assistant: b"]
  assert await da._resolve_chat_history(req(chatContext="user: a"), HistoryRepo(), None) == ["user: a"]
  assert await da._resolve_chat_history(req(), HistoryRepo(), None) is None


# -- fast operations ----------------------------------------------------------------------------------

@pytest.mark.parametrize("prompt,active,expected", [
  ("regenera el documento", None, False),
  ("regenera el documento", "generic_plan", True),
  ("explica la sección", None, True),
  ("qué dice?", None, True),
  ("hola", None, False),
])
def test_questions_and_follow_ups_never_reach_the_fast_handlers(prompt, active, expected):
  assert da._asks_a_question(prompt, active) is expected


@pytest.mark.parametrize("prompt,fast", [
  ("agrega imágenes en las observaciones", True),
  ("agrega imágenes", False),
  ("revisa las observaciones", False),
  ("corrige el nombre", False),
  ("corregir el nombre", True),
  ("el campo es incorrecto", True),
  ("agrega al responsable", True),
  ("¿corregir el nombre?", False),
  ("regenera y corrige", False),
  ("hola", False),
])
def test_which_messages_are_structured_operations(prompt, fast):
  assert da._is_fast_operation(prompt, "generic_plan" if "regenera" in prompt else None) is fast


def test_a_question_about_an_operation_is_not_an_operation():
  assert not da._is_image_request("incluye imágenes en observaciones?", True)
  assert not da._is_correction_request("corregir", True)
  assert not da._is_responsables_request("responsable", True)
  assert da._is_image_request("imagen en observacion", False)
  assert da._is_correction_request("corregir", False) and da._is_responsables_request("responsable", False)


def test_the_image_operations_place_each_asset_in_order_with_its_caption():
  response = da._image_response(req(query="x", attachedAssetIds=["a1", "a2"]))
  first, second = response.planned_operations
  assert [first["asset"]["assetId"], second["asset"]["assetId"]] == ["a1", "a2"]
  assert [first["target"]["paragraphIndex"], second["target"]["paragraphIndex"]] == [1, 2]
  assert first["asset"]["caption"] == "Evidencia visual #1 para Observaciones" and second["asset"]["caption"].endswith("#2 para Observaciones")
  assert first["asset"]["url"] == "/assets/demo/a1.png" and first["asset"]["width"] == 480
  assert (first["target"]["sectionTitle"], first["target"]["tag"], first["target"]["position"]) == (
    "Observaciones", "{{OBSERVACIONES}}", "inside_end")
  assert response.operations == response.planned_operations
  assert response.intent_detected == "insert_asset_in_section" and response.requires_document_mutation is True
  assert response.rag_knowledge_used == ["Plantilla Corporativa: Sección Observaciones y Casos de Borde"]
  assert response.assistant_message == response.answer == (
    "He procesado tu solicitud y planificado la inserción de 2 imagen(es) en la sección de 'Observaciones'.")


def test_without_attached_assets_two_demo_images_are_planned():
  response = da._image_response(req(query="x"))
  assert [op["asset"]["assetId"] for op in response.planned_operations] == ["img_error_login", "img_flujo_alterno"]


def test_the_validation_of_the_planned_images_is_reported_for_each_one():
  blank = req(query="x", attachedAssetIds=["a1"])
  assert da._image_response(blank).validation_status["valid"] is True
  state = {"documentId": "d", "sections": [DocumentSection(id="s", title="Otra cosa").model_dump(by_alias=True)]}
  response = da._image_response(req(query="x", attachedAssetIds=["a1", "a2"], documentState=state))
  assert response.validation_status["valid"] is False and len(response.validation_status["details"]) == 2


def test_a_correction_about_the_leader_replaces_the_signature_row():
  response = da._correction_response(req(query="x"), "Corregir, pepito no es líder", "corregir, pepito no es líder")
  (op,) = response.planned_operations
  assert op["operation"] == "replace_content" and op["newContent"] == "| Usuario Funcional | Dr. Pepito Pérez | Aprobado |"
  assert (op["target"]["sectionTitle"], op["target"]["tag"], op["target"]["position"]) == (
    "Firmas y Responsables", "{{FIRMAS}}", "replace_target")
  assert response.intent_detected == "correct_document_content"
  assert response.rag_knowledge_used == ["Matriz de Roles y Responsabilidades QA MGMT"]
  assert response.assistant_message.startswith("He corregido el rol del Dr. Pepito Pérez")
  assert response.validation_status["valid"] is True and len(response.validation_status["details"]) == 1


@pytest.mark.parametrize("prompt,section,tag", [
  ("cambia el rol", "Firmas", "{{FIRMAS}}"), ("corrige la firmas", "Firmas", "{{FIRMAS}}"),
  ("cambia el texto", "Solución", "{{SOLUCION}}"),
])
def test_other_corrections_target_the_signatures_or_the_solution(prompt, section, tag):
  response = da._correction_response(req(query="x"), prompt, prompt)
  (op,) = response.planned_operations
  assert (op["target"]["sectionTitle"], op["target"]["tag"]) == (section, tag)
  assert op["newContent"] == f"Corrección aplicada: {prompt}"
  assert response.assistant_message == f"He aplicado la corrección en la sección de '{section}'."


@pytest.mark.parametrize("prompt,row", [
  ("agrega al doctor pepito perez usuario funcional", "| Usuario Funcional | Dr. Pepito Pérez | Aprobado |"),
  ("agrega al responsable", "| Líder Funcional | Participante Asignado | Aprobado |"),
  ("agrega a pérez como funcional", "| Usuario Funcional | Dr. Pepito Pérez | Aprobado |"),
  ("agrega al usuario", "| Usuario Funcional | Participante Asignado | Aprobado |"),
])
def test_a_responsable_is_added_with_the_role_and_name_the_message_gives(prompt, row):
  response = da._responsables_response(req(query="x"), prompt)
  (op,) = response.planned_operations
  assert op["operation"] == "insert_text" and op["content"] == row
  assert (op["target"]["sectionTitle"], op["target"]["tag"], op["target"]["position"]) == (
    "Firmas y Responsables", "{{FIRMAS}}", "inside_end")
  assert response.intent_detected == "add_responsables" and response.requires_document_mutation is True
  assert response.rag_knowledge_used == ["Estructura Organizacional del Proyecto"]
  assert "Participante Asignado" in response.assistant_message or "Pepito" in response.assistant_message


def test_the_fast_response_is_chosen_by_the_kind_of_request():
  intent = lambda prompt: getattr(da._fast_operation_response(req(query=prompt), prompt, None), "intent_detected", None)  # noqa: E731
  assert intent("incluye imágenes en observaciones") == "insert_asset_in_section"
  assert intent("corregir el valor") == "correct_document_content"
  assert intent("agrega al responsable") == "add_responsables"
  assert intent("hola") is None


# -- running the chat ---------------------------------------------------------------------------------

class RunRepo:
  def __init__(self):
    self.messages, self.sessions = [], []

  async def get_session_messages(self, *args, **kwargs):
    return []

  async def get_session_artifacts(self, *args, **kwargs):
    return []

  async def save_message(self, **kwargs):
    self.messages.append(kwargs)

  async def save_session(self, data):
    self.sessions.append(data)


def runner(*chunks, route="plain", exc=None):
  async def run(cfg):
    cfg.run_info["route"] = route
    for chunk in chunks:
      yield chunk
    if exc:
      raise exc
  return run


@pytest.fixture
def no_classifier(monkeypatch):
  monkeypatch.setattr(da, "classifier_enabled", lambda: False)
  monkeypatch.setattr(da, "_load_active_template_info", AsyncMock(return_value=("", "docx")))


@pytest.mark.asyncio
async def test_a_chat_turn_is_answered_and_stored_under_the_given_conversation(monkeypatch, no_classifier):
  monkeypatch.setattr(da, "run_agentic_chat_stream", runner("Hola ", "mundo"))
  repo = RunRepo()
  response = await da.handle_agentic_prompt(req(query="hola", conversationId="c7"), {"id": "u1"}, repo)
  assert (response.intent_detected, response.answer, response.assistant_message) == ("chat", "Hola mundo", "Hola mundo")
  assert response.requires_document_mutation is False and response.document_updates is None
  assert response.planned_operations == [] and response.operations == []
  assert response.validation_status == {"valid": True, "details": ["Agentic generation successful."]}
  assert response.rag_knowledge_used == ["knowledge"]
  assert {s["id"] for s in repo.sessions} == {"c7"} and {m["session_id"] for m in repo.messages} == {"c7"}


@pytest.mark.asyncio
async def test_a_turn_without_a_conversation_gets_a_new_one(monkeypatch, no_classifier):
  monkeypatch.setattr(da, "run_agentic_chat_stream", runner("ok"))
  repo = RunRepo()
  await da.handle_agentic_prompt(req(query="hola"), {"id": "u1"}, repo)
  assert repo.sessions[0]["id"].startswith("conv-") and len(repo.sessions[0]["id"]) == len("conv-") + 12


@pytest.mark.asyncio
async def test_a_template_turn_reports_the_document_update(monkeypatch, no_classifier):
  monkeypatch.setattr(da, "run_agentic_chat_stream", runner("# Documento"))
  response = await da.handle_agentic_prompt(req(query="genera el documento"), {"id": "u1"}, RunRepo())
  assert response.requires_document_mutation is True and response.document_updates == "# Documento"
  assert response.intent_detected == "template_mutation"


@pytest.mark.asyncio
async def test_a_failing_run_is_logged_as_not_streamed_and_answered_with_502(monkeypatch, no_classifier):
  monkeypatch.setattr(da, "run_agentic_chat_stream", runner(exc=RuntimeError("boom")))
  logged = []
  monkeypatch.setattr(da, "log_ai_call", logged.append)
  with pytest.raises(HTTPException) as err:
    await da.handle_agentic_prompt(req(query="hola"), {"id": "u1"}, RunRepo())
  assert err.value.status_code == 502 and logged[0]["streamed"] is False


def test_a_failure_is_logged_once_with_what_the_run_knew(monkeypatch):
  logged = []
  monkeypatch.setattr(da, "log_ai_call", logged.append)
  cfg = AgenticChatConfig(query="q", intent="chat", feature="f", conversation_id="c", provider="p0", model="m0")
  cfg.run_info.update(route="r", protocol="v2", intent_source="rules")
  da._log_request_failure(cfg, RuntimeError("x"), streamed=True)
  da._log_request_failure(cfg, RuntimeError("x"), streamed=True)
  (entry,) = logged
  assert entry["refused"] is False and entry["streamed"] is True and entry["stage"] == "endpoint"
  assert (entry["feature"], entry["intent"], entry["route"], entry["conversation_id"]) == ("f", "chat", "r", "c")
  assert (entry["provider"], entry["model"], entry["protocol"], entry["intent_source"]) == ("p0", "m0", "v2", "rules")
  assert cfg.run_info["logged"] is True


def test_the_failure_log_prefers_what_the_run_reports(monkeypatch):
  logged = []
  monkeypatch.setattr(da, "log_ai_call", logged.append)
  cfg = AgenticChatConfig(query="q", provider="p0", model="m0")
  cfg.run_info.update(provider="p1", model="m1", stage="generate")
  da._log_request_failure(cfg, RuntimeError("x"), streamed=False)
  assert (logged[0]["provider"], logged[0]["model"], logged[0]["stage"]) == ("p1", "m1", "generate")
  other = AgenticChatConfig(query="q")
  other.run_info["stage"] = "generate"
  da._log_request_failure(other, RuntimeError("x"), streamed=False, stage="custom")
  assert logged[1]["stage"] == "custom"


@pytest.mark.asyncio
async def test_a_failing_artifact_store_is_logged_with_its_traceback(caplog):
  class Broken(HistoryRepo):
    async def get_session_artifacts(self, *a, **k):
      raise RuntimeError("down")

  with caplog.at_level(logging.WARNING, logger=da.logger.name):
    intent = await da._resolve_active_artifact_intent(req(conversationId="c1"), Broken(), "u")
  assert intent is None and "Could not load artifacts of conversation c1" in caplog.text
  assert caplog.records[0].exc_info


@pytest.mark.asyncio
async def test_a_failing_turn_store_is_logged_with_its_traceback_and_does_not_fail_the_request(caplog):
  class Broken(RunRepo):
    async def save_message(self, **kwargs):
      raise RuntimeError("down")

  prepared = da._PreparedRun(AgenticChatConfig(query="q"), "chat", "q", ["knowledge"], "docx")
  outcome = da._AnswerOutcome([], "", "r", False, False)
  with caplog.at_level(logging.WARNING, logger=da.logger.name):
    await da._persist_turn(Broken(), req=req(), user_id="u", conv_id="c1", user_text="q", prepared=prepared,
                           outcome=outcome, full_content="r")
  assert "Could not persist chat turn of conversation c1" in caplog.text and caplog.records[0].exc_info


@pytest.mark.asyncio
async def test_the_session_title_and_feature_come_from_the_request():
  repo = RunRepo()
  prepared = da._PreparedRun(AgenticChatConfig(query="q"), "chat", "q", ["knowledge", "jira"], "docx")
  outcome = da._AnswerOutcome([], "", "respuesta", False, False)
  await da._persist_turn(repo, req=req(), user_id="u", conv_id="c1", user_text="x" * 50, prepared=prepared,
                         outcome=outcome, full_content="respuesta")
  assert repo.sessions == [{"id": "c1", "user_id": "u", "title": "x" * 35, "feature_slug": "mejoras_doc"}]
  assert repo.messages[1]["context_sources"] == [{"source": "knowledge"}, {"source": "jira"}]
  await da._persist_turn(repo, req=req(feature="inventario_doc"), user_id="u", conv_id="c1", user_text="q",
                         prepared=prepared, outcome=outcome, full_content="r")
  assert repo.sessions[1]["feature_slug"] == "inventario_doc"
  await da._persist_turn(repo, req=req(feature=None), user_id="u", conv_id="c1", user_text="q",
                         prepared=prepared, outcome=outcome, full_content="r")
  assert repo.sessions[2]["feature_slug"] == "general"


# -- intent with the fast model -----------------------------------------------------------------------

@pytest.fixture
def model(monkeypatch):
  calls = {"classify": [], "resolve": 0}
  monkeypatch.setattr(da, "classifier_enabled", lambda: True)

  def resolve(**kwargs):
    calls["resolve"] += 1
    return "fast-provider"

  async def classify(prompt, provider, active_intent, has_template):
    calls["classify"].append((prompt, provider, active_intent, has_template))
    return SimpleNamespace(intent="generic_report", cached=False)

  monkeypatch.setattr(da, "resolve_provider", resolve)
  monkeypatch.setattr(da, "classify_intent_with_model", classify)
  return calls


@pytest.mark.asyncio
async def test_the_model_is_asked_only_when_the_classifier_is_on_and_the_message_needs_it(monkeypatch, model):
  await da._resolve_intent(req(query="hola"), "u", None)  # small talk
  assert model["classify"] == []
  monkeypatch.setattr(da, "classifier_enabled", lambda: False)
  await da._resolve_intent(req(query="revisa el documento"), "u", None)
  assert model["classify"] == []
  monkeypatch.setattr(da, "classifier_enabled", lambda: True)
  intent, info = await da._resolve_intent(req(query="revisa el documento"), "u", None)
  assert intent == "generic_report" and len(model["classify"]) == 1
  assert info["intent_source"] == "model" and info["intent_rules"] == "chat"


@pytest.mark.asyncio
@pytest.mark.parametrize("template_id,expected", [(None, False), ("", False), ("  ", False), ("t1", True)])
async def test_the_model_is_told_whether_a_template_is_selected(model, template_id, expected):
  await da._resolve_intent(req(query="¿revisa el documento?", templateId=template_id), "u", "generic_plan")
  assert model["classify"][0][2:] == ("generic_plan", expected)


@pytest.mark.asyncio
async def test_the_classifier_time_is_reported_in_milliseconds(monkeypatch, model):
  ticks = iter([10.0, 10.0123456])
  monkeypatch.setattr(da.time, "perf_counter", lambda: next(ticks))
  _, info = await da._resolve_intent(req(query="revisa el documento"), "u", None)
  assert info["intent_classifier_ms"] == 12.3


# -- preparing the run --------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_runner_gets_the_request_with_its_defaults(no_classifier):
  prepared = await da._prepare_chat_run(req(query="hola"), RunRepo(), "u1", None)
  cfg = prepared.cfg
  assert (cfg.feature, cfg.sources, cfg.document_ids, cfg.chat_context, cfg.user_id) == ("mejoras_doc", ["knowledge"], [], None, "u1")
  assert prepared.sources == ["knowledge"] and (cfg.template_content, cfg.template_extension) == ("", "docx")


@pytest.mark.asyncio
async def test_the_runner_gets_what_the_request_asks_for(no_classifier):
  request = req(query="hola", feature="inventario_doc", sources=["jira"], documentIds=["d1"], chatContext=["a", "b"],
                conversationId="c1", provider="openai", model="gpt")
  cfg = (await da._prepare_chat_run(request, RunRepo(), "u1", None)).cfg
  assert (cfg.feature, cfg.sources, cfg.document_ids, cfg.chat_context) == ("inventario_doc", ["jira"], ["d1"], "a\nb")
  assert (cfg.conversation_id, cfg.provider, cfg.model) == ("c1", "openai", "gpt")


@pytest.mark.asyncio
async def test_the_artifact_follow_up_is_flagged_only_for_the_open_documents_intent(no_classifier):
  repo = RunRepo()
  flagged = await da._prepare_chat_run(req(query="regenera el documento"), repo, "u", "generic_plan")
  assert flagged.cfg.run_info["artifact_follow_up"] is True
  other = await da._prepare_chat_run(req(query="regenera el documento", mode="report"), repo, "u", "generic_plan")
  assert other.intent == "generic_report" and "artifact_follow_up" not in other.cfg.run_info
  plain = await da._prepare_chat_run(req(query="hola"), repo, "u", "chat")
  assert "artifact_follow_up" not in plain.cfg.run_info
  none = await da._prepare_chat_run(req(query="regenera el documento"), repo, "u", None)
  assert "artifact_follow_up" not in none.cfg.run_info


def test_chat_context_is_joined_or_converted():
  assert da._chat_context_text(None) is None and da._chat_context_text([]) is None and da._chat_context_text("") is None
  assert da._chat_context_text(["a", "b"]) == "a\nb" and da._chat_context_text("texto") == "texto"


def test_local_models_are_not_run_in_the_backend():
  with pytest.raises(HTTPException) as err:
    da._reject_unsupported_model(req(model="llama.GGUF"))
  assert err.value.status_code == 400
  da._reject_unsupported_model(req(model="gpt", provider="openai"))
  da._reject_unsupported_model(req())


# -- the streamed run ---------------------------------------------------------------------------------

def make_stream(v2=False, request=None, **config):
  cfg = AgenticChatConfig(query="consulta", **config)
  prepared = da._PreparedRun(cfg, "chat", "consulta", ["knowledge"], "docx")
  request = request or SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
  return da._ChatStream(request, req(query="consulta", runId="run-1", conversationId="c1"), RunRepo(), "u1", prepared, v2)


@pytest.mark.asyncio
async def test_the_disconnect_poll_runs_only_after_the_poll_interval(monkeypatch):
  request = SimpleNamespace(is_disconnected=AsyncMock(return_value=True))
  stream = make_stream(request=request)
  clock = {"now": 0.4}
  monkeypatch.setattr(da.time, "monotonic", lambda: clock["now"])
  assert await stream.should_stop() is None and request.is_disconnected.await_count == 0
  clock["now"] = da.CANCEL_POLL_S
  assert await stream.should_stop() == "disconnected" and request.is_disconnected.await_count == 1
  da.run_registry.unregister("run-1")


@pytest.mark.asyncio
async def test_a_recent_poll_is_not_repeated(monkeypatch):
  request = SimpleNamespace(is_disconnected=AsyncMock(return_value=False))
  stream = make_stream(request=request)
  clock = {"now": 100.0}
  monkeypatch.setattr(da.time, "monotonic", lambda: clock["now"])
  assert await stream.should_stop() is None
  clock["now"] = 100.1
  assert await stream.should_stop() is None and request.is_disconnected.await_count == 1
  da.run_registry.unregister("run-1")


def test_the_v1_client_gets_step_packets_for_tool_and_section_events():
  stream = make_stream()

  def steps(event):
    return [(p["type"], p["data"]["step_id"], p["data"]["label"]) for p in map(packet_json, stream._v1_packets_for(event))]

  assert steps(AgentEvent(type="tool_call", data={"id": "1", "name": "buscar"})) == [
    ("run.step.started", "step-tool-1", "Usando herramienta: buscar")]
  assert steps(AgentEvent(type="tool_result", data={"id": "1", "name": "buscar"})) == [
    ("run.step.completed", "step-tool-1", "Herramienta buscar finalizada")]
  assert steps(AgentEvent(type="plan", data={"sections": ["A", "B"]})) == [
    ("run.step.started", "step-section-0", "Sección: A"), ("run.step.started", "step-section-1", "Sección: B")]
  assert steps(AgentEvent(type="plan", data={})) == []
  assert steps(AgentEvent(type="status", data={"stage": "section", "section_index": 2, "section_title": "C"})) == [
    ("run.step.completed", "step-section-2", "Sección: C")]
  assert steps(AgentEvent(type="status", data={"stage": "section"})) == [("run.step.completed", "step-section-0", "Sección: ")]
  pending = stream._v1_packets_for(AgentEvent(type="status", data={"stage": "section", "section_index": 3, "section_title": "D", "pending": True}))
  assert packet_json(pending[0])["type"] == "run.step.failed" and packet_json(pending[0])["data"]["details"] == "Sección pendiente"
  assert stream._v1_packets_for(AgentEvent(type="status", data={"stage": "other"})) == []
  assert stream._v1_packets_for(AgentEvent(type="usage", data={})) == []
  da.run_registry.unregister("run-1")


def test_the_opening_packets_announce_the_intent_in_each_protocol():
  v2 = make_stream(v2=True)
  assert v2._opening_packets()[0].startswith("event: status")
  assert '"intent": "chat"' in v2._opening_packets()[0] and '"run_id": "run-1"' in v2._opening_packets()[0]
  v1 = make_stream()
  types = [packet_json(p).get("type") for p in v1._opening_packets()]
  assert types == ["run.started", "run.step.started", "intent", "run.step.completed", "run.step.started"]
  assert packet_json(v1._opening_packets()[0])["data"]["initial_prompt"] == "consulta"
  da.run_registry.unregister("run-1")


def test_the_summary_of_a_v1_run_lists_artifacts_rubric_and_completion():
  stream = make_stream()
  outcome = da._AnswerOutcome(
    [{"id": "", "title": "Plan", "content": "x" * 60, "extension": "md"}, {"id": "a2"}], "limpio", "mensaje", False, True)
  packets, score = stream._summary_packets(outcome)
  decoded = [packet_json(p) for p in packets]
  assert [p["type"] for p in decoded] == [
    "artifact.created", "artifact.created", "run.step.completed", "run.step.started", "run.step.completed", "run.completed"]
  first, second = decoded[0]["data"], decoded[1]["data"]
  assert (first["artifact_id"], first["title"], first["extension"]) == ("art-1", "Plan", "md")
  assert (second["artifact_id"], second["title"], second["content"], second["extension"]) == ("a2", "Documento", "", "docx")
  assert score == 67.5 and decoded[4]["data"]["label"] == "Calidad de artefacto: 67.5/100"
  assert decoded[5]["data"]["final_message"] == "mensaje" and decoded[5]["data"]["sources_used"] == ["knowledge"]
  da.run_registry.unregister("run-1")


def test_a_v1_run_without_artifacts_skips_the_rubric_and_has_no_score():
  packets, score = make_stream()._summary_packets(da._AnswerOutcome([], "", "m", False, False))
  assert [packet_json(p)["type"] for p in packets] == ["run.step.completed", "run.completed"] and score is None
  da.run_registry.unregister("run-1")


def test_a_v2_run_has_no_summary_packets_but_still_a_score():
  stream = make_stream(v2=True)
  packets, score = stream._summary_packets(da._AnswerOutcome([{"title": "T", "content": "x" * 60}], "", "m", False, True))
  assert packets == [] and score == 85.0
  assert stream._summary_packets(da._AnswerOutcome([], "", "m", False, False)) == ([], None)
  da.run_registry.unregister("run-1")


def test_the_final_response_carries_the_clean_answer_or_the_full_one():
  stream = make_stream(v2=True)
  stream.cfg.run_info.update(route="r", truncated=True)
  outcome = da._AnswerOutcome([{"title": "T"}], "", "mensaje", True, True)
  (packet,) = stream._final_packets("completo", outcome, 90.0)
  body = json.loads(packet.split("data: ", 1)[1])
  assert body["answer_clean"] == "completo" and body["answer"] == "completo" and body["document_updates"] == "completo"
  assert (body["route"], body["truncated"], body["rubric_score"], body["run_id"], body["conversation_id"]) == ("r", True, 90.0, "run-1", "c1")
  clean = da._AnswerOutcome([], "limpio", "m", False, False)
  assert json.loads(stream._final_packets("completo", clean, None)[0].split("data: ", 1)[1])["answer_clean"] == "limpio"
  v1 = make_stream()._final_packets("completo", clean, None)
  assert [packet_json(p)["type"] for p in v1] == ["full", "done"]
  da.run_registry.unregister("run-1")


@pytest.mark.asyncio
async def test_a_failing_stream_is_logged_as_streamed(monkeypatch):
  logged = []
  monkeypatch.setattr(da, "log_ai_call", logged.append)
  stream = make_stream()
  packets = stream._failure_packets(RuntimeError("x"))
  assert logged[0]["streamed"] is True and packet_json(packets[1])["type"] == "error"
  da.run_registry.unregister("run-1")


# -- structured artifacts and the rubric --------------------------------------------------------------

def test_a_json_answer_or_its_fenced_json_is_found():
  assert da._json_object_text('  {"a": 1}  ') == '{"a": 1}'
  assert da._json_object_text('texto ```json\n{"a": 1}\n``` más') == '{"a": 1}'
  assert da._json_object_text("{abc") is None and da._json_object_text("abc}") is None
  assert da._json_object_text("```json\nno es objeto\n```") is None and da._json_object_text("nada") is None


IMPROVEMENT = {"problem_statement": "p", "business_objective": "b"}


@pytest.mark.parametrize("data,kind", [
  (IMPROVEMENT, FunctionalImprovementArtifact),
  ({**IMPROVEMENT, "acceptance_criteria": []}, FunctionalImprovementArtifact),
  ({"project_name": "p"}, FunctionalInventoryArtifact),
  ({"project_name": "p", "modules": []}, FunctionalInventoryArtifact),
])
def test_the_structured_artifact_kind_follows_its_fields(data, kind):
  parsed = da._try_parse_structured_artifact(json.dumps({"title": "T", **data}), "otro")
  assert isinstance(parsed, kind) and parsed.title == "T"


def test_a_structured_answer_missing_required_fields_is_not_an_artifact():
  assert da._try_parse_structured_artifact('{"acceptance_criteria": [], "title": "T"}', "T") is None
  assert da._try_parse_structured_artifact('{"modules": []}', "T") is None


def test_the_title_and_id_are_filled_in_when_missing():
  parsed = da._try_parse_structured_artifact('{"project_name": "p"}', "Mi título")
  assert parsed.title == "Mi título" and parsed.artifact_id.startswith("art-")
  assert da._try_parse_structured_artifact('{"project_name": "p"}', "").title == "Documento"
  fenced = da._try_parse_structured_artifact('```json\n{"project_name": "p"}\n```', "T")
  assert fenced.project_name == "p"


def test_other_json_or_broken_json_is_not_a_structured_artifact():
  assert da._try_parse_structured_artifact('{"otra": 1}', "T") is None
  assert da._try_parse_structured_artifact("{no json}", "T") is None
  assert da._try_parse_structured_artifact("texto libre", "T") is None


@pytest.mark.parametrize("length,score", [(49, 50.0), (50, 85.0)])
def test_free_text_is_scored_by_its_length(length, score):
  assert da._rubric_for_artifact({"content": "x" * length}) == (score, [])


def test_the_average_rubric_score_and_feedback():
  assert da._evaluate_artifacts_rubric([]) == (100.0, "Sin artefactos estructurados")
  score, feedback = da._evaluate_artifacts_rubric([{"content": "x" * 60}, {"content": "corto"}])
  assert (score, feedback) == (67.5, "Artefactos aprobados por rúbrica.")


# -- exports ------------------------------------------------------------------------------------------

def test_a_json_export_is_parsed_only_when_it_is_an_object():
  assert da._resolve_export_data('{"a": 1}', None, "T") == {"a": 1, "title": "T"}
  assert da._resolve_export_data('{"a": 1, "title": "X"}', None, "T")["title"] == "X"
  for content in ("{abc", "abc}", "[1]", "{roto}"):
    assert da._resolve_export_data(content, None, "T") == {"title": "T", "content": content, "markdown": content}
  assert da._resolve_export_data("x", {"k": 1}, "T") == {"k": 1, "title": "T"}


def test_an_export_uses_the_template_only_when_the_file_is_of_the_right_kind(monkeypatch):
  from pathlib import Path

  rendered = []
  monkeypatch.setattr(da.DocxTemplateRenderer, "render", staticmethod(lambda path, data: rendered.append(path) or b"docx"))
  monkeypatch.setattr(da.XlsxTemplateRenderer, "render", staticmethod(lambda path, data: rendered.append(path) or b"xlsx"))
  monkeypatch.setattr(da, "create_mejoras_docx", lambda text, title: b"mejoras")
  monkeypatch.setattr(da, "create_levantamiento_docx", lambda text, title: b"levantamiento")
  monkeypatch.setattr(da, "create_inventario_xlsx", lambda **kw: b"inventario")
  monkeypatch.setattr(da, "create_qa_matrix_xlsx", lambda **kw: b"matriz")

  paths = {"t-docx": Path("a.DOCX"), "t-xlsx": Path("a.xlsx"), "t-none": None}
  monkeypatch.setattr(da, "get_template_file_path", lambda tid: paths.get(tid))

  docx = lambda **kw: da._generate_docx_bytes(da.ExportDocxRequest(**kw))  # noqa: E731
  assert docx(templateId="t-docx") == b"docx" and docx(templateId="t-xlsx") == b"mejoras"
  assert docx(templateId="t-none") == b"mejoras" and docx(title="Levantamiento X") == b"levantamiento"

  xlsx = lambda **kw: da._generate_xlsx_bytes(da.ExportXlsxRequest(title="Otra hoja", **kw))  # noqa: E731
  assert xlsx(templateId="t-xlsx") == b"xlsx" and xlsx(templateId="t-docx", markdown="") == b"matriz"
  assert xlsx(templateId="t-none", markdown="") == b"matriz" and xlsx(markdown="texto") == b"inventario"
  assert da._generate_xlsx_bytes(da.ExportXlsxRequest(title="Inventario de X", markdown="")) == b"inventario"
  assert rendered == [paths["t-docx"], paths["t-xlsx"]]


def test_an_artifact_left_open_when_the_stream_ends_is_closed_in_v2_only():
  v2 = make_stream(v2=True)
  v2._chunk_packets('<artifact title="T" extension="md">texto sin cerrar')
  closing = v2._splitter_close_packets()
  assert closing and any("artifact_end" in packet for packet in closing)
  v1 = make_stream()
  v1._chunk_packets('<artifact title="T" extension="md">texto sin cerrar')
  assert v1._splitter_close_packets() == []
  for stream in (v1, v2):
    da.run_registry.unregister(stream.run_id)


def test_a_json_value_that_is_not_an_object_is_exported_as_text():
  for content in ("[1]", "123", '"texto"', "null"):
    assert da._resolve_export_data(content, None, "T") == {"title": "T", "content": content, "markdown": content}
  assert da._resolve_export_data(None, None, "T") == {"title": "T", "content": None, "markdown": None}
