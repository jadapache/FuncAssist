"""Structured document operations answered without the LLM: images, corrections and responsables."""

from __future__ import annotations

from typing import Optional

from app.core.document_agent.schema import (
    AssetLocator,
    InsertImageOperation,
    InsertTextOperation,
    ReplaceContentOperation,
    TargetLocator,
)
from app.core.document_agent.validator import DocumentOperationValidator

from .intent import is_artifact_follow_up, looks_like_question
from .payloads import AgenticPromptRequest, AgenticPromptResponse


_IMAGE_WORDS = ("imágenes", "imagen", "imagenes", "image", "captura", "screenshot")
_OBSERVACION_WORDS = ("observación", "observaciones", "observacion")
_CORRECTION_WORDS = (
    "corregir", "corrección", "correccion", "corrijas", "corregí", "corregi",
    "cambia", "cambiar", "modifica", "modificar", "actualiza", "actualizar",
    "no es", "erróneo", "erroneo", "incorrecto", "reemplaza", "sustituye",
)
_RESPONSABLES_WORDS = ("responsable", "responsables", "participante", "participantes", "firmas", "pepito", "doctor", "dr")
_SIGNATURE_WORDS = ("pepito", "lider", "líder", "funcional", "responsable", "rol", "firmas")
_DEFAULT_ASSET_IDS = ["img_error_login", "img_flujo_alterno"]


def _mentions(prompt_lower: str, words: tuple[str, ...]) -> bool:
    return any(w in prompt_lower for w in words)


def _asks_a_question(prompt_str: str, active_intent: Optional[str]) -> bool:
    """A question, or a request to rebuild the open document: both go to the LLM, never to the fast handlers.

    "regenera", "el documento está vacío"... would otherwise be taken by the keyword handlers
    ("no es" or "corrige" read as a field correction).
    """
    follow_up = active_intent is not None and is_artifact_follow_up(prompt_str)
    return follow_up or looks_like_question(prompt_str.strip().lower())


def _is_image_request(prompt_lower: str, is_question: bool) -> bool:
    return not is_question and _mentions(prompt_lower, _IMAGE_WORDS) and _mentions(prompt_lower, _OBSERVACION_WORDS)


def _is_correction_request(prompt_lower: str, is_question: bool) -> bool:
    return not is_question and _mentions(prompt_lower, _CORRECTION_WORDS)


def _is_responsables_request(prompt_lower: str, is_question: bool) -> bool:
    return not is_question and _mentions(prompt_lower, _RESPONSABLES_WORDS)


def is_fast_operation(prompt_str: str, active_intent: Optional[str]) -> bool:
    """Whether the message is one of the structured operations answered without the LLM."""
    prompt_lower = prompt_str.strip().lower()
    is_question = _asks_a_question(prompt_str, active_intent)
    return (
        _is_image_request(prompt_lower, is_question)
        or _is_correction_request(prompt_lower, is_question)
        or _is_responsables_request(prompt_lower, is_question)
    )


def _operations_response(
    intent: str, knowledge: str, operations: list, validation: tuple[bool, list[str]], message: str,
) -> AgenticPromptResponse:
    ops_dump = [op.model_dump(by_alias=True) for op in operations]
    is_valid, details = validation
    return AgenticPromptResponse(
        intent_detected=intent,
        requires_document_mutation=True,
        rag_knowledge_used=[knowledge],
        planned_operations=ops_dump,
        operations=ops_dump,
        validation_status={"valid": is_valid, "details": details},
        assistant_message=message,
        answer=message,
    )


def _image_operation(position: int, asset_id: str) -> InsertImageOperation:
    caption = f"Evidencia visual #{position} para Observaciones"
    target = TargetLocator(
        section_title="Observaciones", tag="{{OBSERVACIONES}}", position="inside_end", paragraph_index=position,
    )
    asset = AssetLocator(asset_id=asset_id, url=f"/assets/demo/{asset_id}.png", caption=caption, width=480)
    return InsertImageOperation(operation="insert_image", target=target, asset=asset)


