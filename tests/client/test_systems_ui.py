"""Parcours des systèmes ajoutés en 4.1 : accueil, messagerie et notifications, calendrier, R&D,
convertisseur, administration découpée par système."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt, QTime

from syncron_client.tools.research.model import Line, TierStatus

from .test_end_to_end import admin_section, import_sample, sign_in


def member(make_launcher, tmp_path, name="membre"):
    return sign_in(make_launcher(user_dir=tmp_path / name), name, "player")


def test_home_lists_country_tools_without_admin_and_hides_search(make_launcher, server):
    server.settings.nation_name = "Empire du Levant"
    shell = sign_in(make_launcher())
    window = shell.window
    window.show_page("home")
    assert window._home.card_ids == ["craft", "research", "calendar", "converter"]
    assert window._home._title.text() == "Empire du Levant"
    assert "outils internes de Empire du Levant" in window._home._intro.text()
    assert not window.top_bar.search_visible()
    window.show_page("craft")
    assert window.top_bar.search_visible()


def test_welcome_message_notifies_and_is_read_from_the_mailbox(make_launcher, tmp_path):
    shell = member(make_launcher, tmp_path)
    window = shell.window
    assert window.toast.message() == "Nouveau message : Bienvenue sur Syncron"
    assert window.top_bar.unread_text() == "1" and window.sidebar.badge_text("mailbox") == "1"
    window.top_bar.notificationsRequested.emit()
    page = shell.registry.get("mailbox").page
    assert window.current_page == "mailbox" and [m["title"] for m in page.messages] == ["Bienvenue sur Syncron"]
    page.list.setCurrentRow(0)
    assert page.view.title.text() == "Bienvenue sur Syncron"
    assert shell.host.notifications.unread == 0 and window.top_bar.unread_text() == ""
    page.delete(page.messages[0]["id"])
    assert page.messages == []


def test_announcement_reaches_members(make_launcher, tmp_path):
    reader = member(make_launcher, tmp_path, "lecteur")
    admin = sign_in(make_launcher(user_dir=tmp_path / "chef"), "chef", "admin")
    announcements = admin_section(admin, "messages.announcements")
    announcements.title_field.setText("Mobilisation")
    announcements.body_field.setPlainText("Tous au QG à 21 h.")
    announcements.send()
    assert announcements.sent[0]["title"] == "Mobilisation" and announcements.sent[0]["recipients"] == 2

    announcements.set_audience("users")
    announcements.choose({"chef"})
    announcements.title_field.setText("Note perso")
    announcements.send()

    reader.host.notifications.poll()
    assert reader.window.toast.message() == "Nouveau message : Mobilisation"
    reader.window.show_page("mailbox")
    titles = [m["title"] for m in reader.registry.get("mailbox").page.messages]
    assert titles == ["Mobilisation", "Bienvenue sur Syncron"]


def test_calendar_event_created_in_admin_is_shown_and_announced(make_launcher, tmp_path):
    reader = member(make_launcher, tmp_path, "lecteur")
    admin = sign_in(make_launcher(user_dir=tmp_path / "chef"), "chef", "admin")
    day = date.today() + timedelta(days=3)
    events = admin_section(admin, "calendar.events", f"new:{day.isoformat()}")
    assert events.current_id is None and events.start_date.date() == QDate(day.year, day.month, day.day)
    events.title_field.setText("Assaut sur Lyon")
    events.category_field.setCurrentIndex(events.category_field.findData("war"))
    events.start_time.setTime(QTime(21, 0))
    events.location_field.setText("Frontière est")
    events.save()
    assert events.banner.isHidden(), events.banner.text()
    assert events.current_id is not None and events.list.count() == 1

    admin.window.show_page("calendar")
    calendar = admin.registry.get("calendar").page
    calendar.select_day(day)
    assert calendar.day_event_titles() == ["Assaut sur Lyon"] and calendar.new_button.isVisible()

    reader.host.notifications.poll()
    reader.window.show_page("mailbox")
    message = reader.registry.get("mailbox").page.messages[0]
    assert message["title"] == "Nouvel événement : Assaut sur Lyon" and message["link_tool"] == "calendar"
    reader.window.open_in_tool(message["link_tool"], message["link_key"])
    page = reader.registry.get("calendar").page
    assert reader.window.current_page == "calendar" and page.selected_day == day
    assert page.day_event_titles() == ["Assaut sur Lyon"] and not page.new_button.isVisible()


def test_research_tiers_edited_in_admin_show_progress(make_launcher, tmp_path):
    reader = member(make_launcher, tmp_path, "lecteur")
    admin = sign_in(make_launcher(user_dir=tmp_path / "chef"), "chef", "admin")
    import_sample(admin, tmp_path)
    research = admin_section(admin, "research.domains", "militaire:1")
    assert research.current_id == "militaire" and research.current_level == 1
    research.tier_name_field.setText("Fondations")
    research.conditions.add_line(Line("", 2000, "quartz"))
    research.conditions.add_line(Line("Avoir 10 membres", done=True))
    research.rewards.add_line(Line("+5 % de vitesse de craft"))
    research.save_tier()
    assert research.tier_banner.isHidden(), research.tier_banner.text()
    research.completed_field.setValue(1)
    research.active_field.setChecked(True)
    research.save_domain()
    assert research.domain_banner.isHidden(), research.domain_banner.text()

    reader.window.show_page("research")
    page = reader.registry.get("research").page
    assert [(d.id, d.tier_count) for d in page.domains] == [
        ("global", 16),
        ("militaire", 16),
        ("ressources", 15),
        ("industrie", 12),
        ("technologie", 7),
    ]
    assert page.selected.id == "militaire" and not page.manage_button.isVisible()
    first, second = page.tier_cards[1], page.tier_cards[2]
    assert first.status is TierStatus.DONE and second.status is TierStatus.ACTIVE
    assert first.tier.conditions[0].describe(reader.registry.get("research")._catalog) == "2 000 × Quartz"
    assert reader.registry.get("research").status().message == "Militaire : palier 2 en cours"

    reader.host.notifications.poll()
    reader.window.show_page("mailbox")
    titles = [m["title"] for m in reader.registry.get("mailbox").page.messages]
    assert titles[:2] == ["Recherche lancée : Militaire, palier 2", "R&D Militaire : palier 1 terminé"]


def test_converter_modes(make_launcher, tmp_path):
    shell = member(make_launcher, tmp_path)
    shell.window.show_page("converter")
    tool = shell.registry.get("converter")
    page = tool.page
    page.set_quantity("648")
    assert page.breakdown.text() == "1 ligne + 1 stack + 8 objets seuls"
    page.set_quantity("5000")
    assert page.breakdown.text() == "1 double coffre + 2 lignes + 6 stacks + 8 objets seuls"
    assert page._tiles["double_coffre"]._value.full_text() == "2"
    page.unit_boxes["double_coffre"].setChecked(False)
    page.unit_boxes["ligne"].setChecked(False)
    assert page.breakdown.text() == "2 coffres + 24 stacks + 8 objets seuls"

    page.set_mode("single", "stack")
    page.set_quantity("648")
    assert page.breakdown.text() == "10 stacks + 8 objets seuls"
    assert page.detail.text().startswith("Soit 10,125 stacks")
    page.set_mode("single", "coffre")
    assert page.breakdown.text() == "648 objets seuls"
    assert tool._settings.get("preferences")["mode"] == "single"

    page.set_mode("euclidean")
    page.set_quantity("3 coffres + 12")
    assert page.breakdown.quantity == 5196
    page.stack_choice.set_current_index(1)
    assert page.breakdown.quantity == 3 * 432 + 12
    page.set_quantity("10 billes")
    assert page.breakdown is None and "billes" in page.error.text()
    page._spins["ligne"].setValue(2)
    page._use_composed()
    assert page.breakdown.quantity == 288


def test_editor_only_sees_the_systems_entrusted_to_them(make_launcher, tmp_path):
    launcher = make_launcher(user_dir=tmp_path / "planner")
    launcher.start()
    launcher._signed_in(launcher.api.dev_login("planner", "editor", ["calendar"]))
    shell = launcher.shell
    admin = shell.registry.get("admin")
    assert [group.title for group in admin.groups()] == ["Général", "Calendrier"]
    page = admin_section(shell, "admin.overview")
    assert list(page.cards) == ["calendar"] and page.accounts.isHidden()
    assert "admin.users" not in shell.registry.get("admin").page.section_keys
    shell.window.show_page("research")
    assert not shell.registry.get("research").page.manage_button.isVisible()
    shell.window.show_page("calendar")
    assert shell.registry.get("calendar").page.new_button.isVisible()


def test_offline_mode_keeps_research_and_calendar(make_launcher, tmp_path):
    user_dir = tmp_path / "nomade"
    online = make_launcher(user_dir=user_dir)
    shell = sign_in(online, "nomade", "admin")
    import_sample(shell, tmp_path)
    shell.window.show_page("research")
    shell.window.show_page("calendar")
    online.shell.window.close()

    offline = make_launcher(server_url="http://127.0.0.1:9", user_dir=user_dir)
    offline.start()
    offline.open_offline()
    shell = offline.shell
    assert not shell.window.top_bar.unread_text()
    shell.window.show_page("research")
    assert len(shell.registry.get("research").page.domains) == 5
    shell.window.show_page("calendar")
    shell.window.show_page("mailbox")
    assert "Hors ligne" in shell.registry.get("mailbox").page.count.text()


# -- 4.3 ----------------------------------------------------------------------------------------


def test_research_progress_is_tracked_from_the_research_page(make_launcher, tmp_path):
    reader = member(make_launcher, tmp_path, "lecteur")
    chef = sign_in(make_launcher(user_dir=tmp_path / "chef"), "chef", "admin")
    admin = admin_section(chef, "research.domains", "militaire:1")
    first = admin.conditions.add_line(Line("Déposer des circuits élites"))
    first.quantity_field.setValue(1000)
    admin.conditions.add_line(Line("Casser des minerais obscurs", 180))
    admin.conditions.add_line(Line("Avoir 10 membres"))
    admin.rewards.add_line(Line("Tourelles"))
    admin.save_tier()
    assert admin.tier_banner.isHidden(), admin.tier_banner.text()
    ids = [row.line_id for row in admin.conditions.rows]
    assert all(ids)

    chef.window.show_page("research")
    tool = chef.registry.get("research")
    tool.page.select("militaire")
    card = tool.page.tier_cards[1]
    card.rows[0].set_progress(380)
    card = tool.page.tier_cards[1]
    assert card.rows[0].line.progress == 380 and not card.rows[0].line.done
    card.rows[2].done_box.setChecked(True)
    card = tool.page.tier_cards[1]
    assert card.rows[2].line.done and card.rows[2].done_box.isChecked()
    card.rows[1].set_progress(180)
    assert tool.page.tier_cards[1].rows[1].line.done

    tool.run_action("militaire", "start", 1)
    assert tool.page.tier_cards[1].status is TierStatus.ACTIVE
    tool.run_action("militaire", "complete", 1)
    assert tool.page.tier_cards[1].status is TierStatus.DONE and tool.page.selected.completed == 1

    admin = admin_section(chef, "research.domains", "militaire:1")
    assert [row.line_id for row in admin.conditions.rows] == ids
    assert admin.conditions.rows[0].progress_field.value() == 380
    admin.select_tier(2)
    admin.copy_previous()
    copied = admin.conditions.lines()[0]
    assert copied.text == "Déposer des circuits élites" and copied.id is None and not copied.progress

    reader.window.show_page("research")
    page = reader.registry.get("research").page
    page.select("militaire")
    rows = page.tier_cards[1].rows
    assert rows[0].progress_spin is None and rows[0].done_box is None
    assert rows[0].line.progress_text() == "380 / 1 000"


def test_recurring_and_single_day_events(make_launcher, tmp_path):
    chef = sign_in(make_launcher(user_dir=tmp_path / "chef"), "chef", "admin")
    today = date.today()
    first = today + timedelta(days=(5 - today.weekday()) % 7 or 7)  # prochain samedi
    events = admin_section(chef, "calendar.events", f"new:{first.isoformat()}")
    events.title_field.setText("Conseil du samedi avec un titre vraiment très long pour la case")
    events.start_time.setTime(QTime(21, 0))
    events.repeat_field.setCurrentIndex(events.repeat_field.findData("weekly"))
    assert events.weekdays.days() == [5] and events.summary.text().startswith("Chaque samedi à 21:00")
    events.notify_field.setChecked(False)
    events.save()
    assert events.banner.isHidden(), events.banner.text()

    events.open_key(f"new:{(first + timedelta(days=1)).isoformat()}")
    events.title_field.setText("Jour du marché")
    events.set_kind(1)
    events.repeat_field.setCurrentIndex(0)
    events.notify_field.setChecked(False)
    events.save()
    assert events.payload()["all_day"] and events.payload()["ends_at"] is None
    assert len(events._events) == 2

    chef.window.show_page("calendar")
    tool = chef.registry.get("calendar")
    page = tool.page
    page.select_day(first)
    occurrences = [e for e in page.events if e.title.startswith("Conseil")]
    assert len(occurrences) >= 2 and all(e.recurring for e in occurrences)
    assert page.day_event_titles() == ["Conseil du samedi avec un titre vraiment très long pour la case"]
    assert page.month_view.visible_lines(0) >= 0
    page.select_day(first + timedelta(days=1))
    assert page.day_event_titles() == ["Jour du marché"]

    tool.skip(occurrences[0].id, first, notify=False)
    page.select_day(first)
    assert page.day_event_titles() == []
    market = first + timedelta(days=1)
    tool.load_month(market.year, market.month)
    page.view_choice.set_current_index(1)
    assert page.list_mode and "Jour du marché" in page.list_titles()


def test_user_text_is_never_rendered_as_html(make_launcher, tmp_path):
    reader = member(make_launcher, tmp_path, "lecteur")
    chef = sign_in(make_launcher(user_dir=tmp_path / "chef"), "chef", "admin")
    announcements = admin_section(chef, "messages.announcements")
    announcements.title_field.setText("<b>Piège</b> <a href='http://x'>clic</a>")
    announcements.send()
    reader.host.notifications.poll()
    reader.window.show_page("mailbox")
    page = reader.registry.get("mailbox").page
    page.list.setCurrentRow(0)
    assert page.view.title.textFormat() == Qt.TextFormat.PlainText
    assert page.view.title.text() == "<b>Piège</b> <a href='http://x'>clic</a>"
