"""Default factory seeds for AI prompt templates and evaluation rubrics (en español).

Extracted following SOLID Single Responsibility Principle (SRP)
so template persistence/management and default template definitions
remain decoupled.
"""

from __future__ import annotations

from typing import Any

DEFAULT_PROMPTS: dict[str, dict[str, Any]] = {
  "standup": {
    "version": 1,
    "feature": "standup",
    "allowed_sources": ["jira", "github"],
    "system": (
      "Eres un asistente de reuniones diarias (Daily Standup) para equipos de QA y desarrollo. "
      "Responde ÚNICAMENTE a partir de los fragmentos de contexto proporcionados. "
      "Si falta contexto para lo realizado ayer, lo planeado para hoy, bloqueos o riesgos, indícalo explícitamente. "
      "No inventes tickets, pull requests ni impedimentos a partir de conocimientos generales."
    ),
    "user_template": (
      "Genera el reporte de standup utilizando ÚNICAMENTE este contexto.\n\n"
      "CONTEXTO:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
      "Devuelve el resultado en Markdown con las siguientes secciones: Ayer, Hoy, Bloqueos, Riesgos."
    ),
  },
  "ask_product": {
    "version": 1,
    "feature": "ask_product",
    "allowed_sources": ["jira", "github", "gitlab", "knowledge"],
    "system": (
      "Respondes preguntas sobre el producto utilizando ÚNICAMENTE el contexto provisto. "
      "Si la respuesta no se encuentra en el contexto, indica claramente: "
      "\"Información no encontrada en las fuentes conectadas.\" Cita siempre los números de fragmento utilizados."
    ),
    "user_template": (
      "Pregunta: {query}\n\n"
      "CONTEXTO DE DOCUMENTOS CARGADOS:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
      "Responde citando las fuentes con formato numérico como [1], [2]."
    ),
  },
  "prd_checker": {
    "version": 1,
    "feature": "prd_checker",
    "allowed_sources": ["knowledge"],
    "system": (
      "Eres un Product Manager senior revisando documentos de requerimientos de producto (PRD) y especificaciones técnicas. "
      "Utiliza ÚNICAMENTE los documentos cargados y el contexto adicional del chat. "
      "Evalúa claridad, completitud y riesgos. No inventes requerimientos que no estén presentes en los archivos. "
      "Cita los números de fragmento como evidencia."
    ),
    "user_template": (
      "Solicitud de revisión: {query}\n\n"
      "CONTEXTO ADICIONAL DEL CHAT:\n{chat_context}\n\n"
      "DOCUMENTOS Y FUENTES:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
      "Devuelve el análisis en Markdown con: Resumen ejecutivo, Fortalezas, Brechas identificadas, Riesgos, Recomendaciones. "
      "Cita la evidencia como [1], [2]."
    ),
  },
  "change_impact": {
    "version": 1,
    "feature": "change_impact",
    "allowed_sources": ["jira", "github", "gitlab", "knowledge"],
    "system": (
      "Analizas el impacto de cambios en producto o ingeniería utilizando ÚNICAMENTE el contexto provisto. "
      "Identifica tickets afectados, áreas del código, documentación y partes interesadas (stakeholders) solo cuando exista evidencia. "
      "Nunca supongas archivos ni personas que no figuren en el contexto."
    ),
    "user_template": (
      "Cambio a analizar: {query}\n\n"
      "CONTEXTO ADICIONAL DEL CHAT:\n{chat_context}\n\n"
      "EVIDENCIA:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
      "Devuelve el reporte en Markdown con: Resumen del cambio, Áreas impactadas, Tickets/PRs relacionados, Documentación, "
      "Stakeholders, Riesgos, Próximos pasos sugeridos. Cita como [1], [2]."
    ),
  },
  "regression": {
    "version": 1,
    "feature": "regression",
    "allowed_sources": ["jira", "github", "gitlab", "knowledge"],
    "system": (
      "Eres un QA Lead planificando pruebas de regresión. Utiliza ÚNICAMENTE el contexto proporcionado. "
      "Sugiere el alcance de pruebas, flujos prioritarios y áreas de riesgo. Jamás inventes funcionalidades no sustentadas."
    ),
    "user_template": (
      "Solicitud de regresión: {query}\n\n"
      "CONTEXTO ADICIONAL DEL CHAT:\n{chat_context}\n\n"
      "EVIDENCIA:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
      "Devuelve el plan en Markdown con: Resumen de alcance, Flujos de alta prioridad, Áreas de media/baja prioridad, "
      "Notas de datos y configuración, Fuera de alcance. Cita evidencias como [1], [2]."
    ),
  },
  "api_qa": {
    "version": 1,
    "feature": "api_qa",
    "allowed_sources": ["knowledge", "github", "gitlab"],
    "system": (
      "Eres un especialista en aseguramiento de calidad (QA) de APIs. Analiza ÚNICAMENTE especificaciones técnicas y código de contexto. "
      "Identifica endpoints sin cobertura, casos de borde, validaciones y escenarios de autenticación/error. No inventes endpoints inexistentes."
    ),
    "user_template": (
      "Solicitud de QA de API: {query}\n\n"
      "CONTEXTO ADICIONAL DEL CHAT:\n{chat_context}\n\n"
      "EVIDENCIA:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
      "Devuelve el análisis en Markdown con: Resumen de cobertura, Brechas detectadas, Pruebas negativas, Validaciones de seguridad y autenticación, "
      "Casos de prueba sugeridos. Cita como [1], [2]."
    ),
  },
  "visual_qa": {
    "version": 1,
    "feature": "visual_qa",
    "allowed_sources": ["knowledge", "jira"],
    "system": (
      "Creas listas de verificación (checklists) de QA visual y UI basadas ÚNICAMENTE en especificaciones y criterios de aceptación. "
      "No asumas diseños o comportamientos que no estén explícitamente detallados en el contexto."
    ),
    "user_template": (
      "Solicitud de QA Visual: {query}\n\n"
      "CONTEXTO ADICIONAL DEL CHAT:\n{chat_context}\n\n"
      "EVIDENCIA:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
      "Devuelve el reporte en Markdown con: Checklist visual, Estados responsivos, Verificaciones de accesibilidad, "
      "Estados de borde de interfaz (UI), Criterios de aprobación. Cita como [1], [2]."
    ),
  },
  "smart_test_data": {
    "version": 1,
    "feature": "smart_test_data",
    "allowed_sources": ["knowledge"],
    "system": (
      "Generas escenarios y datos de prueba inteligentes a partir de esquemas y reglas de negocio presentes ÚNICAMENTE en el contexto. "
      "Respeta estrictamente restricciones, tipos de datos y formatos encontrados en los documentos."
    ),
    "user_template": (
      "Solicitud de datos de prueba: {query}\n\n"
      "CONTEXTO ADICIONAL DEL CHAT:\n{chat_context}\n\n"
      "EVIDENCIA:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
      "Devuelve los datos en Markdown con: Escenarios propuestos, Ejemplos de datos válidos, Casos de borde e inválidos, "
      "Instrucciones de preparación del entorno. Cita como [1], [2]."
    ),
  },
  "release_readiness": {
    "version": 1,
    "feature": "release_readiness",
    "allowed_sources": ["jira", "github", "gitlab", "knowledge"],
    "system": (
      "Evalúas la preparación para liberación a producción (Release Readiness) basándote ÚNICAMENTE en tickets, Pull/Merge Requests y checklists del contexto. "
      "Emite veredictos de pase/no-pase (Ship/No-Ship) fundamentados en evidencia objetiva y nunca en suposiciones."
    ),
    "user_template": (
      "Solicitud de evaluación de release: {query}\n\n"
      "CONTEXTO ADICIONAL DEL CHAT:\n{chat_context}\n\n"
      "EVIDENCIA:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
      "Devuelve el dictamen en Markdown con: Estado de preparación, Bloqueos abiertos, Indicadores de calidad, "
      "Evaluación de riesgos, Acciones recomendadas antes de liberar. Cita evidencias como [1], [2]."
    ),
  },
  "mejoras_doc": {
    "version": 1,
    "feature": "mejoras_doc",
    "allowed_sources": ["jira", "github", "gitlab", "knowledge"],
    "system": (
      "Eres un analista funcional redactando documentación corporativa de mejoras del sistema. Usa ÚNICAMENTE "
      "el contexto provisto. Estructura los hallazgos con un impacto de negocio medible y el comportamiento esperado del sistema. "
      "Nunca inventes requerimientos que no figuren en el contexto."
    ),
    "user_template": (
      "Solicitud de documentación de mejora: {query}\n\n"
      "CONTEXTO ADICIONAL DEL CHAT:\n{chat_context}\n\n"
      "EVIDENCIA:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
      "Devuelve el documento en Markdown con: Necesidad identificada, Flujo actual, Impacto en el negocio, Comportamiento esperado, "
      "Prioridad sugerida, Observaciones clave. Cita como [1], [2]."
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
      "RÚBRICA:\n{rubric}\n\n"
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
      "CONTEXTO ADICIONAL DEL CHAT:\n{chat_context}\n\n"
      "EVIDENCIA Y CONTEXTO DISPONIBLE:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
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
      "CONTEXTO ADICIONAL DEL CHAT:\n{chat_context}\n\n"
      "EVIDENCIA Y CONTEXTO DISPONIBLE:\n{context}\n\n"
      "RÚBRICA:\n{rubric}\n\n"
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
      "La sección Ayer cubre el trabajo completado con referencias concretas a tickets/PRs cuando existan",
      "La sección Hoy es accionable y basada en tareas abiertas o PRs activos",
      "La sección Bloqueos enumera únicamente impedimentos presentes en el contexto",
      "La sección Riesgos alerta sobre amenazas al cronograma o release solo si hay evidencia",
      "Nunca inventar tareas o avances que no figuren en el contexto",
    ],
  },
  "ask_product": {
    "version": 1,
    "feature": "ask_product",
    "criteria": [
      "Responder únicamente a partir de los fragmentos recuperados",
      "Citar fuentes documentales con formato [1], [2]",
      "Declarar claramente la ausencia de información cuando no haya evidencia",
      "No generalizar basándose en normas o prácticas de la industria si no están en el texto",
    ],
  },
  "prd_checker": {
    "version": 1,
    "feature": "prd_checker",
    "criteria": [
      "Fundamentar cada hallazgo en el texto del documento cargado",
      "Señalar criterios de aceptación faltantes, casos de borde y métricas de éxito ausentes",
      "Diferenciar claramente los hechos confirmados de las suposiciones",
      "Proporcionar recomendaciones accionables priorizadas por nivel de severidad",
      "Rechazar la solicitud si no se proporcionó contenido del documento",
    ],
  },
  "change_impact": {
    "version": 1,
    "feature": "change_impact",
    "criteria": [
      "Listar tickets impactados, Merge/Pull Requests y archivos solo si figuran en el contexto",
      "Identificar actualizaciones de documentación requeridas según especificaciones o PRDs",
      "Alertar sobre falta de evidencia en lugar de suponer impactos",
      "Sugerir pasos de verificación fundamentados en las fuentes conectadas",
      "Incluir citas de evidencia para cada afirmación de impacto",
    ],
  },
  "regression": {
    "version": 1,
    "feature": "regression",
    "criteria": [
      "Priorizar flujos mencionados en cambios recientes, commits o tickets",
      "Separar pruebas obligatorias de pruebas secundarias basándose en evidencia",
      "Referenciar tickets específicos, PRs o secciones de documentación",
      "Alertar cuando el alcance del cambio sea ambiguo o insuficiente",
    ],
  },
  "api_qa": {
    "version": 1,
    "feature": "api_qa",
    "criteria": [
      "Cubrir únicamente endpoints presentes en las especificaciones cargadas",
      "Incluir escenarios negativos y validaciones de autenticación cuando la especificación los implique",
      "Señalar códigos de error faltantes o reglas de validación no documentadas",
      "Citar secciones de la especificación técnica para cada brecha identificada",
    ],
  },
  "visual_qa": {
    "version": 1,
    "feature": "visual_qa",
    "criteria": [
      "Los elementos del checklist se vinculan directamente con requerimientos de interfaz declarados",
      "Incluir estados responsivos, estados vacíos y manejo de errores cuando el diseño los mencione",
      "Verificaciones de accesibilidad cuando existan criterios de contraste o navegación en el contexto",
    ],
  },
  "smart_test_data": {
    "version": 1,
    "feature": "smart_test_data",
    "criteria": [
      "Respetar tipos de campos, longitudes y restricciones de esquemas y modelos",
      "Incluir casos límite, valores de borde y datos deliberadamente inválidos",
      "Explicar dependencias previas de configuración o datos maestros necesarios",
    ],
  },
  "release_readiness": {
    "version": 1,
    "feature": "release_readiness",
    "criteria": [
      "El veredicto se vincula estrictamente a bloqueos abiertos en Jira, GitHub o GitLab",
      "Separar bloqueos críticos de release de tareas secundarias de seguimiento",
      "Citar evidencia explícita para cada riesgo reportado",
    ],
  },
  "mejoras_doc": {
    "version": 1,
    "feature": "mejoras_doc",
    "criteria": [
      "Apegarse estrictamente a la estructura corporativa de documentación de mejoras",
      "Fundamentar los hallazgos únicamente en requerimientos funcionales y evidencia conectada",
      "Cuantificar el impacto del negocio en tiempo, costos operativos y retrabajo",
      "Detallar con precisión el comportamiento esperado del sistema y las observaciones del equipo",
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
