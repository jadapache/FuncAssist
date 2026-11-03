"""Helpers for deciding when a response should be generated section by section."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlanSection:
    title: str
    instructions: str = ""


@dataclass(frozen=True)
class DocumentPlan:
    title: str
    extension: str
    chat_intro: str
    sections: list[PlanSection]


def is_section_generation_candidate(intent: str, query: str) -> bool:
    """Return whether a request is suitable for a multi-section document plan."""
    if (intent or "").strip().lower() in {"generic_plan", "generic_report", "template_mutation"}:
        return True
    text = (query or "").strip().lower()
    if text.startswith("/plan"):
        return True
    return bool(re.search(r"\b(elabora|genera|crear|crea|redacta)\b.*\b(plan|informe|reporte)\b", text))


def _clean_json_response(response: str) -> str:
    """Remove markdown fences and surrounding text from a JSON response."""
    text = (response or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


def _parse_plan_json(response: str) -> DocumentPlan | None:
    try:
        data: Any = json.loads(_clean_json_response(response))
        if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
            return None
        sections = [
            PlanSection(str(item["title"]), str(item.get("instructions", "")))
            for item in data["sections"]
            if isinstance(item, dict) and item.get("title")
        ]
        if not sections or not data.get("title") or not data.get("extension"):
            return None
        return DocumentPlan(
            title=str(data["title"]),
            extension=str(data["extension"]),
            chat_intro=str(data.get("chat_intro", "")),
            sections=sections,
        )
    except (TypeError, ValueError, KeyError):
        return None
