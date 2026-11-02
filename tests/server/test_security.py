"""Protections : limite de débit sur la connexion, taille des requêtes, images piégées, identifiants."""

from __future__ import annotations

import io
import struct
import zlib

from PIL import Image

from .conftest import login


def _png_header_only(width: int, height: int) -> bytes:
    """PNG valide en apparence, aux dimensions énormes (bombe de décompression)."""
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = b"IHDR" + header
    ihdr = struct.pack(">I", len(header)) + chunk + struct.pack(">I", zlib.crc32(chunk))
    data = zlib.compress(b"\x00" * 64)
    idat_chunk = b"IDAT" + data
    idat = struct.pack(">I", len(data)) + idat_chunk + struct.pack(">I", zlib.crc32(idat_chunk))
    end = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + end


async def test_auth_endpoints_are_rate_limited(client, settings):
    settings.auth_rate_limit = 5
    try:
        codes = [
            (await client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 40})).status_code for _ in range(7)
        ]
        assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]
        limited = await client.post("/api/v1/auth/refresh", json={"refresh_token": "x" * 40})
        assert "retry-after" in limited.headers and "réessaie" in limited.json()["detail"]
        assert (await client.get("/api/v1/meta")).status_code == 200
    finally:
        settings.auth_rate_limit = 0


async def test_oversized_bodies_are_refused(client, editor, settings):
    settings.max_request_bytes = 64 * 1024
    try:
        big = {"schema_version": 2, "items": {f"objet_{i}": {"name": "x" * 200} for i in range(600)}}
        refused = await client.post("/api/v1/admin/craft/import", json=big, headers=editor)
        assert refused.status_code == 413
    finally:
        settings.max_request_bytes = 5 * 1024 * 1024


async def test_image_bombs_and_unknown_targets_are_refused(client, seeded, editor, settings):
    bomb = _png_header_only(30_000, 30_000)
    refused = await client.put(
        "/api/v1/admin/craft/items/quartz/image", files={"file": ("x.png", bomb, "image/png")}, headers=editor
    )
    assert refused.status_code == 409 and "trop grande" in refused.json()["detail"]
    buffer = io.BytesIO()
    Image.new("RGBA", (8, 8)).save(buffer, format="PNG")
    unknown = await client.put(
        "/api/v1/admin/craft/items/inconnu/image",
        files={"file": ("x.png", buffer.getvalue(), "image/png")},
        headers=editor,
    )
    assert unknown.status_code == 404
    assert not (settings.media_dir / "items").exists() or not any((settings.media_dir / "items").iterdir())
    invalid = await client.put(
        "/api/v1/admin/craft/items/Mauvais%20ID/image",
        files={"file": ("x.png", buffer.getvalue(), "image/png")},
        headers=editor,
    )
    assert invalid.status_code == 422


async def test_role_change_applies_immediately_to_existing_tokens(client, admin):
    editor = await login(client, "temporaire", "editor")
    users = (await client.get("/api/v1/admin/users", params={"q": "temporaire"}, headers=admin)).json()
    await client.patch(f"/api/v1/admin/users/{users[0]['id']}", json={"role": "player"}, headers=admin)
    refused = await client.post("/api/v1/admin/calendar/events", json={"title": "x"}, headers=editor)
    assert refused.status_code == 403


# -- 5.1 ----------------------------------------------------------------------------------------


async def test_image_uploads_are_rate_limited_per_member(client, settings, player):
    from syncron_server.protection import SlidingWindow

    client._transport.app.state.image_uploads = SlidingWindow(2, 600)
    buffer = io.BytesIO()
    Image.new("RGBA", (8, 8), (10, 20, 30, 255)).save(buffer, format="PNG")
    files = {"file": ("x.png", buffer.getvalue(), "image/png")}
    statuses = [(await client.post("/api/v1/images", files=files, headers=player)).status_code for _ in range(3)]
    assert statuses == [201, 201, 429]


def test_discord_avatar_hash_is_validated():
    from syncron_server.routers.auth import AVATAR_HASH

    assert AVATAR_HASH.match("a_" + "0123456789abcdef" * 2) and AVATAR_HASH.match("f" * 32)
    for bad in ("../../x", "f" * 31, "F" * 32, "abc?size=1", "f" * 32 + "/x"):
        assert not AVATAR_HASH.match(bad)


def test_window_limits_and_trusted_proxies():
    from syncron_server.__main__ import TRUSTED_PROXIES
    from syncron_server.protection import SlidingWindow

    now = [0.0]
    window = SlidingWindow(2, 60, clock=lambda: now[0])
    assert window.allow("a") and window.allow("a") and not window.allow("a") and window.allow("b")
    now[0] = 61
    assert window.allow("a")
    assert "*" not in TRUSTED_PROXIES and "172.16.0.0/12" in TRUSTED_PROXIES
