from __future__ import annotations

import io

from PIL import Image

from syncron_core.catalog_format import parse_catalog

from ..sample import sample_document

ITEM = "/api/v1/admin/craft/items"


def png_bytes(color=(200, 50, 50, 255), size=(16, 16)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


async def test_import_dry_run_then_apply(client, editor):
    dry = await client.post("/api/v1/admin/craft/import", json=sample_document(), headers=editor)
    assert dry.status_code == 200
    body = dry.json()
    assert body["dry_run"] and not body["applied"] and len(body["items"]["added"]) == 15 and body["revision"] == 0
    applied = await client.post("/api/v1/admin/craft/import?dry_run=false", json=sample_document(), headers=editor)
    assert applied.json()["applied"] and applied.json()["revision"] == 1
    again = await client.post("/api/v1/admin/craft/import?dry_run=false", json=sample_document(), headers=editor)
    assert not again.json()["applied"] and again.json()["items"]["unchanged"] == 15 and again.json()["revision"] == 1


async def test_catalog_roundtrip_and_etag(client, seeded, player):
    response = await client.get("/api/v1/catalog", headers=player)
    assert response.status_code == 200 and response.headers["etag"] == '"rev-1"'
    document = response.json()
    assert document["revision"] == 1
    data = parse_catalog(document).data
    original = parse_catalog(sample_document()).data
    assert {i.id: i.recipe for i in data.items} == {i.id: i.recipe for i in original.items}
    cached = await client.get("/api/v1/catalog", headers={**player, "If-None-Match": '"rev-1"'})
    assert cached.status_code == 304


async def test_craft_plan_endpoint(client, seeded, player):
    response = await client.post("/api/v1/craft/plan", json={"item_id": "machine_x", "quantity": 1}, headers=player)
    assert response.status_code == 200
    raws = {r["id"]: r["required"] for r in response.json()["raw_materials"]}
    assert raws == {"lingot_etain": 18, "bois": 6, "quartz": 28, "pierre": 12, "redstone": 6}
    unknown = await client.post("/api/v1/craft/plan", json={"item_id": "nope"}, headers=player)
    assert unknown.status_code == 400 and "nope" in unknown.json()["detail"]


async def test_player_cannot_write(client, seeded, player):
    response = await client.put(f"{ITEM}/x", json={"name": "X", "type": "raw"}, headers=player)
    assert response.status_code == 403


async def test_create_update_item_bumps_revision_and_audits(client, seeded, editor):
    created = await client.put(
        f"{ITEM}/plaque",
        json={
            "name": "Plaque",
            "type": "crafted",
            "recipe": {"fer": 2},
            "time": "1m30",
            "station_id": "atelier_debutant",
        },
        headers=editor,
    )
    assert created.status_code == 200 and created.json() == {"revision": 2, "changed": True}
    same = await client.put(
        f"{ITEM}/plaque",
        json={"name": "Plaque", "type": "crafted", "recipe": {"fer": 2}, "time": 90, "station_id": "atelier_debutant"},
        headers=editor,
    )
    assert same.json() == {"revision": 2, "changed": False}
    audit = (await client.get("/api/v1/admin/audit", headers=editor)).json()
    assert audit[0]["summary"] == "Objet créé : Plaque" and audit[0]["username"] == "editeur"


async def test_invalid_writes_are_rejected_with_issues(client, seeded, editor):
    unknown = await client.put(
        f"{ITEM}/x", json={"name": "X", "type": "crafted", "recipe": {"ghost": 1}}, headers=editor
    )
    assert unknown.status_code == 422 and "ghost" in unknown.json()["issues"][0]["message"]
    level = await client.put(
        f"{ITEM}/x",
        json={"name": "X", "type": "crafted", "recipe": {"fer": 1}, "requires": {"rd_energie": 99}},
        headers=editor,
    )
    assert level.status_code == 422 and "maximum" in level.json()["issues"][0]["message"]
    cycle = await client.put(
        f"{ITEM}/fer", json={"name": "Fer", "type": "crafted", "recipe": {"vis": 1}}, headers=editor
    )
    assert cycle.status_code == 422 and "circulaire" in cycle.json()["issues"][0]["message"]
    bad_id = await client.put(f"{ITEM}/Pas Bon", json={"name": "X", "type": "raw"}, headers=editor)
    assert bad_id.status_code == 422
    bad_time = await client.put(
        f"{ITEM}/x", json={"name": "X", "type": "crafted", "recipe": {"fer": 1}, "time": "?"}, headers=editor
    )
    assert bad_time.status_code == 422
    revision = (await client.get("/api/v1/meta")).json()["catalog_revision"]
    assert revision == 1


async def test_deleting_used_entities_is_refused_with_explanation(client, seeded, editor):
    used = await client.delete(f"{ITEM}/vis", headers=editor)
    assert used.status_code == 409 and "Support" in used.json()["detail"] and "Cadre" in used.json()["detail"]
    station = await client.delete("/api/v1/admin/craft/stations/atelier_energie", headers=editor)
    assert station.status_code == 409 and "Machine X" in station.json()["detail"]
    skill = await client.delete("/api/v1/admin/craft/skills/ingenieur", headers=editor)
    assert skill.status_code == 409
    free = await client.delete(f"{ITEM}/chassis", headers=editor)
    assert free.status_code == 200
    assert (await client.delete(f"{ITEM}/chassis", headers=editor)).status_code == 404


async def test_switching_raw_to_crafted_and_back(client, seeded, editor):
    to_crafted = await client.put(
        f"{ITEM}/bois", json={"name": "Bois", "type": "crafted", "recipe": {"pierre": 1}, "output": 4}, headers=editor
    )
    assert to_crafted.status_code == 200
    back = await client.put(f"{ITEM}/bois", json={"name": "Bois", "type": "raw"}, headers=editor)
    assert back.status_code == 200
    document = (await client.get("/api/v1/catalog", headers=editor)).json()
    assert document["items"]["bois"] == {"name": "Bois", "type": "raw"}


async def test_stations_and_skills_crud(client, seeded, editor):
    assert (
        await client.put("/api/v1/admin/craft/stations/four", json={"name": "Four"}, headers=editor)
    ).status_code == 200
    assert (
        await client.put(
            "/api/v1/admin/craft/skills/pilote", json={"name": "Pilote", "kind": "job", "max_level": 5}, headers=editor
        )
    ).status_code == 200
    item = await client.put(
        f"{ITEM}/brique",
        json={
            "name": "Brique",
            "type": "crafted",
            "station_id": "four",
            "requires": {"pilote": 2},
            "recipe": {"pierre": 1},
        },
        headers=editor,
    )
    assert item.status_code == 200
    lowered = await client.put(
        "/api/v1/admin/craft/skills/pilote", json={"name": "Pilote", "kind": "job", "max_level": 1}, headers=editor
    )
    assert lowered.status_code == 422


async def test_images_upload_replace_and_delete(client, seeded, editor, settings):
    upload = await client.put(
        f"{ITEM}/quartz/image", files={"file": ("q.png", png_bytes(), "image/png")}, headers=editor
    )
    assert upload.status_code == 200
    url = (await client.get("/api/v1/catalog", headers=editor)).json()["items"]["quartz"]["image"]
    assert url.startswith("/media/items/quartz-")
    served = await client.get(url)
    assert served.status_code == 200 and served.content[:8] == b"\x89PNG\r\n\x1a\n"
    replaced = await client.put(
        f"{ITEM}/quartz/image", files={"file": ("q.png", png_bytes((0, 0, 255, 255)), "image/png")}, headers=editor
    )
    assert replaced.status_code == 200
    files = list((settings.media_dir / "items").iterdir())
    assert len(files) == 1 and files[0].name != url.rsplit("/", 1)[1]
    assert (await client.delete(f"{ITEM}/quartz/image", headers=editor)).status_code == 200
    assert not list((settings.media_dir / "items").iterdir())


async def test_invalid_images_are_rejected(client, seeded, editor, settings):
    not_image = await client.put(
        f"{ITEM}/quartz/image", files={"file": ("q.png", b"hello", "image/png")}, headers=editor
    )
    assert not_image.status_code == 409 and "illisible" in not_image.json()["detail"]
    settings.max_image_bytes = 100
    too_big = await client.put(
        f"{ITEM}/quartz/image", files={"file": ("q.png", png_bytes(size=(64, 64)), "image/png")}, headers=editor
    )
    assert too_big.status_code == 409 and "lourde" in too_big.json()["detail"]
    missing = await client.put(
        f"{ITEM}/absent/image", files={"file": ("q.png", png_bytes(), "image/png")}, headers=editor
    )
    assert missing.status_code in (404, 409)
    assert not (settings.media_dir / "items").exists() or not list((settings.media_dir / "items").iterdir())


async def test_import_replace_is_admin_only_and_removes(client, seeded, editor, admin):
    document = sample_document()
    for item_id in ("chassis", "support", "cadre"):
        del document["items"][item_id]
    forbidden = await client.post(
        "/api/v1/admin/craft/import?mode=replace&dry_run=false", json=document, headers=editor
    )
    assert forbidden.status_code == 403
    result = await client.post("/api/v1/admin/craft/import?mode=replace&dry_run=false", json=document, headers=admin)
    assert sorted(result.json()["items"]["removed"]) == ["cadre", "chassis", "support"]


async def test_import_rejects_invalid_files_and_strips_local_images(client, seeded, editor):
    broken = sample_document()
    broken["items"]["x"] = {"type": "crafted", "recipe": {"inexistant": 1}}
    refused = await client.post("/api/v1/admin/craft/import?dry_run=false", json=broken, headers=editor)
    assert refused.status_code == 422 and refused.json()["issues"][0]["entity_id"] == "x"
    local = sample_document()
    local["items"]["quartz"]["image"] = "minerais/quartz.png"
    report = await client.post("/api/v1/admin/craft/import?dry_run=false", json=local, headers=editor)
    assert report.status_code == 200 and "image" in report.json()["warnings"][0]["message"]


async def test_export_is_reimportable(client, seeded, editor):
    exported = await client.get("/api/v1/admin/craft/export", headers=editor)
    assert "attachment" in exported.headers["content-disposition"]
    dry = (await client.post("/api/v1/admin/craft/import", json=exported.json(), headers=editor)).json()
    assert dry["items"]["unchanged"] == 15 and not dry["items"]["updated"] and not dry["items"]["added"]


async def test_user_management(client, editor, admin, player):
    assert (await client.get("/api/v1/admin/users", headers=editor)).status_code == 403
    users = (await client.get("/api/v1/admin/users", headers=admin)).json()
    joueur = next(u for u in users if u["username"] == "joueur")
    me = next(u for u in users if u["username"] == "patron")
    promoted = await client.patch(f"/api/v1/admin/users/{joueur['id']}", json={"role": "editor"}, headers=admin)
    assert promoted.json()["role"] == "editor"
    assert (
        await client.patch(f"/api/v1/admin/users/{me['id']}", json={"role": "player"}, headers=admin)
    ).status_code == 400
    banned = await client.patch(f"/api/v1/admin/users/{joueur['id']}", json={"is_banned": True}, headers=admin)
    assert banned.json()["is_banned"]
    assert (await client.get("/api/v1/auth/me", headers=player)).status_code == 403
    search = (await client.get("/api/v1/admin/users?q=jou", headers=admin)).json()
    assert [u["username"] for u in search] == ["joueur"]
    log = (await client.get("/api/v1/admin/audit", headers=admin)).json()
    assert "suspendu" in log[0]["summary"] and log[0]["system"] == "accounts"
