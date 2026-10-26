# Plan Técnico de Implementación — FuncAssist

**Fecha:** 24 de Octubre de 2026  
**Rama:** `feat/blueprint-modernization`  
**Referencia:** [FuncAssist_Blueprint_Implementacion.md](file:///c:/Dev/FCV/FuncAssist/FuncAssist_Blueprint_Implementacion.md)

---

## 1. Estrategia de Modernización Incremental

Para mitigar riesgos y preservar la estabilidad operativa del sistema actual, la modernización se ejecuta en entregas atómicas verificables:
1. Mantener retrocompatibilidad en APIs mientras se introducen los nuevos contratos tipados.
2. Adaptar componentes existentes (`AgenticDocumentWorkspace`, `ArtifactsStudio`, `AgenticThinkingBubble`) en lugar de reescribirlos.
3. Asegurar validación de datos en fronteras (Pydantic en backend, TypeScript interfaces en frontend).

---

## 2. Mapa de Fases y Archivos a Modificar

```
┌────────────────────────────────────────────────────────────────────────┐
│ Fase 0: Auditoría, diagnóstico y línea base de compilación/tests      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Fase 1: Perfeccionamiento del Workspace y paneles responsive          │
│ Archivos: AgenticDocumentWorkspace.tsx, ChatHistorySidebar.tsx,        │
│           ArtifactsStudio.tsx, index.css                              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Fase 2: Protocolo y Contrato de Eventos Agénticos                      │
│ Archivos: backend/app/schemas/agent_events.py (nuevo)                 │
│           backend/app/services/event_serializer.py (nuevo)            │
│           backend/app/api/document_agent.py                           │
│           backend/tests/unit/test_agent_events.py (nuevo)             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Fase 3: Timeline Operativo y Consumo Frontend                          │
│ Archivos: frontend/src/features/document/hooks/useAgentRun.ts (nuevo) │
│           frontend/src/features/document/components/AgenticThinkingBubble.tsx
│           frontend/src/features/document/api/docAgentApi.ts           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Fase 4: Memoria Persistente y ContextBuilder                           │
│ Archivos: backend/app/models/memory.py (nuevo)                        │
│           backend/app/services/context_builder.py (nuevo)             │
│           backend/app/api/history.py                                  │
│           backend/tests/unit/test_context_builder.py (nuevo)          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Fase 5: Artefactos Estructurados, Schemas, Skills y Rúbricas           │
│ Archivos: backend/app/schemas/artifacts/improvement.py (nuevo)        │
│           backend/app/schemas/artifacts/inventory.py (nuevo)          │
│           backend/app/services/rubric_evaluator.py (nuevo)            │
│           backend/app/ai/templates.py                                 │
│           backend/tests/unit/test_artifact_schemas.py (nuevo)         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Fase 6: Motor de Plantillas DOCX/XLSX con Marcadores Declarativos     │
│ Archivos: backend/app/services/template_renderer/docx_engine.py (nuevo)│
│           backend/app/services/template_renderer/xlsx_engine.py (nuevo)│
│           backend/app/api/document_agent.py                           │
│           backend/tests/unit/test_template_renderers.py (nuevo)       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Fase 7: Entrada por Voz en Composer con Transcripción Editable         │
│ Archivos: frontend/src/features/transcription/components/VoiceInput.tsx│
│           frontend/src/features/document/components/AgenticDocumentWorkspace.tsx
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Fase 8 & 9: Seguridad, Observabilidad y Suite de Pruebas Integral      │
│ Archivos: backend/tests/e2e/test_agent_lifecycle.py (nuevo)           │
│           docs/operations-guide.md (nuevo)                            │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Criterios de Aceptación por Fase

- **Fase 0:** Diagnóstico completo, TypeScript compila sin errores, suite de pruebas base documentada.
- **Fase 1:** Los paneles se contraen/expanden preservando el estado de la conversación, accesibilidad por teclado y soporte responsive.
- **Fase 2:** Endpoints emiten SSE estructurado con secuencia monotónica (`run.started`, `run.step.*`, `message.delta`, `run.completed`).
- **Fase 3:** `useAgentRun` captura y despacha eventos al timeline sin timers artificiales. Soporta cancelación interactiva.
- **Fase 4:** `ContextBuilder` recupera solo memoria y conocimiento pertinente con control de presupuesto de tokens.
- **Fase 5:** Documento de Mejoras e Inventario producen objetos estructurados validados contra schemas antes de su renderizado.
- **Fase 6:** Renderizadores sustituyen marcadores `{{artifact.*}}` en DOCX y mapean celdas en XLSX sin romper estructura ni fórmulas existentes.
- **Fase 7:** El usuario puede pulsar el micrófono, dictar la solicitud, corregir la transcripción y enviarla con el mismo flujo del chat.
- **Fase 8 & 9:** Cobertura de tests unitarios y de integración de extremo a extremo aprobada.
