"""Administration par système, R&D, calendrier, messagerie."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .conftest import login

RESEARCH = "/api/v1/admin/research/categories"
EVENTS = "/api/v1/admin/calendar/events"


async def _inbox(client, headers, **params):
    response = await client.get("/api/v1/inbox", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _user_id(client, admin, username):
    users = (await client.get("/api/v1/admin/users", params={"q": username}, headers=admin)).json()
    return next(u["id"] for u in users if u["username"] == username)


# -- administration --------------------------------------------------------------------------


async def test_overview_is_split_by_system_and_permission(client, seeded, admin, player):
    craft_only = await login(client, "artisan", "editor")
    artisan = await _user_id(client, admin, "artisan")
    await client.patch(f"/api/v1/admin/users/{artisan}", json={"permissions": ["craft"]}, headers=admin)

    board = (await client.get("/api/v1/admin/overview", headers=admin)).json()
    assert [s["id"] for s in board["systems"]] == ["craft", "research", "calendar", "messages"]
    craft = board["systems"][0]
    assert {t["label"] for t in craft["todo"]} == {"Objets sans image", "Objets sans catégorie", "Ateliers sans image"}
    assert craft["stats"][0] == {"label": "Objets", "value": "15", "detail": "6 ressource(s) primaire(s)"}
    research = board["systems"][1]
    assert research["stats"][0]["value"] == "0 / 66"
    assert board["accounts"]["by_role"] == {"player": 1, "editor": 2, "admin": 1}

    limited = (await client.get("/api/v1/admin/overview", headers=craft_only)).json()
    assert [s["id"] for s in limited["systems"]] == ["craft"] and limited["accounts"] is None
    assert all(entry["system"] == "craft" for entry in limited["recent"])
    assert (await client.get("/api/v1/admin/audit?system=accounts", headers=craft_only)).status_code == 403
    assert (await client.get("/api/v1/admin/overview", headers=player)).status_code == 403


async def test_permissions_gate_each_system_and_notify_the_editor(client, admin):
    editor = await login(client, "redac", "editor")
    redac = await _user_id(client, admin, "redac")
    assert (await client.patch(f"/api/v1/admin/users/{redac}", json={"permissions": ["craft"]}, headers=admin)).json()[
        "permissions"
    ] == ["craft"]
    event = {"title": "Réunion", "starts_at": datetime.now(UTC).isoformat()}
    refused = await client.post(EVENTS, json=event, headers=editor)
    assert refused.status_code == 403 and "Calendrier" in refused.json()["detail"]

    granted = await client.patch(
        f"/api/v1/admin/users/{redac}", json={"permissions": ["craft", "calendar"]}, headers=admin
    )
    assert granted.json()["permissions"] == ["calendar", "craft"]
    assert (await client.post(EVENTS, json=event, headers=editor)).status_code == 201
    news = await _inbox(client, editor)
    assert news[0]["title"] == "Ton compte a été mis à jour" and "Calendrier" in news[0]["body"]
    unknown = await client.patch(f"/api/v1/admin/users/{redac}", json={"permissions": ["banque"]}, headers=admin)
    assert unknown.status_code == 422


# -- R&D -----------------------------------------------------------------------------------


async def test_research_has_the_five_domains(client, player):
    research = (await client.get("/api/v1/research", headers=player)).json()["categories"]
    assert [(c["id"], c["tier_count"]) for c in research] == [
        ("global", 16),
        ("militaire", 16),
        ("ressources", 15),
        ("industrie", 12),
        ("technologie", 7),
    ]
    assert len(research[4]["tiers"]) == 7 and research[4]["tiers"][0] == {
        "level": 1,
        "name": "",
        "description": "",
        "conditions": [],
        "rewards": [],
    }


async def test_research_tiers_are_validated_in_order_without_messages(client, seeded, editor, player):
    tier = {
        "name": "Fondations",
        "conditions": [{"text": "", "item_id": "quartz", "quantity": 2000}, {"text": "Avoir 10 membres", "done": True}],
        "rewards": [{"text": "+5 % de vitesse de craft"}],
    }
    saved = await client.put(f"{RESEARCH}/militaire/tiers/1", json=tier, headers=editor)
    assert saved.status_code == 200, saved.text
    first = saved.json()["tiers"][0]
    assert [c["quantity"] for c in first["conditions"]] == [2000, None] and first["conditions"][1]["done"]
    assert first["rewards"] == [{"id": first["rewards"][0]["id"], "text": "+5 % de vitesse de craft"}]
    assert "active" not in saved.json()
    assert (await client.put(f"{RESEARCH}/militaire/tiers/17", json=tier, headers=editor)).status_code == 422
    empty = await client.put(f"{RESEARCH}/militaire/tiers/2", json={"conditions": [{"text": ""}]}, headers=editor)
    assert empty.status_code == 422
    item_reward = {"rewards": [{"item_id": "quartz"}]}
    no_text = await client.put(f"{RESEARCH}/militaire/tiers/2", json=item_reward, headers=editor)
    assert no_text.status_code == 422
    second = {"conditions": [{"text": "Casser 180 minerais", "quantity": 180}], "rewards": [{"text": "Tourelles"}]}
    assert (await client.put(f"{RESEARCH}/militaire/tiers/2", json=second, headers=editor)).status_code == 200

    shrink = {"name": "Militaire", "tier_count": 0}
    refused = await client.put(f"{RESEARCH}/militaire", json=shrink, headers=editor)
    assert refused.status_code == 409 and "1" in refused.json()["detail"]

    validate = f"{RESEARCH}/militaire/tiers/{{}}/validate"
    unmet = await client.post(validate.format(1), headers=editor)
    assert unmet.status_code == 409 and "1 / 2" in unmet.json()["detail"]
    current = (await client.get("/api/v1/research", headers=player)).json()["categories"][1]["tiers"]
    ore = current[1]["conditions"][0]["id"]
    await client.patch(f"/api/v1/admin/research/lines/{ore}", json={"progress": 180, "done": True}, headers=editor)
    out_of_order = await client.post(validate.format(2), headers=editor)
    assert out_of_order.status_code == 409 and "palier 1" in out_of_order.json()["detail"]

    quartz = current[0]["conditions"][0]["id"]
    await client.patch(f"/api/v1/admin/research/lines/{quartz}", json={"progress": 2000}, headers=editor)
    await client.patch(f"/api/v1/admin/research/lines/{quartz}", json={"done": True}, headers=editor)
    assert (await client.post(validate.format(1), headers=player)).status_code == 403
    assert (await client.post(validate.format(1), headers=editor)).json()["completed"] == 1
    assert (await client.post(validate.format(1), headers=editor)).status_code == 409
    assert (await client.post(validate.format(2), headers=editor)).json()["completed"] == 2
    assert (await client.delete(validate.format(1), headers=editor)).status_code == 409
    assert (await client.delete(validate.format(2), headers=editor)).json()["completed"] == 1
    titles = [m["title"] for m in await _inbox(client, player)]
    assert not any("R&D" in title or "Recherche" in title for title in titles)

    too_far = {"name": "Militaire", "tier_count": 16, "completed": 17}
    assert (await client.put(f"{RESEARCH}/militaire", json=too_far, headers=editor)).status_code == 422
    fixed = {"name": "Militaire", "tier_count": 16, "completed": 5}
    assert (await client.put(f"{RESEARCH}/militaire", json=fixed, headers=editor)).json()["completed"] == 5
    assert (await client.put(f"{RESEARCH}/militaire", json=fixed, headers=player)).status_code == 403


async def test_research_domains_can_be_added_and_removed(client, editor, admin):
    created = await client.put(f"{RESEARCH}/espace", json={"name": "Espace", "tier_count": 3}, headers=editor)
    assert created.status_code == 200 and len(created.json()["tiers"]) == 3
    assert (await client.put(f"{RESEARCH}/Espace!", json={"name": "x"}, headers=editor)).status_code == 422
    assert (await client.delete(f"{RESEARCH}/espace", headers=editor)).status_code == 204
    log = (await client.get("/api/v1/admin/audit?system=research", headers=admin)).json()
    assert log[0]["summary"] == "R&D supprimé : Espace"


# -- calendrier ----------------------------------------------------------------------------


async def test_calendar_events_lifecycle(client, editor, player):
    start = datetime(2026, 11, 14, 20, 0, tzinfo=UTC)
    payload = {
        "title": "Assaut sur Lyon",
        "category": "war",
        "location": "Frontière est",
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=2)).isoformat(),
        "notify": True,
    }
    created = await client.post(EVENTS, json=payload, headers=editor)
    assert created.status_code == 201, created.text
    event = created.json()
    assert event["author"] == "editeur"
    message = (await _inbox(client, player))[0]
    assert message["title"] == "Nouvel événement : Assaut sur Lyon"
    assert "samedi 14 novembre à 21:00" in message["body"] and message["link_key"] == event["id"]

    window = {"start": "2026-11-01T00:00:00+01:00", "end": "2026-12-01T00:00:00+01:00"}
    listed = (await client.get("/api/v1/calendar/events", params=window, headers=player)).json()
    assert [e["title"] for e in listed] == ["Assaut sur Lyon"]
    before = {"start": "2026-10-01T00:00:00+00:00", "end": "2026-11-01T00:00:00+00:00"}
    assert (await client.get("/api/v1/calendar/events", params=before, headers=player)).json() == []
    assert (await client.get(f"/api/v1/calendar/events/{event['id']}", headers=player)).json()["title"] == (
        "Assaut sur Lyon"
    )
    naive = {"start": "2026-11-01T00:00:00", "end": "2026-12-01T00:00:00"}
    assert (await client.get("/api/v1/calendar/events", params=naive, headers=player)).status_code == 422

    payload.update(title="Assaut sur Lyon (reporté)", notify=False)
    updated = await client.put(f"{EVENTS}/{event['id']}", json=payload, headers=editor)
    assert updated.json()["title"] == "Assaut sur Lyon (reporté)"
    backwards = {**payload, "ends_at": (start - timedelta(hours=1)).isoformat()}
    assert (await client.put(f"{EVENTS}/{event['id']}", json=backwards, headers=editor)).status_code == 422
    assert (await client.post(EVENTS, json=payload, headers=player)).status_code == 403

    assert (await client.delete(f"{EVENTS}/{event['id']}?notify=true", headers=editor)).status_code == 204
    assert (await _inbox(client, player))[0]["title"] == "Événement annulé : Assaut sur Lyon (reporté)"
    assert (await client.delete(f"{EVENTS}/{event['id']}", headers=editor)).status_code == 404


# -- messagerie ------------------------------------------------------------------------------


async def test_inbox_welcome_read_and_delete(client, admin, player):
    inbox = await _inbox(client, player)
    assert [m["title"] for m in inbox] == ["Bienvenue sur Syncron"] and not inbox[0]["read"]
    staff = await _inbox(client, admin)
    assert any(m["title"] == "Nouveau compte : joueur" for m in staff)

    summary = (await client.get("/api/v1/inbox/summary", headers=player)).json()
    assert summary == {"unread": 1, "latest_id": inbox[0]["id"]}
    after = (await client.post("/api/v1/inbox/read", json={"ids": [inbox[0]["id"]]}, headers=player)).json()
    assert after["unread"] == 0
    assert (await _inbox(client, player))[0]["read"]
    assert (await client.delete(f"/api/v1/inbox/{inbox[0]['id']}", headers=player)).json()["latest_id"] == 0
    assert await _inbox(client, player) == []
    assert (await client.delete(f"/api/v1/inbox/{inbox[0]['id']}", headers=player)).status_code == 404
    others = [m["id"] for m in staff]
    assert (await client.post("/api/v1/inbox/read", json={"ids": others}, headers=player)).json()["unread"] == 0


async def test_announcements_reach_their_audience(client, editor, admin, player):
    other = await login(client, "voisin", "player")
    to_all = await client.post(
        "/api/v1/admin/messages", json={"title": "Mobilisation", "body": "Tous à la base."}, headers=editor
    )
    assert to_all.status_code == 201 and to_all.json()["recipients"] == 4
    joueur = await _user_id(client, admin, "joueur")
    direct = {"title": "Mission", "audience": "users", "user_ids": [joueur]}
    assert (await client.post("/api/v1/admin/messages", json=direct, headers=editor)).json()["recipients"] == 1
    staff = {"title": "Réunion de l'équipe", "audience": "staff"}
    assert (await client.post("/api/v1/admin/messages", json=staff, headers=editor)).json()["recipients"] == 2

    assert [m["title"] for m in await _inbox(client, player)][:2] == ["Mission", "Mobilisation"]
    voisin = [m["title"] for m in await _inbox(client, other)]
    assert "Mobilisation" in voisin and "Mission" not in voisin and "Réunion de l'équipe" not in voisin
    assert "Réunion de l'équipe" in [m["title"] for m in await _inbox(client, admin)]
    mine = await _inbox(client, editor)
    assert next(m for m in mine if m["title"] == "Mobilisation")["read"]

    unread = await _inbox(client, player, unread_only="true")
    assert all(not m["read"] for m in unread)
    assert (await client.post("/api/v1/inbox/read", json={"all": True}, headers=player)).json()["unread"] == 0
    sent = (await client.get("/api/v1/admin/messages", headers=editor)).json()
    assert [m["title"] for m in sent] == ["Réunion de l'équipe", "Mission", "Mobilisation"]
    assert sent[2]["read"] == 2
    assert (await client.delete(f"/api/v1/admin/messages/{sent[2]['id']}", headers=editor)).status_code == 204
    assert "Mobilisation" not in [m["title"] for m in await _inbox(client, other)]
    names = [r["name"] for r in (await client.get("/api/v1/admin/messages/recipients", headers=editor)).json()]
    assert names == ["editeur", "joueur", "patron", "voisin"]
    assert (await client.get("/api/v1/admin/messages/recipients", headers=player)).status_code == 403
    empty = await client.post("/api/v1/admin/messages", json={"title": "x", "audience": "users"}, headers=editor)
    assert empty.status_code == 422
    assert (await client.post("/api/v1/admin/messages", json=staff, headers=player)).status_code == 403


async def test_meta_exposes_systems_and_nation(client, settings):
    settings.nation_name = "Empire du Levant"
    meta = (await client.get("/api/v1/meta")).json()
    assert meta["nation_name"] == "Empire du Levant" and meta["systems"]["research"] == "R&D"


# -- 4.3 : progression des conditions, récurrence -------------------------------------------


async def test_condition_can_only_be_ticked_once_its_quantity_is_reached(client, seeded, editor, admin, player):
    tier = {
        "conditions": [
            {"text": "Déposer des circuits élites", "quantity": 1000, "progress": 0, "done": True},
            {"text": "Casser des minerais obscurs", "quantity": 180},
            {"text": "Avoir 10 membres"},
        ],
        "rewards": [{"text": "Tourelles"}],
    }
    saved = (await client.put(f"{RESEARCH}/militaire/tiers/3", json=tier, headers=editor)).json()
    circuits, ores, members = saved["tiers"][2]["conditions"]
    assert not circuits["done"]
    lines = "/api/v1/admin/research/lines"
    patched = await client.patch(f"{lines}/{circuits['id']}", json={"progress": 380}, headers=editor)
    assert patched.status_code == 200
    first = patched.json()["tiers"][2]["conditions"][0]
    assert (first["progress"], first["quantity"], first["done"]) == (380, 1000, False)
    early = await client.patch(f"{lines}/{circuits['id']}", json={"done": True}, headers=editor)
    assert early.status_code == 422 and "620" in early.json()["detail"]

    full = await client.patch(f"{lines}/{ores['id']}", json={"progress": 180}, headers=editor)
    assert not full.json()["tiers"][2]["conditions"][1]["done"]
    ticked = await client.patch(f"{lines}/{ores['id']}", json={"done": True}, headers=editor)
    assert ticked.json()["tiers"][2]["conditions"][1]["done"]
    lowered = await client.patch(f"{lines}/{ores['id']}", json={"progress": 90}, headers=editor)
    assert not lowered.json()["tiers"][2]["conditions"][1]["done"]
    members_done = await client.patch(f"{lines}/{members['id']}", json={"done": True}, headers=editor)
    assert members_done.json()["tiers"][2]["conditions"][2]["done"]

    assert (await client.patch(f"{lines}/{members['id']}", json={"progress": 3}, headers=editor)).status_code == 422
    reward = saved["tiers"][2]["rewards"][0]["id"]
    assert (await client.patch(f"{lines}/{reward}", json={"done": True}, headers=editor)).status_code == 404
    assert (await client.patch(f"{lines}/{members['id']}", json={"done": True}, headers=player)).status_code == 403

    current = (await client.get("/api/v1/research", headers=player)).json()["categories"][1]["tiers"][2]
    edited = {
        "name": "Défense",
        "conditions": [{**line, "text": line["text"] + " !"} for line in current["conditions"][:2]],
        "rewards": current["rewards"],
    }
    kept = (await client.put(f"{RESEARCH}/militaire/tiers/3", json=edited, headers=editor)).json()["tiers"][2]
    assert [c["id"] for c in kept["conditions"]] == [circuits["id"], ores["id"]]
    assert kept["conditions"][0]["progress"] == 380 and kept["conditions"][0]["text"].endswith("!")
    assert kept["rewards"][0]["id"] == reward

    staff = [m["title"] for m in await _inbox(client, admin)]
    assert not any("R&D" in title for title in staff)
    log = (await client.get("/api/v1/admin/audit?system=research", headers=admin)).json()
    assert any(entry["summary"].endswith("380 / 1000, à faire") for entry in log)


async def test_recurring_events_are_expanded_and_can_skip_a_date(client, editor, player):
    first = datetime(2026, 11, 7, 20, 0, tzinfo=UTC)  # samedi 21 h à Paris
    payload = {
        "title": "Conseil du samedi",
        "category": "meeting",
        "starts_at": first.isoformat(),
        "ends_at": (first + timedelta(hours=1)).isoformat(),
        "recurrence": "weekly",
        "notify": True,
    }
    created = (await client.post(EVENTS, json=payload, headers=editor)).json()
    assert created["recurrence"] == "weekly" and created["occurrence"] is None
    message = (await _inbox(client, player))[0]
    assert "Chaque samedi à 21:00" in message["body"]

    window = {"start": "2026-11-01T00:00:00+01:00", "end": "2026-12-01T00:00:00+01:00"}
    listed = (await client.get("/api/v1/calendar/events", params=window, headers=player)).json()
    assert [e["occurrence"] for e in listed] == ["2026-11-07", "2026-11-14", "2026-11-21", "2026-11-28"]
    winter = datetime.fromisoformat(listed[3]["starts_at"])
    assert winter.utcoffset() is not None and winter.astimezone(UTC).hour == 20

    skip = {"day": "2026-11-14", "notify": True}
    skipped = await client.post(f"{EVENTS}/{created['id']}/skip", json=skip, headers=editor)
    assert skipped.json()["skipped_dates"] == ["2026-11-14"]
    listed = (await client.get("/api/v1/calendar/events", params=window, headers=player)).json()
    assert "2026-11-14" not in [e["occurrence"] for e in listed]
    assert (await _inbox(client, player))[0]["title"].startswith("Annulé : Conseil du samedi, samedi 14 novembre")
    wrong_day = await client.post(f"{EVENTS}/{created['id']}/skip", json={"day": "2026-11-15"}, headers=editor)
    assert wrong_day.status_code == 422
    restore = {"day": "2026-11-14", "skipped": False}
    assert (await client.post(f"{EVENTS}/{created['id']}/skip", json=restore, headers=editor)).json()[
        "skipped_dates"
    ] == []

    until = {**payload, "recurrence_until": "2026-11-20", "notify": False}
    await client.put(f"{EVENTS}/{created['id']}", json=until, headers=editor)
    listed = (await client.get("/api/v1/calendar/events", params=window, headers=player)).json()
    assert [e["occurrence"] for e in listed] == ["2026-11-07", "2026-11-14"]

    too_long = {**payload, "ends_at": (first + timedelta(days=2)).isoformat()}
    assert (await client.post(EVENTS, json=too_long, headers=editor)).status_code == 422


async def test_single_day_event_without_hours(client, editor, player):
    day = datetime(2026, 11, 20, 0, 0, tzinfo=UTC)
    created = await client.post(
        EVENTS, json={"title": "Jour du marché", "starts_at": day.isoformat(), "all_day": True}, headers=editor
    )
    assert created.status_code == 201 and created.json()["all_day"] and created.json()["ends_at"] is None
    window = {"start": "2026-11-20T00:00:00+00:00", "end": "2026-11-21T00:00:00+00:00"}
    assert [
        e["title"] for e in (await client.get("/api/v1/calendar/events", params=window, headers=player)).json()
    ] == ["Jour du marché"]