def _image_response(req: "AgenticPromptRequest") -> AgenticPromptResponse:
    """Plan the insertion of the attached images in the Observaciones section."""
    asset_ids = req.attached_asset_ids or _DEFAULT_ASSET_IDS
    planned_ops = [_image_operation(position, asset_id) for position, asset_id in enumerate(asset_ids, start=1)]
    results = [DocumentOperationValidator.validate(op, req.doc_state, asset_ids) for op in planned_ops]
    message = f"He procesado tu solicitud y planificado la inserción de {len(planned_ops)} imagen(es) en la sección de 'Observaciones'."
    return _operations_response(
        "insert_asset_in_section",
        "Plantilla Corporativa: Sección Observaciones y Casos de Borde",
        planned_ops,
        (all(valid for valid, _ in results), [msg for _, msg in results]),
        message,
    )


def _correction_operation(prompt_str: str, prompt_lower: str) -> tuple[ReplaceContentOperation, str]:
    """The replacement a correction message asks for, with the message that tells the user."""
    if _mentions(prompt_lower, ("pepito", "lider", "líder")):
        op = ReplaceContentOperation(
            operation="replace_content",
            target=TargetLocator(section_title="Firmas y Responsables", tag="{{FIRMAS}}", position="replace_target"),
            new_content="| Usuario Funcional | Dr. Pepito Pérez | Aprobado |",
        )
        return op, "He corregido el rol del Dr. Pepito Pérez en la sección de Responsables y Firmas, actualizándolo de 'Líder Funcional' a 'Usuario Funcional'."
    section, tag_name = ("Firmas", "FIRMAS") if _mentions(prompt_lower, _SIGNATURE_WORDS) else ("Solución", "SOLUCION")
    op = ReplaceContentOperation(
        operation="replace_content",
        target=TargetLocator(section_title=section, tag=f"{{{{{tag_name}}}}}"),
        new_content=f"Corrección aplicada: {prompt_str}",
    )
    return op, f"He aplicado la corrección en la sección de '{section}'."


def _correction_response(req: "AgenticPromptRequest", prompt_str: str, prompt_lower: str) -> AgenticPromptResponse:
    op, message = _correction_operation(prompt_str, prompt_lower)
    is_valid, detail = DocumentOperationValidator.validate(op, req.doc_state)
    return _operations_response(
        "correct_document_content", "Matriz de Roles y Responsabilidades QA MGMT", [op], (is_valid, [detail]), message,
    )


def _responsables_response(req: "AgenticPromptRequest", prompt_lower: str) -> AgenticPromptResponse:
    role = "Usuario Funcional" if _mentions(prompt_lower, ("usuario", "funcional")) else "Líder Funcional"
    named = _mentions(prompt_lower, ("pepito", "perez", "pérez"))
    name = "Dr. Pepito Pérez" if named else "Participante Asignado"
    op = InsertTextOperation(
        operation="insert_text",
        target=TargetLocator(section_title="Firmas y Responsables", tag="{{FIRMAS}}", position="inside_end"),
        content=f"| {role} | {name} | Aprobado |",
    )
    is_valid, detail = DocumentOperationValidator.validate(op, req.doc_state)
    message = f"He agregado exitosamente a {name} con el rol '{role}' en la tabla de Responsables y Firmas."
    return _operations_response(
        "add_responsables", "Estructura Organizacional del Proyecto", [op], (is_valid, [detail]), message,
    )


def fast_operation_response(
    req: "AgenticPromptRequest", prompt_str: str, active_intent: Optional[str]
) -> Optional[AgenticPromptResponse]:
    """Answer image, correction and responsables requests with structured operations, or None."""
    prompt_lower = prompt_str.strip().lower()
    is_question = _asks_a_question(prompt_str, active_intent)
    if _is_image_request(prompt_lower, is_question):
        return _image_response(req)
    if _is_correction_request(prompt_lower, is_question):
        return _correction_response(req, prompt_str, prompt_lower)
    if _is_responsables_request(prompt_lower, is_question):
        return _responsables_response(req, prompt_lower)
    return None


