"""The streamed chat run: its packets in the legacy (v1) and the named-event (v2) wire formats."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.ai.artifacts import ArtifactStreamSplitter
from app.ai.events import AgentEvent as AIAgentEvent, sse_event
from app.ai.stream_control import StreamStopped, iterate_until_stopped
from app.db.repositories.history_repository import ChatRepository
from app.services.event_serializer import AgentRunEmitter, run_registry

from app.core.document_agent.chat_run import (
    AnswerOutcome,
    PreparedRun,
    error_code,
    finalize_answer,
    format_stream_error,
    log_request_failure,
    persist_turn,
    start_run,
)
from app.core.document_agent.rubric import evaluate_artifacts_rubric
from app.core.document_agent.payloads import AgenticPromptRequest, AgenticPromptResponse


CANCEL_POLL_S = 0.5


def _data_line(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


class ChatStream:
    """One streamed chat run: turns the runner's chunks into the v1 (legacy) or v2 (named events) wire format."""

    def __init__(
        self,
        request: Request,
        req: AgenticPromptRequest,
        chat_repo: ChatRepository,
        user_id: str | None,
        prepared: PreparedRun,
        v2: bool,
    ) -> None:
        self.request = request
        self.req = req
        self.chat_repo = chat_repo
        self.user_id = user_id
        self.prepared = prepared
        self.cfg = prepared.cfg
        self.v2 = v2
        self.run_id = req.run_id or f"run-{uuid.uuid4().hex[:12]}"
        self.conv_id = req.conversation_id or f"conv-{uuid.uuid4().hex[:12]}"
        self.emitter = AgentRunEmitter(run_id=self.run_id, conversation_id=self.conv_id)
        run_registry.register(self.emitter)
        self.last_disconnect_check = 0.0
        self.accumulated: List[str] = []
        self.splitter = ArtifactStreamSplitter()

    async def should_stop(self) -> Optional[str]:
        if self.emitter.is_cancelled:
            return "cancelled"
        now = time.monotonic()
        if now - self.last_disconnect_check >= CANCEL_POLL_S:
            self.last_disconnect_check = now
            if await self.request.is_disconnected():
                self.emitter.request_cancellation(reason="Client disconnected")
                return "disconnected"
        return None

    def _v1_packets_for(self, event: AIAgentEvent) -> List[str]:
        """Map typed runner events onto the legacy step events the v1 client understands."""
        emitter = self.emitter
        data = event.data
        if event.type == "tool_call":
            return [emitter.step_started(f"step-tool-{data.get('id', '')}", f"Usando herramienta: {data.get('name')}").to_sse_packet()]
        if event.type == "tool_result":
            return [emitter.step_completed(f"step-tool-{data.get('id', '')}", f"Herramienta {data.get('name')} finalizada").to_sse_packet()]
        if event.type == "plan":
            sections = data.get("sections") or []
            return [
                emitter.step_started(f"step-section-{i}", f"Sección: {title}").to_sse_packet()
                for i, title in enumerate(sections)
            ]
        if event.type == "status" and data.get("stage") == "section":
            index = data.get("section_index", 0)
            label = f"Sección: {data.get('section_title', '')}"
            if data.get("pending"):
                return [emitter.step_failed(f"step-section-{index}", label, "Sección pendiente").to_sse_packet()]
            return [emitter.step_completed(f"step-section-{index}", label).to_sse_packet()]
        return []

    def _opening_packets(self) -> List[str]:
        intent = self.prepared.intent
        if self.v2:
            return [sse_event("status", {
                "message": "Intención detectada",
                "stage": "classify",
                "intent": intent,
                "run_id": self.run_id,
                "conversation_id": self.conv_id,
            })]
        emitter = self.emitter
        return [
            emitter.started(task_profile=intent, prompt=self.prepared.query_text).to_sse_packet(),
            emitter.step_started("step-classify", "Clasificando intención...").to_sse_packet(),
            _data_line({"type": "intent", "intent": intent}),
            emitter.step_completed("step-classify", f"Intención: {intent}").to_sse_packet(),
            emitter.step_started("step-generate", "Generando contenido...").to_sse_packet(),
        ]

    def _chunk_packets(self, chunk: Any) -> List[str]:
        if isinstance(chunk, AIAgentEvent):
            return [chunk.to_sse()] if self.v2 else self._v1_packets_for(chunk)
        self.accumulated.append(chunk)
        if self.v2:
            return [sse_event(event_type, data) for event_type, data in self.splitter.feed(chunk)]
        return [self.emitter.message_delta(chunk).to_sse_packet(), _data_line({"type": "token", "text": chunk})]

    def _splitter_close_packets(self) -> List[str]:
        if not self.v2:
            return []
        return [sse_event(event_type, data) for event_type, data in self.splitter.close()]

    def _empty_response_packets(self) -> List[str]:
        err_text = "El modelo LLM no generó contenido. Verifica tu conexión o clave de API en Configuración."
        if self.v2:
            return [sse_event("error", {"code": "empty_response", "message": err_text})]
        return [self.emitter.failed("EMPTY_RESPONSE", err_text).to_sse_packet(), _data_line({"type": "error", "message": err_text})]

    def _artifact_packet(self, position: int, art: Dict[str, Any]) -> str:
        artifact_id = art.get("id") or f"art-{position}"
        return self.emitter.artifact_created(
            artifact_id=artifact_id,
            title=art.get("title", "Documento"),
            content=art.get("content", ""),
            extension=art.get("extension", "docx"),
        ).to_sse_packet()

    def _summary_packets(self, outcome: AnswerOutcome) -> tuple[List[str], Optional[float]]:
        """Artifact, rubric and completion packets of the legacy protocol, plus the artifacts' rubric score."""
        art_dicts = outcome.artifacts
        rubric_score = evaluate_artifacts_rubric(art_dicts)[0] if art_dicts else None
        if self.v2:
            return [], rubric_score
        emitter = self.emitter
        packets = [self._artifact_packet(position, art) for position, art in enumerate(art_dicts, start=1)]
        packets.append(emitter.step_completed("step-generate", "Generación completada").to_sse_packet())
        if art_dicts:
            packets.append(emitter.step_started("step-rubric", "Evaluando artefactos con rúbricas de calidad...").to_sse_packet())
            packets.append(emitter.step_completed("step-rubric", f"Calidad de artefacto: {rubric_score}/100").to_sse_packet())
        packets.append(emitter.completed(
            final_message=outcome.assistant_message, artifacts=art_dicts, sources=self.prepared.sources,
        ).to_sse_packet())
        return packets, rubric_score

    def _final_packets(self, full_content: str, outcome: AnswerOutcome, rubric_score: Optional[float]) -> List[str]:
        answer_clean = outcome.clean_answer or full_content
        final_response = {
            "answer": full_content,
            "intent_detected": self.prepared.intent,
            "requires_document_mutation": outcome.is_template,
            "document_updates": full_content if outcome.is_template else None,
            "answer_clean": answer_clean,
            "assistant_message": outcome.assistant_message,
            "artifacts": outcome.artifacts,
            "run_id": self.run_id,
            "conversation_id": self.conv_id,
            "route": self.cfg.run_info.get("route"),
            "truncated": bool(self.cfg.run_info.get("truncated")),
            "rubric_score": rubric_score,
        }
        if self.v2:
            return [sse_event("done", final_response)]
        return [_data_line({"type": "full", "data": final_response}), _data_line({"type": "done"})]

    def _stopped_packets(self, stop: StreamStopped) -> List[str]:
        # The runner was cancelled inside its task and already logged the cancellation.
        # "disconnected": nobody is listening, nothing to send.
        if stop.reason != "cancelled":
            return []
        if self.v2:
            return [sse_event("error", {"code": "cancelled", "message": "Cancelado por el usuario"})]
        return [self.emitter.cancelled("Cancelado por el usuario").to_sse_packet()]

    def _failure_packets(self, err: Exception) -> List[str]:
        log_request_failure(self.cfg, err, streamed=True)
        err_msg = format_stream_error(err)
        if self.v2:
            return [sse_event("error", {
                "code": error_code(err),
                "message": err_msg,
                "retry_after": getattr(err, "retry_after", None),
            })]
        return [self.emitter.failed("RUN_EXCEPTION", err_msg).to_sse_packet(), _data_line({"type": "error", "message": err_msg})]

    async def _complete(self, full_content: str):
        outcome = finalize_answer(full_content, self.prepared)
        packets, rubric_score = self._summary_packets(outcome)
        for packet in packets:
            yield packet
        await persist_turn(
            self.chat_repo,
            req=self.req,
            user_id=self.user_id,
            conv_id=self.conv_id,
            user_text=self.prepared.query_text,
            prepared=self.prepared,
            outcome=outcome,
            full_content=full_content,
        )
        for packet in self._final_packets(full_content, outcome, rubric_score):
            yield packet

    async def _run(self):
        for packet in self._opening_packets():
            yield packet
        runner = start_run(self.cfg)
        async for chunk in iterate_until_stopped(runner, self.should_stop, poll_s=CANCEL_POLL_S):
            for packet in self._chunk_packets(chunk):
                yield packet
        for packet in self._splitter_close_packets():
            yield packet

        full_content = "".join(self.accumulated)
        if not full_content.strip():
            for packet in self._empty_response_packets():
                yield packet
            return
        async for packet in self._complete(full_content):
            yield packet

    async def stream(self):
        try:
            async for packet in self._run():
                yield packet
        except StreamStopped as stop:
            for packet in self._stopped_packets(stop):
                yield packet
        except Exception as err:
            for packet in self._failure_packets(err):
                yield packet
        finally:
            run_registry.unregister(self.run_id)


def fast_operation_stream(response: AgenticPromptResponse, v2: bool) -> StreamingResponse:
    async def fast_gen():
        payload = response.model_dump(by_alias=True)
        yield sse_event("done", payload) if v2 else _data_line({"type": "full", "data": payload})

    return StreamingResponse(fast_gen(), media_type="text/event-stream")

