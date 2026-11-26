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
from dataclasses import dataclass


_ARTIFACT_PATTERN = re.compile(
    r'<artifact\s+title=[\'"]([^\'"]+)[\'"]\s+extension=[\'"]([^\'"]+)[\'"]>(.*?)</artifact>',
    re.DOTALL | re.IGNORECASE,
)

# También soportar orden invertido de atributos: extension primero, luego title
_ARTIFACT_PATTERN_ALT = re.compile(
    r'<artifact\s+extension=[\'"]([^\'"]+)[\'"]\s+title=[\'"]([^\'"]+)[\'"]>(.*?)</artifact>',
    re.DOTALL | re.IGNORECASE,
)
_ARTIFACT_OPEN = re.compile(
    r'<artifact\s+(?:title=[\'"]([^\'"]+)[\'"]\s+extension=[\'"]([^\'"]+)[\'"]|extension=[\'"]([^\'"]+)[\'"]\s+title=[\'"]([^\'"]+)[\'"])>',
    re.IGNORECASE,
)


@dataclass
class LLMArtifact:
    """Representa un artefacto de documento generado por el LLM."""
    title: str
    extension: str          # ej: "docx", "md", "xlsx"
    content: str
    index: int = 0          # posición en la respuesta (0-based)


def has_unclosed_artifact(raw_text: str) -> bool:
    """True when an `<artifact ...>` opening tag has no matching `</artifact>`."""
    if not raw_text:
        return False
    openings = len(_ARTIFACT_OPEN.findall(raw_text))
    closings = len(re.findall(r"</artifact>", raw_text, re.IGNORECASE))
    return closings < openings


_ABRUPT_LAST_LINE = (
    # Heading or section number without content, e.g. "2.5 ACTIVIDADES MANUALES", "### BENEFICIO".
    re.compile(r"^(#{1,6}\s+|(?:\d+\.)+\d*\s+|[A-Z0-9\s]{4,}:?\s*$|\*\*[^*]+\*\*\s*$)"),
    # Empty or incomplete bullet: "-", "*", "1.".
    re.compile(r"^[-*]\s*$"),
    re.compile(r"^\d+\.\s*$"),
)
_MIN_CHARS_FOR_TRUNCATION_HEURISTIC = 500


def _ends_abruptly(raw_text: str) -> bool:
    """Heuristic for long texts cut by a token limit: dangling heading, bullet, code fence or table row."""
    stripped = raw_text.rstrip()
    if len(stripped) <= _MIN_CHARS_FOR_TRUNCATION_HEURISTIC:
        return False
    last_line = stripped.splitlines()[-1].strip()
    return (
        any(pattern.match(last_line) for pattern in _ABRUPT_LAST_LINE)
        or stripped.count("```") % 2 != 0
        or (last_line.startswith("|") and not last_line.endswith("|"))
    )


def is_artifact_truncated(raw_text: str) -> bool:
    """Detecta si la generación se cortó antes de finalizar.

    Verifica:
    1. Si hay una etiqueta <artifact ...> abierta sin su correspondiente </artifact>.
    2. Si el texto (markdown directo o dentro de artefacto) termina abruptamente
       a mitad de una sección, de una línea o lista de viñetas, de una fila de tabla
       o con un bloque de código sin cerrar.
    """
    return bool(raw_text) and (has_unclosed_artifact(raw_text) or _ends_abruptly(raw_text))


def _artifact_from(match: re.Match, index: int, title_group: int, extension_group: int) -> LLMArtifact:
    title, extension, content = match.group(title_group), match.group(extension_group), match.group(3)
    return LLMArtifact(title.strip(), extension.strip().lower(), content.strip(), index)


def _closed_artifacts(raw_text: str) -> list[LLMArtifact]:
    """Artifacts with a closing tag; `title` first, else the reversed attribute order."""
    found = [_artifact_from(m, i, 1, 2) for i, m in enumerate(_ARTIFACT_PATTERN.finditer(raw_text))]
    return found or [_artifact_from(m, i, 2, 1) for i, m in enumerate(_ARTIFACT_PATTERN_ALT.finditer(raw_text))]


def _recover_cut_off_artifacts(raw_text: str, openings: list[re.Match]) -> list[LLMArtifact]:
    """Blocks cut off before the closing tag, including a partial one such as ``</art``."""
    recovered = []
    for idx, opening in enumerate(openings):
        end = openings[idx + 1].start() if idx + 1 < len(openings) else len(raw_text)
        block = raw_text[opening.end():end]
        closing = block.find("</artifact>")
        content = block[:closing] if closing >= 0 else re.sub(r"</art(?:ifact)?$", "", block)
        title = opening.group(1) or opening.group(4)
        extension = opening.group(2) or opening.group(3)
        recovered.append(LLMArtifact(title.strip(), extension.strip().lower(), content.strip(), idx))
    return recovered


def _conversation_text(raw_text: str) -> str:
    """Text without artifact tags; the `<chat>` blocks when present (several are joined in order)."""
    clean = _ARTIFACT_OPEN.sub("", raw_text)
    clean = re.sub(r"</artifact>|</art$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    chat_blocks = [
        block.strip()
        for block in re.findall(r"<chat>(.*?)</chat>", clean, re.DOTALL | re.IGNORECASE)
        if block.strip()
    ]
    if chat_blocks:
        return "\n\n".join(chat_blocks)
    return re.sub(r"</?chat>", "", clean).strip()


