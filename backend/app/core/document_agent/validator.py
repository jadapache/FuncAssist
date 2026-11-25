"""DocumentAgent Operation Validator.

Validates proposed operations against current document canonical state,
ensuring targets, assets, and bounds are valid before execution.
"""

from __future__ import annotations

from typing import List, Optional, Tuple
from .schema import (
    CanonicalDocumentState,
    DocumentOperation,
    InsertImageOperation,
    InsertTextOperation,
    ReplaceContentOperation,
    UpdateTableOperation,
    CreateTableOperation,
    DeleteContentOperation,
    MoveContentOperation,
    TargetLocator,
)




import unicodedata

def _normalize_text(text: str) -> str:
    n = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8')
    return n.strip().lower()


class ValidationError(Exception):
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.field = field



class DocumentOperationValidator:
    """Pre-execution validation engine for canonical document operations."""

    @staticmethod
    def _match_section(target: TargetLocator, state: CanonicalDocumentState) -> Optional[str]:
        """Section title match, accent and case-insensitive, exact or partial."""
        if not target.section_title:
            return None
        wanted = _normalize_text(target.section_title)
        for sec in state.sections:
            title = _normalize_text(sec.title)
            if wanted in title or title in wanted:
                return f"Matched section '{sec.title}' (ID: {sec.id})"
        return None

    @staticmethod
    def _match_tag(target: TargetLocator, state: CanonicalDocumentState) -> Optional[str]:
        """Placeholder tag match, accent and case-insensitive, with or without braces."""
        if not target.tag:
            return None
        wanted = _normalize_text(target.tag.replace("{", "").replace("}", ""))
        for tag in state.tags_present:
            present = _normalize_text(tag.replace("{", "").replace("}", ""))
            if wanted in present or present in wanted:
                return f"Matched document placeholder tag '{{{{{tag}}}}}'"
        return None

    @staticmethod
    def _describe_missing(target: TargetLocator) -> str:
        identifiers = [f"section: {target.section_title}"] if target.section_title else []
        if target.tag:
            identifiers.append(f"tag: {target.tag}")
        if target.anchor_text:
            identifiers.append(f"anchor: '{target.anchor_text}'")
        return ", ".join(identifiers) or "Unknown target locator"

    @classmethod
    def resolve_target(cls, target: TargetLocator, state: CanonicalDocumentState) -> Tuple[bool, str]:
        """Verify if the target locator matches any section, tag, or anchor in the current document state."""
        matched = cls._match_section(target, state) or cls._match_tag(target, state)
        if matched:
            return True, matched
        if target.cell_range and state.kind == "spreadsheet":
            return True, f"Targeted spreadsheet cell range '{target.cell_range}'"
        if not state.sections and not state.tags_present and not state.tables_summary:
            return True, "Document is currently blank; appending to root."
        return False, f"Target not found in document: {cls._describe_missing(target)}"

    @classmethod
    def _checked_target(
        cls, target: TargetLocator, state: CanonicalDocumentState, purpose: str, ok_label: str
    ) -> Tuple[bool, str]:
        found, target_msg = cls.resolve_target(target, state)
        if not found:
            return False, f"Invalid target for {purpose}: {target_msg}"
        return True, f"{ok_label} validated successfully. {target_msg}"

    @classmethod
    def _validate_insert_image(cls, op: InsertImageOperation, state, available_asset_ids) -> Tuple[bool, str]:
        found, target_msg = cls.resolve_target(op.target, state)
        if not found:
            return False, f"Invalid target for image insertion: {target_msg}"
        asset = op.asset
        if not asset.asset_id and not asset.url:
            return False, "Image operation missing both asset_id and url."
        unknown = available_asset_ids is not None and asset.asset_id and asset.asset_id not in available_asset_ids
        # Permissive check if it is a local file or data uri
        if unknown and not (asset.url and asset.url.startswith(("http", "data:"))):
            return False, f"Asset ID '{asset.asset_id}' is not in available assets list."
        return True, f"InsertImage validated successfully. {target_msg}"

    @classmethod
    def _validate_insert_text(cls, op: InsertTextOperation, state, _assets) -> Tuple[bool, str]:
        if not op.content or not op.content.strip():
            return False, "Cannot insert empty text content."
        return cls._checked_target(op.target, state, "text insertion", "InsertText")

    @classmethod
    def _validate_replace(cls, op: ReplaceContentOperation, state, _assets) -> Tuple[bool, str]:
        return cls._checked_target(op.target, state, "content replacement", "ReplaceContent")

    @classmethod
    def _validate_update_table(cls, op: UpdateTableOperation, state, _assets) -> Tuple[bool, str]:
        if state.kind == "spreadsheet":
            return True, "Spreadsheet table update validated."
        if not state.tables_summary and not op.target.section_title:
            return False, "Document contains no tables to update and no section specified."
        return True, "UpdateTable validated successfully."

    @classmethod
    def _validate_create_table(cls, op: CreateTableOperation, state, _assets) -> Tuple[bool, str]:
        if not op.headers:
            return False, "Cannot create table without headers."
        return cls._checked_target(op.target, state, "table creation", "CreateTable")

    @classmethod
    def _validate_delete(cls, op: DeleteContentOperation, state, _assets) -> Tuple[bool, str]:
        return cls._checked_target(op.target, state, "deletion", "DeleteContent")

    @classmethod
    def _validate_move(cls, op: MoveContentOperation, state, _assets) -> Tuple[bool, str]:
        source_found, source_msg = cls.resolve_target(op.source_target, state)
        if not source_found:
            return False, f"MoveContent: source target not found — {source_msg}"
        dest_found, dest_msg = cls.resolve_target(op.destination_target, state)
        if not dest_found:
            return False, f"MoveContent: destination target not found — {dest_msg}"
        return True, f"MoveContent validated. Source: {source_msg}. Destination: {dest_msg}"

    @classmethod
    def validate(
        cls,
        op: DocumentOperation,
        current_state: CanonicalDocumentState,
        available_asset_ids: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """
        Validate operation against current document state.
        Returns (is_valid, validation_message).
        """
        validators = (
            (InsertImageOperation, cls._validate_insert_image),
            (InsertTextOperation, cls._validate_insert_text),
            (ReplaceContentOperation, cls._validate_replace),
            (UpdateTableOperation, cls._validate_update_table),
            (CreateTableOperation, cls._validate_create_table),
            (DeleteContentOperation, cls._validate_delete),
            (MoveContentOperation, cls._validate_move),
        )
        for operation_type, validator in validators:
            if isinstance(op, operation_type):
                return validator(op, current_state, available_asset_ids)
        # Default for read operations (inspect_document, find_section, find_text)
        return True, f"Operation '{op.operation}' validated."
