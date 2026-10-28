"""Parcours complets : connexion, synchronisation, Craft, mode admin, hors ligne, reprise de session."""

from __future__ import annotations

import io
import json
from urllib.parse import parse_qs, urlsplit

import httpx
from PIL import Image

from syncron_server.discord import DiscordUser

from ..sample import sample_document


def sign_in(launcher, username="patron", role="admin"):
    launcher.start()
    launcher.dev_login(username, role)
    assert launcher.shell is not None, launcher.login.error_text()
    return launcher.shell


def import_sample(shell, tmp_path):
    transfer = admin_section(shell, "craft.transfer")
    path = tmp_path / "catalogue.json"
    path.write_text(json.dumps(sample_document()), encoding="utf-8")
    transfer.load_file(path)
    transfer._run(dry_run=True)
    assert "rien n'a été écrit" in transfer.report_text
    transfer._run(dry_run=False)
    assert "Import appliqué" in transfer.report_text


def admin_page(shell):
    shell.window.show_page("admin")
    return shell.registry.get("admin").page


def admin_section(shell, key, item=None):
    return admin_page(shell).show_section(key, item)


def test_login_screen_offers_dev_login_and_blocks_old_clients(make_launcher, server):
    launcher = make_launcher()
    launcher.start()
    assert not launcher.login._dev_box.isHidden()
    assert launcher.login.discord_button.isEnabled()
    server.settings.min_client_version = "99.0.0"
    old = make_launcher()
    old.start()
    assert not old.login.discord_button.isEnabled() and not old.login._update.isHidden()


def test_admin_imports_then_craft_calculates(make_launcher, tmp_path):
    shell = sign_in(make_launcher())
    assert "admin" in shell.registry
    import_sample(shell, tmp_path)
    shell.window.open_in_tool("craft", "machine_x")
    plan = shell.registry.get("craft").page.detail_panel.plan
    raws = {r.item_id: r.required for r in plan.raw_materials}
    assert raws == {"lingot_etain": 18, "bois": 6, "quartz": 28, "pierre": 12, "redstone": 6}
    assert shell.host.catalog.revision == 1


def test_player_has_no_admin_tool(make_launcher):
    shell = sign_in(make_launcher(), "joueur", "player")
    assert "admin" not in shell.registry and "craft" in shell.registry
    assert shell.host.session.role.label == "Membre"


def test_item_editor_creates_and_refuses_invalid_recipes(make_launcher, tmp_path):
    shell = sign_in(make_launcher())
    import_sample(shell, tmp_path)
    editor = admin_section(shell, "craft.items")
    editor.load(None)
    editor.name_field.setText("Plaque de fer")
    editor.id_field.setText("plaque_fer")
    editor.type_field.set_current_index(1)
    editor.time_field.setText("1m30")
    editor.ingredients.add_line("fer", 2)
    editor.requirements.add_line("ingenieur", 5)
    editor._save()
    assert editor.banner.isHidden(), editor.banner.text()
    item = shell.host.catalog.data
    created = next(i for i in item.items if i.id == "plaque_fer")
    assert created.recipe.time_seconds == 90 and created.recipe.ingredients[0].quantity == 2
    assert created.recipe.station_id is None

    editor.load("fer")
    editor.type_field.set_current_index(1)
    editor.ingredients.add_line("vis", 1)
    editor._save()
    assert not editor.banner.isHidden() and "circulaire" in editor.banner.text()


def test_deleting_used_station_shows_reason(make_launcher, tmp_path):
    shell = sign_in(make_launcher())
    import_sample(shell, tmp_path)
    stations = admin_section(shell, "craft.stations", "atelier_energie")
    assert "Machine X" in stations.usage.text()
    stations.ctx.call(lambda: stations.ctx.api.delete_entity("stations", "atelier_energie"), banner=stations.banner)
    assert "Machine X" in stations.banner.text()


def test_image_upload_reaches_client_cache(make_launcher, tmp_path):
    shell = sign_in(make_launcher())
    import_sample(shell, tmp_path)
    editor = admin_section(shell, "craft.items", "quartz")
    image = tmp_path / "quartz.png"
    buffer = io.BytesIO()
    Image.new("RGBA", (16, 16), (240, 230, 220, 255)).save(buffer, format="PNG")
    image.write_bytes(buffer.getvalue())
    editor.image_field.upload(image)
    quartz = next(i for i in shell.host.catalog.data.items if i.id == "quartz")
    assert quartz.image and shell.host.catalog.image_path(quartz.image) is not None


