"""Images hébergées.

- Objets et ateliers du Craft : vérifiées, normalisées en PNG 512 px, nommées par empreinte.
- Images des membres (outil Images) : vérifiées, réencodées (métadonnées retirées) en PNG, JPEG ou GIF
  animé, jusqu'à 4096 px, nommées par un jeton aléatoire impossible à deviner.
"""

from __future__ import annotations

import hashlib
import io
import secrets
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from syncron_core.errors import AppError

MEDIA_PREFIX = "/media/"
MAX_SIDE = 512
MAX_PIXELS = 4096 * 4096  # au-delà : refus avant décodage (images « bombes » de décompression)
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "BMP"}
MAX_FRAMES = 300
MAX_ANIMATION_PIXELS = 64 * 1024 * 1024  # largeur × hauteur × images d'un GIF animé
HOSTED_DIR = "images"


class ImageError(AppError):
    pass


def normalize_image(raw: bytes, max_bytes: int) -> bytes:
    if len(raw) > max_bytes:
        raise ImageError(f"Image trop lourde ({len(raw) // 1024} Ko, maximum {max_bytes // 1024} Ko).")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            _check_dimensions(probe)
            probe.verify()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ImageError(f"Format non accepté : {image.format}. Formats : PNG, JPEG, WEBP, GIF, BMP.")
            _check_dimensions(image)
            image.seek(0)
            converted = image.convert("RGBA")
    except Image.DecompressionBombError as exc:
        raise ImageError("Image trop grande.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ImageError("Fichier image illisible.") from exc
    if max(converted.size) > MAX_SIDE:
        converted.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.NEAREST)
    output = io.BytesIO()
    converted.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _check_dimensions(image: Image.Image) -> None:
    width, height = image.size
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise ImageError(f"Image trop grande ({width}×{height} pixels, 4096×4096 au plus).")


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


@dataclass(frozen=True, slots=True)
class HostedFile:
    content: bytes
    content_type: str
    extension: str
    width: int
    height: int


def normalize_hosted(raw: bytes, max_bytes: int) -> HostedFile:
    """Réencode une image envoyée par un membre : rien de ce qu'elle contenait d'autre que ses pixels
    (EXIF, position GPS, données cachées) ne reste. GIF animé conservé ; photo opaque en JPEG ; sinon PNG."""
    if len(raw) > max_bytes:
        raise ImageError(f"Image trop lourde ({len(raw) // 1024} Ko, maximum {max_bytes // 1024} Ko).")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            _check_dimensions(probe)
            probe.verify()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ImageError(f"Format non accepté : {image.format}. Formats : PNG, JPEG, WEBP, GIF, BMP.")
            _check_dimensions(image)
            frames = getattr(image, "n_frames", 1)
            if image.format == "GIF" and frames > 1:
                return _animated_gif(image, frames)
            image.seek(0)
            width, height = image.size
            output = io.BytesIO()
            if image.format == "JPEG" or (image.mode in ("RGB", "L", "CMYK") and image.format != "PNG"):
                image.convert("RGB").save(output, format="JPEG", quality=90, optimize=True)
                return HostedFile(output.getvalue(), "image/jpeg", "jpg", width, height)
            image.convert("RGBA").save(output, format="PNG", optimize=True)
            return HostedFile(output.getvalue(), "image/png", "png", width, height)
    except Image.DecompressionBombError as exc:
        raise ImageError("Image trop grande.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as exc:
        raise ImageError("Fichier image illisible.") from exc


def _animated_gif(image: Image.Image, frames: int) -> HostedFile:
    width, height = image.size
    if frames > MAX_FRAMES or width * height * frames > MAX_ANIMATION_PIXELS:
        raise ImageError(f"Animation trop longue ({frames} images de {width}×{height}).")
    images, durations = [], []
    for index in range(frames):
        image.seek(index)
        images.append(image.convert("RGBA"))
        durations.append(int(image.info.get("duration", 100)) or 100)
    output = io.BytesIO()
    images[0].save(
        output, format="GIF", save_all=True, append_images=images[1:], duration=durations, loop=0, disposal=2
    )
    return HostedFile(output.getvalue(), "image/gif", "gif", width, height)


def store_hosted(media_dir: Path, hosted: HostedFile) -> str:
    """Enregistre l'image sous un nom aléatoire ; renvoie son chemin relatif (« images/<jeton>.png »)."""
    relative = f"{HOSTED_DIR}/{secrets.token_urlsafe(12)}.{hosted.extension}"
    target = media_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(hosted.content)
    return relative
