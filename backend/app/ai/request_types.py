"""Specialized request types for AI features following ISP"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class SimpleFeatureRequest:
    """For features that only need a query"""
    feature: str
    query: str


@dataclass
class DocumentFeatureRequest:
    """For features that analyze uploaded documents"""
    feature: str
    query: str
    document_ids: list[str]
    sources: list[str] | None = None


@dataclass
class GroundedFeatureRequest:
    """For features needing full RAG context"""
    feature: str
    query: str
    sources: list[str] | None = None
    document_ids: list[str] | None = None
    chat_context: str | None = None
    template_content: str | None = None


class IFeatureRunner(Protocol):
    """Interface for running AI features"""

    async def run(self, request: GroundedFeatureRequest) -> dict[str, Any]:
        """Execute feature with full context"""
        ...

    async def run_simple(self, request: SimpleFeatureRequest) -> dict[str, Any]:
        """Execute simple feature (query only)"""
        ...

    async def run_with_documents(self, request: DocumentFeatureRequest) -> dict[str, Any]:
        """Execute feature with document analysis"""
        ...
