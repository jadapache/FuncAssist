"""Declarative DOCX template renderer with XML run-splitting support."""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Union
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table


class DocxTemplateRenderer:
    """Renders structured artifact data into DOCX templates preserving document styling."""

    @classmethod
    def render(cls, template_source: Union[str, bytes, io.BytesIO], data: Dict[str, Any]) -> bytes:
        doc = cls._load_document(template_source)
        flattened_data = cls._flatten_dict(data)

        cls._process_paragraphs(doc.paragraphs, flattened_data)
        cls._process_tables(doc.tables, flattened_data)
        cls._process_sections(doc.sections, flattened_data)

        output = io.BytesIO()
        doc.save(output)
        return output.getvalue()

    @staticmethod
    def _load_document(source: Union[str, bytes, io.BytesIO]) -> Document:
        if isinstance(source, bytes):
            return Document(io.BytesIO(source))
        if isinstance(source, io.BytesIO):
            return Document(source)
        return Document(source)

    @classmethod
    def _process_paragraphs(cls, paragraphs: List[Paragraph], data: Dict[str, str]) -> None:
        for p in paragraphs:
            cls._replace_in_paragraph(p, data)

    @classmethod
    def _process_tables(cls, tables: List[Table], data: Dict[str, str]) -> None:
        for table in tables:
            for row in table.rows:
                for cell in row.cells:
                    cls._process_paragraphs(cell.paragraphs, data)

    @classmethod
    def _process_sections(cls, sections: Any, data: Dict[str, str]) -> None:
        for section in sections:
            cls._process_paragraphs(section.header.paragraphs, data)
            cls._process_paragraphs(section.footer.paragraphs, data)

    @classmethod
    def _replace_in_paragraph(cls, paragraph: Paragraph, data: Dict[str, str]) -> None:
        full_text = paragraph.text
        if "{{" not in full_text:
            return

        replaced_text = full_text
        for key, value in data.items():
            pattern = f"{{{{{key}}}}}"
            if pattern in replaced_text:
                replaced_text = replaced_text.replace(pattern, str(value))

        if replaced_text != full_text:
            cls._apply_replacement_to_runs(paragraph, replaced_text)

    @staticmethod
    def _apply_replacement_to_runs(paragraph: Paragraph, new_text: str) -> None:
        if not paragraph.runs:
            paragraph.add_run(new_text)
            return

        paragraph.runs[0].text = new_text
        for run in paragraph.runs[1:]:
            run.text = ""

    @classmethod
    def _flatten_dict(cls, d: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
        items: Dict[str, str] = {}
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                items.update(cls._flatten_dict(v, key))
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    continue
                items[key] = "\n".join(f"- {item}" for item in v)
            else:
                items[key] = str(v) if v is not None else ""
        return items
