"""Images hébergées côté client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from syncron_core.text import format_quantity

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp)"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


@dataclass(frozen=True, slots=True)
class HostedImage:
    id: str
    url: str
    title: str
    content_type: str
    width: int
    height: int
    size_bytes: int
    uploader: str | None
    mine: bool
    can_delete: bool
    created_at: datetime

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> HostedImage:
        return cls(
            id=str(raw["id"]),
            url=raw["url"],
            title=raw.get("title") or "Image",
            content_type=raw.get("content_type") or "image/png",
            width=int(raw["width"]),
            height=int(raw["height"]),
            size_bytes=int(raw["size_bytes"]),
            uploader=raw.get("uploader"),
            mine=bool(raw.get("mine")),
            can_delete=bool(raw.get("can_delete")),
            created_at=datetime.fromisoformat(raw["created_at"]),
        )

    @property
    def animated(self) -> bool:
        return self.content_type == "image/gif"

    def details(self) -> str:
        """« 1 280 × 720 · 340 Ko · Ruixi · 2 nov. »."""
        parts = [f"{format_quantity(self.width)} × {format_quantity(self.height)}", format_size(self.size_bytes)]
        if self.uploader:
            parts.append(self.uploader)
        parts.append(self.created_at.astimezone().strftime("%d/%m/%Y"))
        return " · ".join(parts)


def format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{max(round(size / 1024), 1)} Ko"
    return f"{size / (1024 * 1024):.1f} Mo".replace(".", ",")


def matches(image: HostedImage, query: str) -> bool:
    words = query.casefold().split()
    haystack = f"{image.title} {image.uploader or ''}".casefold()
    return all(word in haystack for word in words)
