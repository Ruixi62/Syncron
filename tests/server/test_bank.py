"""Banque du pays : solde, opérations, contributeurs, droits."""

from __future__ import annotations

from .conftest import login

BANK = "/api/v1/bank"
ADMIN = "/api/v1/admin/bank/transactions"


async def _user_id(client, admin, username):
    users = (await client.get("/api/v1/admin/users", params={"q": username}, headers=admin)).json()
    return next(u["id"] for u in users if u["username"] == username)


async def test_bank_operations_balance_and_contributors(client, admin, player):
    empty = (await client.get(BANK, headers=player)).json()
    assert empty["balance"] == 0 and empty["transactions"] == [] and empty["contributors"] == []

    joueur = await _user_id(client, admin, "joueur")
    entries = [
        {"amount": 50_000, "label": "Fonds de départ", "category": "other"},
        {"amount": 12_000, "label": "Cotisation", "category": "contribution", "member_id": joueur},
        {"amount": 8_000, "label": "Cotisation", "category": "contribution", "member_name": "Visiteur_7"},
        {"amount": 3_000, "label": "Cotisation", "category": "contribution", "member_id": joueur},
        {"amount": -20_000, "label": "Achat de TNT", "category": "war"},
    ]
    created = []
    for entry in entries:
        response = await client.post(ADMIN, json=entry, headers=admin)
        assert response.status_code == 201, response.text
        created.append(response.json())
    assert created[1]["member"] == "joueur" and created[2]["member"] == "Visiteur_7"

    state = (await client.get(BANK, headers=player)).json()
    assert state["balance"] == 53_000 and state["count"] == 5
    assert state["income_30_days"] == 73_000 and state["expenses_30_days"] == 20_000
    assert [(c["member"], c["total"], c["count"]) for c in state["contributors"]] == [
        ("joueur", 15_000, 2),
        ("Visiteur_7", 8_000, 1),
    ]
    assert state["transactions"][0]["label"] == "Achat de TNT"

    fixed = {**entries[4], "amount": -15_000}
    edited = await client.put(f"{ADMIN}/{created[4]['id']}", json=fixed, headers=admin)
    assert edited.status_code == 200 and edited.json()["amount"] == -15_000
    assert (await client.delete(f"{ADMIN}/{created[0]['id']}", headers=admin)).status_code == 204
    assert (await client.get(BANK, headers=player)).json()["balance"] == 8_000

    for bad in (
        {"amount": 0, "label": "x"},
        {"amount": 10, "label": ""},
        {"amount": 10, "label": "x", "category": "y"},
    ):
        assert (await client.post(ADMIN, json=bad, headers=admin)).status_code == 422
    unknown = {"amount": 10, "label": "x", "member_id": "00000000-0000-0000-0000-000000000000"}
    assert (await client.post(ADMIN, json=unknown, headers=admin)).status_code == 422
    assert (await client.post(ADMIN, json=entries[0], headers=player)).status_code == 403
    assert (await client.delete(f"{ADMIN}/{created[1]['id']}", headers=player)).status_code == 403

    treasurer = await login(client, "tresorier", "editor")
    tid = await _user_id(client, admin, "tresorier")
    await client.patch(f"/api/v1/admin/users/{tid}", json={"permissions": ["bank"]}, headers=admin)
    assert (await client.post(ADMIN, json=entries[0], headers=treasurer)).status_code == 201

    log = (await client.get("/api/v1/admin/audit?system=bank", headers=admin)).json()
    assert log[0]["summary"].startswith("Banque : ajout +50")
    board = (await client.get("/api/v1/admin/overview", headers=admin)).json()
    assert next(s for s in board["systems"] if s["id"] == "bank")["stats"][0]["value"].endswith("$")
