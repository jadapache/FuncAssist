"""User messages that carry images next to their text."""

from __future__ import annotations

from typing import Any

from app.ai.providers.base import AIMessage


def _image_url(image: dict[str, str]) -> str:
    """Data URL of an uploaded image, built from raw base64 plus its MIME type when needed."""
    data_url = image.get("data") or image.get("dataUrl") or ""
    if data_url.startswith("data:"):
        return data_url
    mime = image.get("mime_type") or image.get("type") or "image/png"
    return f"data:{mime};base64,{data_url}"


def user_message_with_images(text: str, images: list[dict[str, str]] | None, *, skip_empty: bool = False) -> AIMessage:
    """A user message with `text` and one image part per image.

    Images without data are skipped when `skip_empty` is set; otherwise they are sent as an empty
    PNG data URL.
    """
    if not images:
        return AIMessage(role="user", content=text)
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for image in images:
        if skip_empty and not (image.get("data") or image.get("dataUrl")):
            continue
        parts.append({"type": "image_url", "image_url": {"url": _image_url(image)}})
    return AIMessage(role="user", content=parts)
