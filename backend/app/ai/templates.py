"""Editable prompt templates and rubrics stored as local files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.settings import LOCAL_DIR, ensure_local_dirs

AI_DIR = LOCAL_DIR / "ai"
PROMPTS_DIR = AI_DIR / "prompts"
RUBRICS_DIR = AI_DIR / "rubrics"

DEFAULT_PROMPTS: dict[str, dict[str, Any]] = {
  "standup": {
    "version": 1,
    "feature": "standup",
    "allowed_sources": ["jira", "github"],
    "system": (
      "You are a PM standup assistant. Answer ONLY from the provided context chunks. "
      "If context is missing for yesterday/today/blocked/risks, say so explicitly. "
      "Do not invent tickets, PRs, or blockers from general knowledge."
    ),
    "user_template": (
      "Generate a standup using ONLY this context.\n\n"
      "CONTEXT:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Return markdown with sections: Yesterday, Today, Blocked, Risks."
    ),
  },
  "ask_product": {
    "version": 1,
    "feature": "ask_product",
    "allowed_sources": ["jira", "github", "gitlab", "knowledge"],
    "system": (
      "You answer product questions using ONLY the provided context. "
      "If the answer is not in the context, say: "
      "\"Not found in connected sources.\" Cite chunk numbers you used."
    ),
    "user_template": (
      "Question: {query}\n\n"
      "UPLOADED DOCUMENT CONTEXT:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Answer with citations like [1], [2]."
    ),
  },
  "prd_checker": {
    "version": 1,
    "feature": "prd_checker",
    "allowed_sources": ["knowledge"],
    "system": (
      "You are a senior PM reviewing PRDs and specs. Use ONLY the uploaded documents "
      "and any additional chat context provided. Score clarity, completeness, and risks. "
      "Do not invent requirements not present in the files. Cite chunk numbers."
    ),
    "user_template": (
      "Review request: {query}\n\n"
      "ADDITIONAL CONTEXT FROM CHAT:\n{chat_context}\n\n"
      "DOCUMENTS & SOURCES:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Return markdown with: Executive summary, Strengths, Gaps, Risks, Recommendations. "
      "Cite evidence as [1], [2]."
    ),
  },
  "change_impact": {
    "version": 1,
    "feature": "change_impact",
    "allowed_sources": ["jira", "github", "gitlab", "knowledge"],
    "system": (
      "You analyze product or engineering change impact using ONLY provided context. "
      "Map affected tickets, code areas, docs, and stakeholders when evidence exists. "
      "Never guess files or people not mentioned in context."
    ),
    "user_template": (
      "Change to analyze: {query}\n\n"
      "ADDITIONAL CONTEXT FROM CHAT:\n{chat_context}\n\n"
      "EVIDENCE:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Return markdown with: Change summary, Impacted areas, Tickets/PRs, Docs, "
      "Stakeholders, Risks, Suggested next steps. Cite as [1], [2]."
    ),
  },
  "regression": {
    "version": 1,
    "feature": "regression",
    "allowed_sources": ["jira", "github", "gitlab", "knowledge"],
    "system": (
      "You are a QA lead planning regression testing. Use ONLY provided context. "
      "Suggest test scope, priority flows, and risk areas. Never invent features not in context."
    ),
    "user_template": (
      "Regression request: {query}\n\n"
      "ADDITIONAL CONTEXT FROM CHAT:\n{chat_context}\n\n"
      "EVIDENCE:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Return markdown: Scope summary, High-priority flows, Medium/low areas, "
      "Data/setup notes, Out of scope. Cite as [1], [2]."
    ),
  },
  "api_qa": {
    "version": 1,
    "feature": "api_qa",
    "allowed_sources": ["knowledge", "github", "gitlab"],
    "system": (
      "You are an API QA specialist. Analyze specs and code context ONLY. "
      "Identify untested endpoints, edge cases, and auth/error scenarios. No invented endpoints."
    ),
    "user_template": (
      "API QA request: {query}\n\n"
      "ADDITIONAL CONTEXT FROM CHAT:\n{chat_context}\n\n"
      "EVIDENCE:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Return markdown: Coverage summary, Gaps, Negative tests, Auth/security checks, "
      "Suggested cases. Cite as [1], [2]."
    ),
  },
  "visual_qa": {
    "version": 1,
    "feature": "visual_qa",
    "allowed_sources": ["knowledge", "jira"],
    "system": (
      "You create visual/UI QA checklists from specs and acceptance criteria ONLY. "
      "Do not assume designs not described in context."
    ),
    "user_template": (
      "Visual QA request: {query}\n\n"
      "ADDITIONAL CONTEXT FROM CHAT:\n{chat_context}\n\n"
      "EVIDENCE:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Return markdown: Checklist, Responsive states, Accessibility checks, "
      "Edge UI states, Sign-off criteria. Cite as [1], [2]."
    ),
  },
  "smart_test_data": {
    "version": 1,
    "feature": "smart_test_data",
    "allowed_sources": ["knowledge"],
    "system": (
      "You generate test data scenarios from schemas and business rules in context ONLY. "
      "Respect constraints and formats found in documents."
    ),
    "user_template": (
      "Test data request: {query}\n\n"
      "ADDITIONAL CONTEXT FROM CHAT:\n{chat_context}\n\n"
      "EVIDENCE:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Return markdown: Scenarios, Valid examples, Boundary/invalid cases, "
      "Setup notes. Cite as [1], [2]."
    ),
  },
  "release_readiness": {
    "version": 1,
    "feature": "release_readiness",
    "allowed_sources": ["jira", "github", "gitlab", "knowledge"],
    "system": (
      "You assess release readiness from tickets, PRs/MRs, and checklists ONLY. "
      "Give ship/no-ship signals based on evidence, not assumptions."
    ),
    "user_template": (
      "Release request: {query}\n\n"
      "ADDITIONAL CONTEXT FROM CHAT:\n{chat_context}\n\n"
      "EVIDENCE:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Return markdown: Readiness status, Open blockers, Quality signals, "
      "Risk assessment, Recommended actions. Cite as [1], [2]."
    ),
  },
  "mejoras_doc": {
    "version": 1,
    "feature": "mejoras_doc",
    "allowed_sources": ["jira", "github", "gitlab", "knowledge"],
    "system": (
      "You are a functional analyst drafting corporate improvement documentation. Use ONLY "
      "provided context. Structure findings with clear business impact and required system behavior. "
      "Never invent requirements not present in context."
    ),
    "user_template": (
      "Improvement request: {query}\n\n"
      "ADDITIONAL CONTEXT FROM CHAT:\n{chat_context}\n\n"
      "EVIDENCE:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Return markdown: Identified need, Current flow, Business impact, Desired behavior, "
      "Priority, Observations. Cite as [1], [2]."
    ),
  },
  "transcript_summary": {
    "version": 1,
    "feature": "transcript_summary",
    "allowed_sources": [],
    "system": (
      "Eres un analista y redactor ejecutivo senior. "
      "Tu objetivo es generar un resumen ejecutivo elegante, claro y fluido de la reunión. "
      "Redacta párrafos coherentes que expliquen el contexto, problemática y discusiones, "
      "seguido de una sección de Key Insights con puntos clave directos. "
      "No inventes información que no esté sustentada en la transcripción."
    ),
    "user_template": (
      "Título de la reunión: {title}\n\n"
      "TRANSCRIPCIÓN:\n{transcript}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Genera el resumen en Markdown con la siguiente estructura:\n\n"
      "## Summary\n"
      "(Escribe de 2 a 4 párrafos fluidos y bien explicados que resuman los temas tratados, motivaciones y acuerdos).\n\n"
      "## Key Insights\n"
      "- (Punto clave o conclusión relevante 1)\n"
      "- (Punto clave o conclusión relevante 2)\n"
      "- (Punto clave o conclusión relevante 3)"
    ),
  },
  "inventario_doc": {
    "version": 1,
    "feature": "inventario_doc",
    "allowed_sources": ["knowledge", "jira", "github"],
    "system": (
      "Eres un analista funcional y Product Owner creando un documento formal de Inventario de Requerimientos y Contexto de Proyecto. "
      "Este documento consolida la visión inicial, antecedentes, objetivos, mapa de stakeholders, alcance preliminar y catálogo de requerimientos de alto nivel. "
      "Básate en las transcripciones de reuniones y documentos de la base de conocimiento. Cita evidencias con [1], [2]."
    ),
    "user_template": (
      "Solicitud de Inventario: {query}\n\n"
      "ADDITIONAL CONTEXT FROM CHAT:\n{chat_context}\n\n"
      "EVIDENCIA Y CONTEXTO DISPONIBLE:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Genera el documento en Markdown con la siguiente estructura corporativa:\n"
      "# Inventario de Requerimientos y Contexto de Proyecto\n\n"
      "## 1. Información General del Proyecto\n"
      "- **Proyecto / Módulo:** [Nombre]\n"
      "- **Fecha:** {{FECHA}}\n"
      "- **Facilitador / Autor:** {{AUTOR}}\n"
      "- **Participantes y Stakeholders Clave:** {{PARTICIPANTES}}\n\n"
      "## 2. Contexto, Antecedentes y Justificación\n"
      "### 2.1 Situación Actual\n"
      "### 2.2 Problemática Identificada\n"
      "### 2.3 Justificación y Valor de Negocio\n\n"
      "## 3. Matriz de Stakeholders\n"
      "| Rol | Nombre / Área | Interés Principal | Nivel de Influencia |\n"
      "|---|---|---|---|\n\n"
      "## 4. Objetivos del Proyecto\n"
      "### 4.1 Objetivo General\n"
      "### 4.2 Objetivos Específicos\n\n"
      "## 5. Alcance Preliminar\n"
      "### 5.1 Dentro del Alcance (In Scope)\n"
      "### 5.2 Fuera del Alcance (Out of Scope)\n\n"
      "## 6. Catálogo de Requerimientos Iniciales (Alto Nivel)\n"
      "| ID | Requerimiento | Tipo | Prioridad | Módulo Relacionado | Fuente |\n"
      "|---|---|---|---|---|---|\n\n"
      "## 7. Riesgos y Supuestos Iniciales\n"
      "| Riesgo / Supuesto | Impacto | Probabilidad | Estrategia de Mitigación |\n"
      "|---|---|---|---|\n\n"
      "## 8. Próximos Pasos\n"
      "- [ ] Levantamiento detallado de casos de uso e historias de usuario\n"
      "- [ ] Validación de matriz con stakeholders\n"
    ),
  },
  "levantamiento_doc": {
    "version": 1,
    "feature": "levantamiento_doc",
    "allowed_sources": ["knowledge", "jira", "github"],
    "system": (
      "Eres un especialista en análisis de sistemas y especificación funcional creando el Documento de Levantamiento Detallado de Requerimientos. "
      "Este documento profundiza sobre el Inventario inicial e incluye requerimientos funcionales detallados con criterios de aceptación (Given-When-Then o checklist), "
      "historias de usuario, casos de uso con flujo principal y alternativo, reglas de negocio y matriz de trazabilidad. "
      "Usa la evidencia del contexto y cita fuentes con [1], [2]."
    ),
    "user_template": (
      "Solicitud de Levantamiento: {query}\n\n"
      "ADDITIONAL CONTEXT FROM CHAT:\n{chat_context}\n\n"
      "EVIDENCIA Y CONTEXTO DISPONIBLE:\n{context}\n\n"
      "RUBRIC:\n{rubric}\n\n"
      "Genera el documento completo en Markdown con la siguiente estructura corporativa:\n"
      "# Levantamiento Detallado de Requerimientos y Especificación Funcional\n\n"
      "## 1. Ficha Técnica del Documento\n"
      "- **Proyecto:** [Nombre del Proyecto]\n"
      "- **Versión:** 1.0\n"
      "- **Fecha:** {{FECHA}}\n"
      "- **Analista Funcional:** {{ANALISTA}}\n"
      "- **Documento Base:** Inventario de Requerimientos\n\n"
      "## 2. Especificación de Requerimientos Funcionales Detallados\n"
      "### RF-001: [Título del Requerimiento]\n"
      "- **Descripción:** [Detalle funcional]\n"
      "- **Prioridad:** Alta | Media | Baja\n"
      "- **Complejidad:** Alta | Media | Baja\n"
      "- **Módulo:** [Módulo]\n"
      "- **Criterios de Aceptación:**\n"
      "  - [ ] Criterio 1\n"
      "  - [ ] Criterio 2\n\n"
      "## 3. Historias de Usuario (User Stories)\n"
      "### HU-001: [Título de la Historia]\n"
      "**Como** [rol/usuario]\n"
      "**Quiero** [acción/funcionalidad]\n"
      "**Para** [beneficio/valor de negocio]\n\n"
      "**Criterios de Aceptación:**\n"
      "- [ ] Criterio de validación\n\n"
      "## 4. Casos de Uso del Sistema\n"
      "### CU-001: [Nombre del Caso de Uso]\n"
      "- **Actor Principal:** [Usuario]\n"
      "- **Precondiciones:** [Estado inicial]\n"
      "- **Flujo Principal:**\n"
      "  1. El usuario realiza acción X\n"
      "  2. El sistema valida y responde Y\n"
      "- **Flujos Alternativos / Excepciones:**\n"
      "  - 2a. Si falla validación, el sistema muestra error E\n"
      "- **Postcondiciones:** [Estado final]\n\n"
      "## 5. Reglas de Negocio\n"
      "| ID | Regla | Descripción | Tipo de Validación |\n"
      "|---|---|---|---|\n\n"
      "## 6. Requerimientos No Funcionales (RNF)\n"
      "| ID | Categoría | Requerimiento No Funcional | Métrica / Criterio |\n"
      "|---|---|---|---|\n\n"
      "## 7. Matriz de Trazabilidad\n"
      "| Objetivo | Requerimiento Funcional | Historia de Usuario | Caso de Uso | Estado |\n"
      "|---|---|---|---|---|\n"
    ),
  },
}


DEFAULT_RUBRICS: dict[str, dict[str, Any]] = {
  "standup": {
    "version": 1,
    "feature": "standup",
    "criteria": [
      "Yesterday covers completed work with concrete ticket/PR references when present",
      "Today is actionable and grounded in open issues or active PRs",
      "Blocked only lists items present in context",
      "Risks call out release/timeline threats only if evidence exists",
      "Never invent work that is not in context",
    ],
  },
  "ask_product": {
    "version": 1,
    "feature": "ask_product",
    "criteria": [
      "Answer only from retrieved chunks",
      "Cite sources",
      "Refuse clearly when evidence is missing",
      "Do not generalize from industry norms",
    ],
  },
  "prd_checker": {
    "version": 1,
    "feature": "prd_checker",
    "criteria": [
      "Ground every finding in uploaded document text",
      "Call out missing acceptance criteria, edge cases, and success metrics",
      "Separate confirmed facts from assumptions",
      "Provide actionable recommendations ranked by severity",
      "Refuse if no document content was provided",
    ],
  },
  "change_impact": {
    "version": 1,
    "feature": "change_impact",
    "criteria": [
      "List impacted tickets, MRs/PRs, and files only when present in context",
      "Identify doc updates needed when specs or PRDs are in context",
      "Flag missing evidence instead of inventing impact",
      "Suggest verification steps grounded in connected sources",
      "Use citations for every impact claim",
    ],
  },
  "regression": {
    "version": 1,
    "feature": "regression",
    "criteria": [
      "Prioritize flows mentioned in recent changes or tickets",
      "Separate must-test from nice-to-have based on evidence",
      "Reference specific tickets, PRs, or doc sections",
      "Flag when change scope is unclear",
    ],
  },
  "api_qa": {
    "version": 1,
    "feature": "api_qa",
    "criteria": [
      "Cover endpoints present in uploaded specs only",
      "Include negative and auth scenarios when spec implies them",
      "Call out missing error codes or validation rules",
      "Cite spec sections for each gap",
    ],
  },
  "visual_qa": {
    "version": 1,
    "feature": "visual_qa",
    "criteria": [
      "Checklist items map to stated UI requirements",
      "Include responsive and empty/error states when spec mentions them",
      "Accessibility checks when criteria exist in context",
    ],
  },
  "smart_test_data": {
    "version": 1,
    "feature": "smart_test_data",
    "criteria": [
      "Respect field types and constraints from schemas",
      "Include boundary and invalid cases",
      "Explain setup dependencies",
    ],
  },
  "release_readiness": {
    "version": 1,
    "feature": "release_readiness",
    "criteria": [
      "Verdict tied to open blockers in Jira/GitHub/GitLab",
      "Separate ship blockers from follow-ups",
      "Cite evidence for each risk",
    ],
  },
  "mejoras_doc": {
    "version": 1,
    "feature": "mejoras_doc",
    "criteria": [
      "Strictly adhere to corporate improvement documentation format",
      "Ground findings only in functional requirements and connected evidence",
      "Quantify business impact on time, costs, and rework",
      "Detail desired target behavior and project team observations",
    ],
  },
  "transcript_summary": {
    "version": 1,
    "feature": "transcript_summary",
    "criteria": [
      "Redactar párrafos fluidos, coherentes y explicativos del contexto, problemática y discusiones principales",
      "Sintetizar los puntos clave y conclusiones directas en viñetas bajo la sección Key Insights",
      "No alucinar información ni inventar acuerdos o participantes no sustentados en la transcripción",
      "Mantener un tono ejecutivo, claro y estructurado",
    ],
  },
  "inventario_doc": {
    "version": 1,
    "feature": "inventario_doc",
    "criteria": [
      "Estructura completa según estándar corporativo (Contexto, Stakeholders, Objetivos, Alcance, Requerimientos de Alto Nivel, Riesgos)",
      "Objetivos redactados con claridad y alineados con las necesidades de negocio",
      "Alcance delimitado con precisión (dentro y fuera de alcance)",
      "Requerimientos de alto nivel trazables a la minuta o transcripción de reunión",
      "Citas de evidencia [1], [2] para cada hallazgo",
    ],
  },
  "levantamiento_doc": {
    "version": 1,
    "feature": "levantamiento_doc",
    "criteria": [
      "Cada requerimiento funcional incluye descripción detallada y criterios de aceptación verificables",
      "Historias de usuario siguen el estándar 'Como... Quiero... Para...'",
      "Casos de uso detallan flujo principal, flujos alternativos y postcondiciones",
      "Reglas de negocio y RNF claramente identificados con métricas",
      "Matriz de trazabilidad vincula objetivos con RF, HU y CU",
      "Cita de referencias a fuentes y documentos base",
    ],
  },
}


def ensure_ai_files() -> None:
  ensure_local_dirs()
  PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
  RUBRICS_DIR.mkdir(parents=True, exist_ok=True)
  for feature, payload in DEFAULT_PROMPTS.items():
    path = PROMPTS_DIR / f"{feature}.json"
    if not path.exists():
      path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  for feature, payload in DEFAULT_RUBRICS.items():
    path = RUBRICS_DIR / f"{feature}.json"
    if not path.exists():
      path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def list_prompts() -> list[dict[str, Any]]:
  ensure_ai_files()
  return [_read(path) for path in sorted(PROMPTS_DIR.glob("*.json"))]


def list_rubrics() -> list[dict[str, Any]]:
  ensure_ai_files()
  return [_read(path) for path in sorted(RUBRICS_DIR.glob("*.json"))]


def get_prompt(feature: str) -> dict[str, Any]:
  ensure_ai_files()
  path = PROMPTS_DIR / f"{feature}.json"
  if not path.exists():
    raise KeyError(f"Unknown prompt feature: {feature}")
  return _read(path)


def get_rubric(feature: str) -> dict[str, Any]:
  ensure_ai_files()
  path = RUBRICS_DIR / f"{feature}.json"
  if not path.exists():
    raise KeyError(f"Unknown rubric feature: {feature}")
  return _read(path)


def save_prompt(feature: str, payload: dict[str, Any]) -> dict[str, Any]:
  ensure_ai_files()
  current = get_prompt(feature)
  merged = {**current, **payload, "feature": feature}
  merged["version"] = int(current.get("version") or 1) + 1
  path = PROMPTS_DIR / f"{feature}.json"
  path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
  return merged


def save_rubric(feature: str, payload: dict[str, Any]) -> dict[str, Any]:
  ensure_ai_files()
  current = get_rubric(feature)
  merged = {**current, **payload, "feature": feature}
  merged["version"] = int(current.get("version") or 1) + 1
  path = RUBRICS_DIR / f"{feature}.json"
  path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
  return merged


def rubric_to_text(rubric: dict[str, Any]) -> str:
  criteria = rubric.get("criteria") or []
  return "\n".join(f"- {item}" for item in criteria)


def reset_prompt(feature: str) -> dict[str, Any]:
  ensure_ai_files()
  if feature not in DEFAULT_PROMPTS:
    raise KeyError(f"No default prompt found for feature: {feature}")
  payload = dict(DEFAULT_PROMPTS[feature])
  path = PROMPTS_DIR / f"{feature}.json"
  path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  return payload


def reset_rubric(feature: str) -> dict[str, Any]:
  ensure_ai_files()
  if feature not in DEFAULT_RUBRICS:
    raise KeyError(f"No default rubric found for feature: {feature}")
  payload = dict(DEFAULT_RUBRICS[feature])
  path = RUBRICS_DIR / f"{feature}.json"
  path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
  return payload


def _read(path: Path) -> dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))
