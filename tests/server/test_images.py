"""Hébergement d'images : envoi, lien public, réencodage, quota, droits."""

from __future__ import annotations

import io

from PIL import Image

from .conftest import login

IMAGES = "/api/v1/images"


def _image(fmt: str = "PNG", size: tuple[int, int] = (40, 20), mode: str = "RGBA", **save) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, (200, 30, 30) if mode == "RGB" else (200, 30, 30, 255)).save(buffer, format=fmt, **save)
    return buffer.getvalue()


def _gif(frames: int = 3) -> bytes:
    images = [Image.new("RGB", (16, 16), (i * 60, 0, 0)) for i in range(frames)]
    buffer = io.BytesIO()
    images[0].save(buffer, format="GIF", save_all=True, append_images=images[1:], duration=80, loop=0)
    return buffer.getvalue()


async def _upload(client, headers, content: bytes, name: str = "carte_du_front.png", **data):
    return await client.post(
        IMAGES, files={"file": (name, content, "application/octet-stream")}, data=data, headers=headers
    )


async def test_member_uploads_an_image_and_gets_a_public_link(client, player, settings):
    response = await _upload(client, player, _image())
    assert response.status_code == 201, response.text
    image = response.json()
    assert image["title"] == "carte du front" and image["mine"] and image["can_delete"]
    assert (image["width"], image["height"], image["content_type"]) == (40, 20, "image/png")
    assert image["url"].startswith("/media/images/") and image["url"].endswith(".png")
    assert len(image["url"].rsplit("/", 1)[1]) >= 16

    public = await client.get(image["url"])
    assert public.status_code == 200 and public.headers["content-type"] == "image/png"
    assert (settings.media_dir / image["url"].removeprefix("/media/")).is_file()

    listing = (await client.get(IMAGES, headers=player)).json()
    assert [i["id"] for i in listing["images"]] == [image["id"]] and listing["mine_count"] == 1
    assert (await client.get(IMAGES)).status_code == 401

    renamed = await client.patch(f"{IMAGES}/{image['id']}", json={"title": "  Plan   d'attaque "}, headers=player)
    assert renamed.json()["title"] == "Plan d'attaque"


async def test_images_are_reencoded_without_metadata(client, player):
    exif = Image.Exif()
    exif[0x8825] = {2: (48.0, 51.0, 24.0)}
    exif[0x010F] = "Appareil"
    photo = await _upload(client, player, _image("JPEG", (64, 48), "RGB", exif=exif.tobytes()), "photo.jpg")
    assert photo.json()["content_type"] == "image/jpeg"
    stored = (await client.get(photo.json()["url"])).content
    with Image.open(io.BytesIO(stored)) as image:
        assert not image.getexif() and "exif" not in image.info

    animated = await _upload(client, player, _gif(4), "danse.gif", title="Victoire")
    assert animated.json()["content_type"] == "image/gif" and animated.json()["title"] == "Victoire"
    with Image.open(io.BytesIO((await client.get(animated.json()["url"])).content)) as image:
        assert image.n_frames == 4

    buffer = io.BytesIO()
    Image.new("RGBA", (10, 10), (0, 120, 255, 90)).save(buffer, format="WEBP", lossless=True)
    webp = await _upload(client, player, buffer.getvalue(), "transparent.webp")
    assert webp.json()["content_type"] == "image/png"
    assert (await _upload(client, player, b"<script>alert(1)</script>", "x.png")).status_code == 422


async def test_quota_size_and_permissions(client, player, admin, settings):
    settings.hosted_images_per_user = 2
    first = (await _upload(client, player, _image())).json()
    await _upload(client, player, _image())
    full = await _upload(client, player, _image())
    assert full.status_code == 409 and "limite de 2" in full.json()["detail"]

    settings.max_hosted_image_bytes = 64 * 1024
    heavy = await _upload(client, admin, b"0" * (65 * 1024))
    assert heavy.status_code == 422 and "trop lourde" in heavy.json()["detail"]
    settings.max_hosted_image_bytes = 8 * 1024 * 1024
    settings.hosted_images_total_bytes = 1
    assert (await _upload(client, admin, _image())).status_code == 507
    settings.hosted_images_total_bytes = 0

    other = await login(client, "voisin", "player")
    seen = (await client.get(IMAGES, headers=other)).json()["images"]
    assert len(seen) == 2 and not any(i["can_delete"] or i["mine"] for i in seen)
    assert (await client.delete(f"{IMAGES}/{first['id']}", headers=other)).status_code == 403
    assert (await client.patch(f"{IMAGES}/{first['id']}", json={"title": "x"}, headers=other)).status_code == 403
    assert (await client.get(IMAGES, params={"mine": True}, headers=other)).json()["images"] == []

    assert (await client.delete(f"{IMAGES}/{first['id']}", headers=admin)).status_code == 204
    assert not (settings.media_dir / first["url"].removeprefix("/media/")).exists()
    assert (await client.delete(f"{IMAGES}/{first['id']}", headers=admin)).status_code == 404

    log = (await client.get("/api/v1/admin/audit?system=images", headers=admin)).json()
    assert log[0]["summary"] == "Image supprimée : carte du front"
    board = (await client.get("/api/v1/admin/overview", headers=admin)).json()
    images = next(s for s in board["systems"] if s["id"] == "images")
    assert images["stats"][0]["value"] == "1"
