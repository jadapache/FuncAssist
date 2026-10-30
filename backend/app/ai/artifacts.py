"""Utilidades para extraer artefactos estructurados del output crudo del LLM.

El LLM puede generar uno o más documentos delimitados por etiquetas XML:
    <artifact title="Mejora 001" extension="docx">
    ...contenido markdown...
    </artifact>

Este módulo parsea esas etiquetas de forma tolerante a fallos, recuperando
incluso artefactos truncados si el modelo agotó sus tokens de salida.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_ARTIFACT_PATTERN = re.compile(
    r'<artifact\s+title="([^"]+)"\s+extension="([^"]+)">(.*?)</artifact>',
    re.DOTALL | re.IGNORECASE,
)

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


def _parse_attributes(tag_attrs: str) -> tuple[str, str]:
    title_match = re.search(r'title=["\']([^"\']+)["\']', tag_attrs, re.IGNORECASE)
    ext_match = re.search(r'extension=["\']([^"\']+)["\']', tag_attrs, re.IGNORECASE)
    title = title_match.group(1).strip() if title_match else "Documento Generado"
    extension = ext_match.group(1).strip().lower() if ext_match else "docx"
    return title, extension


def _extract_unclosed_artifact(
    text: str, current_count: int
) -> tuple[LLMArtifact | None, str]:
    """Extrae un bloque <artifact> no cerrado por límite de tokens."""
    open_match = re.search(r'<artifact\s+([^>]*?)>(.*)$', text, re.DOTALL | re.IGNORECASE)
    if not open_match:
        return None, text

    tag_attrs = open_match.group(1)
    raw_content = open_match.group(2).strip()
    cleaned_content = re.sub(
        r'</?(?:artifact|art|a)?[^>]*$', '', raw_content, flags=re.IGNORECASE
    ).strip()

    title, extension = _parse_attributes(tag_attrs)
    artifact = LLMArtifact(
        title=title,
        extension=extension,
        content=cleaned_content,
        index=current_count,
    )
    text_without = text[:open_match.start()].strip()
    return artifact, text_without


def _clean_chat_tags(text: str) -> str:
    chat_match = re.search(r'<chat>(.*?)</chat>', text, re.DOTALL | re.IGNORECASE)
    if chat_match:
        return chat_match.group(1).strip()
    unclosed_chat = re.search(r'<chat>(.*)$', text, re.DOTALL | re.IGNORECASE)
    if unclosed_chat:
        return unclosed_chat.group(1).strip()
    return re.sub(r'</?chat>', '', text).strip()


def extract_artifacts(raw_text: str) -> tuple[list[LLMArtifact], str]:
    """Extrae bloques <artifact> del texto crudo con soporte tolerante a truncamiento."""
    artifacts: list[LLMArtifact] = []

    # 1. Extraer bloques cerrados con patron estándar
    for idx, match in enumerate(_ARTIFACT_PATTERN.finditer(raw_text)):
        artifacts.append(LLMArtifact(
            title=match.group(1).strip(),
            extension=match.group(2).strip().lower(),
            content=match.group(3).strip(),
            index=idx,
        ))

    # 2. Si no hubo coincidencia, intentar orden alternativo de atributos
    if not artifacts:
        for idx, match in enumerate(_ARTIFACT_PATTERN_ALT.finditer(raw_text)):
            artifacts.append(LLMArtifact(
                title=match.group(2).strip(),
                extension=match.group(1).strip().lower(),
                content=match.group(3).strip(),
                index=idx,
            ))

    # Limpiar etiquetas cerradas
    clean = _ARTIFACT_PATTERN.sub("", raw_text)
    clean = _ARTIFACT_PATTERN_ALT.sub("", clean)

    # 3. Extraer artefacto truncado no cerrado si existe
    unclosed_art, clean = _extract_unclosed_artifact(clean, len(artifacts))
    if unclosed_art and unclosed_art.content:
        artifacts.append(unclosed_art)

    clean = re.sub(r'\n{3,}', '\n\n', clean).strip()
    clean = _clean_chat_tags(clean)

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
