# ADR-002: Generación de Artefactos Guiada por Esquemas Tipados

**Estado:** Aceptado  
**Fecha:** 2026-10-24  
**Contexto:**  
En la versión actual, el modelo LLM genera Markdown libre que luego el cliente intenta desmenuzar con expresiones regulares (`parseMultipleArtifacts`). Si el modelo altera un encabezado o formato, se pierden campos obligatorios como criterios de aceptación, reglas de negocio o supuestos.

**Decisión:**  
Separar de forma estricta las capas de procedimiento, calidad, datos y presentación:
1. **Procedimiento (Skill):** Instrucciones del rol funcional o QA para recopilar y analizar requerimientos.
2. **Estructura (Artifact Schema):** Modelos Pydantic en backend e interfaces TypeScript en frontend (ej. `FunctionalImprovementArtifact`, `FunctionalInventoryArtifact`).
3. **Calidad (Rubric):** Rúbrica con reglas obligatorias deterministas y semánticas previas a la aprobación.
4. **Presentación (Renderers):** Transformación final del objeto validado hacia Markdown, Univer, DOCX o XLSX.

**Consecuencias:**
- Los artefactos se validan estructuralmente antes de persistirse o renderizarse.
- Se previenen documentos silenciosamente incompletos o malformados.
- Se mantiene historial inmutable por versiones de artefacto (`version_id`, `created_at`, `approved_by`).
