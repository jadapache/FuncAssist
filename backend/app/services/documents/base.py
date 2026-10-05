"""Base interface for document builders"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class DocumentMetadata:
    """Metadata for generated documents"""
    title: str
    author: str = "QA_MGMT"
    created_at: str = ""
    module: str = "general"
    tags: List[str] = field(default_factory=list)


class IDocumentBuilder(ABC):
    """Interface for document generation"""

    @abstractmethod
    async def build(self, content: dict, metadata: Optional[DocumentMetadata] = None) -> bytes:
        """Build document from content and return bytes"""
        pass

    @abstractmethod
    def get_mime_type(self) -> str:
        """Return MIME type for this document format"""
        pass

    @abstractmethod
    def get_extension(self) -> str:
        """Return file extension for this document format"""
        pass

