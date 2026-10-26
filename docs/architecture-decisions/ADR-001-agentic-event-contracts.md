# ADR-001: Protocolo Versionado de Eventos Agénticos (SSE)

**Estado:** Aceptado  
**Fecha:** 2026-10-24  
**Contexto:**  
Actualmente, el backend envía texto parcial (`{"type": "token", "text": "..."}`) y el frontend simula transiciones de estado de pensamiento mediante temporizadores fijos en el cliente (`useAgenticGeneration.ts`). Esto genera inconsistencias visuales, falta de trazabilidad de los pasos reales (RAG, mutaciones, validaciones) y fragilidad ante fallos intermedios.

**Decisión:**  
Implementar un protocolo estructurado de eventos transmitido sobre Server-Sent Events (SSE) con las siguientes características:
1. **Envelope unificado:**
   - `version: int` (iniciando en 1)
   - `run_id: str` (identificador único de la ejecución)
   - `conversation_id: str`
   - `sequence: int` (monotónicamente creciente por run)
   - `type: str` (evento discriminado, ej. `run.started`, `run.step.started`, `run.step.completed`, `message.delta`, `artifact.created`, `run.completed`, `run.failed`)
   - `timestamp: str` (ISO 8601 UTC)
   - `data: dict` (payload validado con esquemas Pydantic)
2. **Propagación de cancelación:** Cancelar la conexión o solicitar `POST /api/runs/{run_id}/cancel` propaga la señal al orquestador del servidor para evitar ejecuciones huérfanas.
3. **Compatibilidad:** Se mantiene soporte temporal para endpoints legados mientras el frontend migra a `useAgentRun`.

**Consecuencias:**
- El frontend renderiza el progreso real del agente en tiempo real.
- No se expone cadena de pensamiento privada del modelo; solo etapas y evidencias operacionales.
- Cada paso completado o fallido queda auditado por ejecución.
