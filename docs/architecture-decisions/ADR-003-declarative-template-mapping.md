# ADR-003: Motor Declarativo de Mapeo de Plantillas DOCX y XLSX

**Estado:** Aceptado  
**Fecha:** 2026-10-24  
**Contexto:**  
Los documentos corporativos DOCX y XLSX se generaban de manera imperativa hardcodeada (`docx_builder.py`, `xlsx_builder.py`), lo que impedía que analistas funcionales o líderes QA personalizaran plantillas oficiales o mapearan nuevos campos sin modificar código fuente.

**Decisión:**  
Implementar motores de renderizado desacoplados basados en una gramática acotada y segura de marcadores:
1. **Sintaxis de marcadores:**
   - Campos simples: `{{artifact.field}}`
   - Bloques repetibles: `{{#each artifact.items}} ... {{/each}}`
   - Secciones condicionales: `{{#if artifact.condition}} ... {{/if}}`
2. **Motor DOCX (`docx_engine.py`):**
   - Detección de marcadores divididos en múltiples `runs` de Word (XML Run Splitting).
   - Sustitución preservando estilos de fuentes, encabezados, tablas y pies de página.
3. **Motor XLSX (`xlsx_engine.py`):**
   - Mapeo directo a coordenadas `Hoja!Celda` y filas repetibles en tablas de especificación o matrices QA.
   - Preservación estricta de fórmulas y estilos existentes.
4. **Seguridad:** No ejecutar macros, eval ni código embebido en las plantillas cargadas.

**Consecuencias:**
- Plantillas corporativas versionables y reutilizables por proyecto.
- Trazabilidad entre el artefacto estructurado y el archivo binario generado.