def test_users_management_and_audit(make_launcher, server, tmp_path):
    other = make_launcher(user_dir=tmp_path / "other")
    sign_in(other, "recrue", "player")
    shell = sign_in(make_launcher())
    users = admin_section(shell, "admin.users")
    recrue = next(u for u in users.users() if u["username"] == "recrue")
    users.patch(recrue, role="editor")
    recrue = next(u for u in users.users() if u["username"] == "recrue")
    assert recrue["role"] == "editor" and recrue["permissions"] == []
    users.patch(recrue, permissions=["calendar"])
    assert next(u for u in users.users() if u["username"] == "recrue")["permissions"] == ["calendar"]
    audit = admin_section(shell, "admin.audit")
    assert "recrue" in audit.entries()[0]["summary"] and audit.entries()[0]["system"] == "accounts"
    audit.set_system("craft")
    assert audit.entries() == []
    overview = admin_section(shell, "admin.overview")
    assert "2 compte(s)" in overview.accounts_text.text()
    assert list(overview.cards) == ["craft", "research", "calendar", "messages"]
    assert "Recettes sans temps de fabrication" not in overview.cards["craft"].todo


def test_export_writes_reimportable_file(make_launcher, tmp_path):
    shell = sign_in(make_launcher())
    import_sample(shell, tmp_path)
    target = tmp_path / "export.json"
    admin_section(shell, "craft.transfer").export_to(target)
    assert set(json.loads(target.read_text(encoding="utf-8"))["items"]) == set(sample_document()["items"])


def test_logout_then_resume_from_stored_session(make_launcher, tmp_path):
    user_dir = tmp_path / "resume"
    first = make_launcher(user_dir=user_dir)
    shell = sign_in(first)
    import_sample(shell, tmp_path)
    first.shell.window.close()
    second = make_launcher(user_dir=user_dir)
    second.start()
    assert second.shell is not None and second.session.display_name == "patron"
    second.logout()
    assert second.shell is None and not second.login.isHidden()
    third = make_launcher(user_dir=user_dir)
    third.start()
    assert third.shell is None


def test_offline_mode_uses_cached_catalog(make_launcher, tmp_path):
    user_dir = tmp_path / "offline"
    online = make_launcher(user_dir=user_dir)
    import_sample(sign_in(online), tmp_path)
    online.shell.window.close()
    offline = make_launcher(server_url="http://127.0.0.1:9", user_dir=user_dir)
    offline.start()
    assert offline.shell is None and not offline.login.offline_button.isHidden()
    offline.open_offline()
    shell = offline.shell
    assert shell is not None and shell.window.top_bar.offline_visible()
    assert "admin" not in shell.registry
    shell.window.open_in_tool("craft", "vis")
    assert shell.registry.get("craft").page.detail_panel.plan is not None


def test_discord_login_through_loopback(make_launcher, server):
    server.discord.users["code-ok"] = DiscordUser("100000000000000001", "chef", "Le Chef", None)

    def browser(url: str) -> None:
        with httpx.Client() as http:
            start = http.get(url)
            state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
            back = http.get(f"{server.url}/api/v1/auth/discord/callback", params={"state": state, "code": "code-ok"})
            page = http.get(back.headers["location"])
            assert "Connexion réussie" in page.text

    launcher = make_launcher(browser=browser)
    launcher.start()
    launcher.login_with_discord()
    assert launcher.shell is not None, launcher.login.error_text()
    assert launcher.session.role.value == "admin" and launcher.session.display_name == "Le Chef"


def test_discord_refusal_is_explained(make_launcher, server):
    server.settings.discord_required_guild_id = "777"
    server.discord.users["code-x"] = DiscordUser("555", "inconnu", None, None)

    def browser(url: str) -> None:
        with httpx.Client() as http:
            start = http.get(url)
            state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
            back = http.get(f"{server.url}/api/v1/auth/discord/callback", params={"state": state, "code": "code-x"})
            http.get(back.headers["location"])

    try:
        launcher = make_launcher(browser=browser)
        launcher.start()
        launcher.login_with_discord()
        assert launcher.shell is None and "pas membre" in launcher.login.error_text()
    finally:
        server.settings.discord_required_guild_id = ""


def test_relogin_in_same_session_does_not_touch_closed_pages(make_launcher, tmp_path):
    launcher = make_launcher()
    shell = sign_in(launcher)
    import_sample(shell, tmp_path)
    shell.window.open_in_tool("craft", "vis")
    launcher.logout()
    shell = sign_in(launcher, "patron", "admin")
    editor = admin_section(shell, "craft.items", "quartz")
    editor.name_field.setText("Quartz pur")
    editor._save()
    assert next(i for i in launcher.catalog.data.items if i.id == "quartz").name == "Quartz pur"
    assert launcher.shell.registry.get("craft").catalog.get("quartz").name == "Quartz pur"