def extract_artifacts(raw_text: str) -> tuple[list[LLMArtifact], str]:
    """Extrae bloques <artifact> del texto crudo del LLM.

    Returns:
        Tupla (lista_de_artefactos, texto_limpio): los artefactos en orden de aparición y el
        texto original sin las etiquetas XML ni los espacios extra.
    """
    artifacts = _closed_artifacts(raw_text)
    openings = list(_ARTIFACT_OPEN.finditer(raw_text))
    if len(artifacts) < len(openings):
        artifacts = _recover_cut_off_artifacts(raw_text, openings)
    return artifacts, _conversation_text(raw_text)


def build_fallback_artifact(
    content: str,
    default_title: str = "Documento",
    default_extension: str = "docx",
) -> LLMArtifact:
    """Builds a primary LLMArtifact when generative intent produced raw markdown without XML tags."""
    first_heading = re.search(r"^\s*#\s+(.+)$", content, re.MULTILINE)
    title = first_heading.group(1).strip() if first_heading else default_title
    return LLMArtifact(
        title=title,
        extension=default_extension.lower(),
        content=content.strip(),
        index=0,
    )


_CHAT_TAG = re.compile(r"</?chat>", re.IGNORECASE)
_CLOSE_TAG = "</artifact>"
_HELD_PREFIXES_OUTSIDE = ("<artifact", "<chat>", "</chat>")


def _partial_suffix_len(text: str, prefixes: tuple[str, ...]) -> int:
    """Length of the longest suffix of `text` that is a proper prefix of one of `prefixes`."""
    lower = text.lower()
    best = 0
    for prefix in prefixes:
        for size in range(min(len(prefix) - 1, len(lower)), best, -1):
            if prefix.startswith(lower[-size:]):
                best = size
                break
    return best


class ArtifactStreamSplitter:
    """Split streamed LLM text into chat deltas and artifact events as it arrives.

    `feed()` and `close()` return `(event_type, data)` tuples with event types `delta` ({text}),
    `artifact_start` ({index, title, extension}), `artifact_delta` ({index, text}) and
    `artifact_end` ({index, title, extension, truncated}). `<chat>` tags are removed from deltas.
    Text that could be the start of a tag split across chunks is held back until it is decidable.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._artifact: dict[str, object] | None = None
        self._count = 0

    def feed(self, text: str) -> list[tuple[str, dict]]:
        self._buf += text or ""
        events: list[tuple[str, dict]] = []
        while self._buf:
            if self._artifact is None:
                if not self._consume_outside(events):
                    break
            elif not self._consume_inside(events):
                break
        return events

    def close(self) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []
        rest, self._buf = self._buf, ""
        if self._artifact is not None:
            if rest:
                events.append(("artifact_delta", {"index": self._artifact["index"], "text": rest}))
            events.append(("artifact_end", {**self._artifact, "truncated": True}))
            self._artifact = None
        else:
            self._emit_chat(events, rest)
        return events

    def _emit_chat(self, events: list[tuple[str, dict]], text: str) -> None:
        clean = _CHAT_TAG.sub("", text)
        if clean:
            events.append(("delta", {"text": clean}))

    def _consume_outside(self, events: list[tuple[str, dict]]) -> bool:
        lower = self._buf.lower()
        start = lower.find("<artifact")
        if start < 0:
            hold = _partial_suffix_len(self._buf, _HELD_PREFIXES_OUTSIDE)
            # A complete "<chat>"/"</chat>" may also sit right before a partial tag; it is removed
            # from the emitted part by _emit_chat.
            self._emit_chat(events, self._buf[: len(self._buf) - hold])
            self._buf = self._buf[len(self._buf) - hold:]
            return False
        self._emit_chat(events, self._buf[:start])
        self._buf = self._buf[start:]
        match = _ARTIFACT_OPEN.match(self._buf)
        if match:
            title = (match.group(1) or match.group(4) or "Documento").strip()
            extension = (match.group(2) or match.group(3) or "docx").strip().lower()
            self._artifact = {"index": self._count, "title": title, "extension": extension}
            self._count += 1
            events.append(("artifact_start", dict(self._artifact)))
            self._buf = self._buf[match.end():]
            return True
        end_of_tag = self._buf.find(">")
        if end_of_tag == -1:
            return False  # opening tag still incomplete
        # Malformed tag: pass it through as text.
        self._emit_chat(events, self._buf[: end_of_tag + 1])
        self._buf = self._buf[end_of_tag + 1:]
        return True

    def _consume_inside(self, events: list[tuple[str, dict]]) -> bool:
        assert self._artifact is not None
        lower = self._buf.lower()
        end = lower.find(_CLOSE_TAG)
        index = self._artifact["index"]
        if end < 0:
            hold = _partial_suffix_len(self._buf, (_CLOSE_TAG,))
            chunk = self._buf[: len(self._buf) - hold]
            if chunk:
                events.append(("artifact_delta", {"index": index, "text": chunk}))
            self._buf = self._buf[len(self._buf) - hold:]
            return False
        if end > 0:
            events.append(("artifact_delta", {"index": index, "text": self._buf[:end]}))
        events.append(("artifact_end", {**self._artifact, "truncated": False}))
        self._artifact = None
        self._buf = self._buf[end + len(_CLOSE_TAG):]
        return True


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
