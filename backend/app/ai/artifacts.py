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


@dataclass
class LLMArtifact:
    """Representa un artefacto de documento generado por el LLM."""
    title: str
    extension: str          # ej: "docx", "md", "xlsx"
    content: str
    index: int = 0          # posición en la respuesta (0-based)


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

    # Limpiar el texto de todas las etiquetas artifact
    clean = _ARTIFACT_PATTERN.sub("", raw_text)
    clean = _ARTIFACT_PATTERN_ALT.sub("", clean)
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
