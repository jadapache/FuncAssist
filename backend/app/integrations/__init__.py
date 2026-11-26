"""Integrations package. `IntegrationRegistry` loads on first use, not on import.

Importing any submodule (for example `mcp_policy` from a repository) runs this file first; loading
the registry here would pull in every adapter and, through them, the storage layer that is still
being imported.
"""

from __future__ import annotations

from typing import Any

__all__ = ["IntegrationRegistry"]


def __getattr__(name: str) -> Any:
    if name == "IntegrationRegistry":
        from app.integrations.registry import IntegrationRegistry

        return IntegrationRegistry
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
