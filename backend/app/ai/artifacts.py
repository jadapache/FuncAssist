"""Utilidades para extraer artefactos estructurados del output crudo del LLM.

El LLM puede generar uno o más documentos delimitados por etiquetas XML:
    <artifact title="Mejora 001" extension="docx">
    ...contenido markdown...
    </artifact>

Este módulo parsea esas etiquetas en el backend para que el runner
retorne una lista tipada de artefactos en lugar de texto crudo con XML embebido.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


_ARTIFACT_PATTERN = re.compile(
    r'<artifact\s+title="([^"]+)"\s+extension="([^"]+)">(.*?)</artifact>',
    re.DOTALL | re.IGNORECASE,
)

# También soportar orden invertido de atributos: extension primero, luego title
_ARTIFACT_PATTERN_ALT = re.compile(
    r'<artifact\s+extension="([^"]+)"\s+title="([^"]+)">(.*?)</artifact>',
    re.DOTALL | re.IGNORECASE,
)
_ARTIFACT_OPEN = re.compile(
    r'<artifact\s+(?:title="([^"]+)"\s+extension="([^"]+)"|extension="([^"]+)"\s+title="([^"]+)")>',
    re.IGNORECASE,
)


@dataclass
class LLMArtifact:
    """Representa un artefacto de documento generado por el LLM."""
    title: str
    extension: str          # ej: "docx", "md", "xlsx"
    content: str
    index: int = 0          # posición en la respuesta (0-based)


def is_artifact_truncated(raw_text: str) -> bool:
    """Detecta si la generación se cortó antes de finalizar.
    
    Verifica:
    1. Si hay una etiqueta <artifact ...> abierta sin su correspondiente </artifact>.
    2. Si el texto (markdown directo o dentro de artefacto) termina abruptamente
       a mitad de una sección (ej. encabezado solo como '## BENEFICIO ESPERADO'),
       a mitad de una línea o lista de viñetas, o con un bloque de código sin cerrar.
    """
    if not raw_text or not raw_text.strip():
        return False

    # 1. Chequeo de etiquetas <artifact>
    if "<artifact" in raw_text.lower():
        openings = list(_ARTIFACT_OPEN.finditer(raw_text))
        if openings:
            closings = list(re.finditer(r"</artifact>", raw_text, re.IGNORECASE))
            if len(closings) < len(openings):
                return True

    # 2. Chequeo heurístico para textos extensos (documentos o respuestas largas cortadas por token limit)
    stripped = raw_text.rstrip()
    if len(stripped) > 500:
        # Termina en encabezado de markdown o número de sección sin contenido
        # ej: "2.5 ACTIVIDADES MANUALES", "### BENEFICIO ESPERADO", "**BENEFICIO ESPERADO**"
        last_line = stripped.splitlines()[-1].strip()
        if re.match(r"^(#{1,6}\s+|(?:\d+\.)+\d*\s+|[A-Z0-9\s]{4,}:?\s*$|\*\*[^*]+\*\*\s*$)", last_line):
            return True
        # Termina en viñeta vacía o incompleta (ej. "-", "*", "1.")
        if re.match(r"^[-*]\s*$", last_line) or re.match(r"^\d+\.\s*$", last_line):
            return True
        # Termina con un bloque de código markdown sin cerrar (número impar de triple backticks)
        backtick_count = stripped.count("```")
        if backtick_count % 2 != 0:
            return True
        # Termina a mitad de una fila de tabla markdown incompleta (ej: "| Col1 |")
        if last_line.startswith("|") and not last_line.endswith("|"):
            return True

    return False


def extract_artifacts(raw_text: str) -> tuple[list[LLMArtifact], str]:
    """Extrae bloques <artifact> del texto crudo del LLM.

    Args:
        raw_text: Texto completo retornado por el LLM, posiblemente
                  con etiquetas <artifact> embebidas.

    Returns:
        Tupla (lista_de_artefactos, texto_limpio).
        - lista_de_artefactos: artefactos encontrados en orden de aparición.
        - texto_limpio: el texto original con las etiquetas XML removidas y
          espacios extra colapsados.
    """
    artifacts: list[LLMArtifact] = []

    # Match patrón principal: title primero
    for idx, match in enumerate(_ARTIFACT_PATTERN.finditer(raw_text)):
        artifacts.append(LLMArtifact(
            title=match.group(1).strip(),
            extension=match.group(2).strip().lower(),
            content=match.group(3).strip(),
            index=idx,
        ))

    # Si no encontró con patrón principal, intentar orden alternativo
    if not artifacts:
        for idx, match in enumerate(_ARTIFACT_PATTERN_ALT.finditer(raw_text)):
            artifacts.append(LLMArtifact(
                title=match.group(2).strip(),
                extension=match.group(1).strip().lower(),
                content=match.group(3).strip(),
                index=idx,
            ))

    # Recover blocks cut off before the closing tag, including a partial
    # closing tag such as ``</art``.
    openings = list(_ARTIFACT_OPEN.finditer(raw_text))
    if len(artifacts) < len(openings):
        artifacts = []
        for idx, opening in enumerate(openings):
            end = openings[idx + 1].start() if idx + 1 < len(openings) else len(raw_text)
            block = raw_text[opening.end():end]
            closing = block.find("</artifact>")
            content = block[:closing] if closing >= 0 else re.sub(r"</art(?:ifact)?$", "", block)
            title = opening.group(1) or opening.group(4)
            extension = opening.group(2) or opening.group(3)
            artifacts.append(LLMArtifact(title.strip(), extension.strip().lower(), content.strip(), idx))

    # Limpiar el texto de todas las etiquetas artifact
    clean = _ARTIFACT_OPEN.sub("", raw_text)
    clean = re.sub(r"</artifact>|</art$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()

    # Si hay bloques <chat>, extraer su contenido como texto limpio de conversacion
    chat_match = re.search(r'<chat>(.*?)</chat>', clean, re.DOTALL | re.IGNORECASE)
    if chat_match:
        clean = chat_match.group(1).strip()
    else:
        clean = re.sub(r'</?chat>', '', clean).strip()

    return artifacts, clean


def artifacts_to_dict(artifacts: list[LLMArtifact]) -> list[dict]:
    """Serializa la lista de artefactos a dicts para la respuesta JSON."""
    return [
        {
            "index": a.index,
            "title": a.title,
            "extension": a.extension,
            "content": a.content,
        }
        for a in artifacts
    ]
