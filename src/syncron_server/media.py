"""Images hébergées : vérifiées, normalisées en PNG, nommées par empreinte (cache client infini)."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from syncron_core.errors import AppError

MEDIA_PREFIX = "/media/"
MAX_SIDE = 512
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "BMP"}


class ImageError(AppError):
    pass


def normalize_image(raw: bytes, max_bytes: int) -> bytes:
    if len(raw) > max_bytes:
        raise ImageError(f"Image trop lourde ({len(raw) // 1024} Ko, maximum {max_bytes // 1024} Ko).")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ImageError(f"Format non accepté : {image.format}. Formats : PNG, JPEG, WEBP, GIF, BMP.")
            image.seek(0)
            converted = image.convert("RGBA")
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ImageError("Fichier image illisible.") from exc
    if max(converted.size) > MAX_SIDE:
        converted.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.NEAREST)
    output = io.BytesIO()
    converted.save(output, format="PNG", optimize=True)
    return output.getvalue()


def store_image(media_dir: Path, kind: str, entity_id: str, png: bytes) -> str:
    digest = hashlib.sha256(png).hexdigest()[:12]
    relative = Path(kind) / f"{entity_id}-{digest}.png"
    target = media_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    return MEDIA_PREFIX + relative.as_posix()


def delete_image(media_dir: Path, url: str | None) -> None:
    """Supprime un fichier hébergé ; ignore toute URL qui ne pointe pas dans le dossier média."""
    if not url or not url.startswith(MEDIA_PREFIX):
        return
    root = media_dir.resolve()
    path = (media_dir / url.removeprefix(MEDIA_PREFIX)).resolve()
    if path.is_relative_to(root) and path.is_file():
        path.unlink()


def is_hosted(url: str | None) -> bool:
    return bool(url) and url.startswith(MEDIA_PREFIX)
