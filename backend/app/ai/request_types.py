"""Specialized request types for AI features following ISP"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SimpleFeatureRequest:
    """For features that only need a query"""
    feature: str
    query: str
    user_id: str | None = None


@dataclass
class DocumentFeatureRequest:
    """For features that analyze uploaded documents"""
    feature: str
    query: str
    document_ids: list[str]
    sources: list[str] | None = None
    user_id: str | None = None


@dataclass
class GroundedFeatureRequest:
    """For features needing full RAG context"""
    feature: str
    query: str
    sources: list[str] | None = None
    document_ids: list[str] | None = None
    chat_context: str | None = None
    template_content: str | None = None
    user_id: str | None = None
