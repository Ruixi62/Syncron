"""Page Recherche : liste des pays, carte interactive, fiche du pays / du biome / du monde."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QSizePolicy,
    QStackedLayout,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from syncron_client.tools.intel.map_view import LAYERS, MapView
from syncron_client.tools.intel.model import (
    CHUNK,
    EVENT_COLORS,
    EVENT_ICONS,
    EVENT_NAMES,
    Event,
    Marker,
    World,
    dots,
    thousands,
)
from syncron_client.ui import icons
from syncron_client.ui.format import format_datetime
from syncron_client.ui.tables import KEY_ROLE, fill_rows, make_table, muted_cell, text_cell
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import Banner, EmptyState, FlowWidget, SearchField, button, icon_button, label

KIND_LABELS = {
    "territories": "Territoires",
    "atlas": "Atlas",
    "frontiers": "Frontières",
    "regions": "Régions",
    "state": "Heure du jeu",
    "weather": "Météo",
    "members": "Membres des pays",
}
PANEL_WIDTH = 330


def swatch(color: str, size: int = 12) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


class InfoPanel(QScrollArea):
    """Fiche à droite de la carte : remplie à la demande, en texte brut (données du site)."""

    closed = Signal()
    showRequested = Signal(int, int)  # x, z en blocs

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFixedWidth(PANEL_WIDTH)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._content.setObjectName("IntelPanel")
        self._content.setStyleSheet(f"#IntelPanel {{ background: {COLORS.surface}; border-radius: 12px; }}")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(16, 14, 16, 16)
        self._layout.setSpacing(6)
        self.setWidget(self._content)
        self._grid: QGridLayout | None = None
        self.title = ""

    def clear(self) -> None:
        _empty(self._layout)
        self._grid = None

    def heading(self, title: str, color: str | None = None, icon_name: str | None = None) -> None:
        self.clear()
        self.title = title
        row = QHBoxLayout()
        row.setSpacing(8)
        if icon_name or color:
            badge = label()
            badge.setFixedSize(14, 14)
            if icon_name:
                badge.setFixedSize(18, 18)
                badge.setPixmap(icons.pixmap(icon_name, color or COLORS.accent, 18))
            else:
                badge.setStyleSheet(f"background: {color}; border-radius: 4px;")
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        name = label(title, "heading", wrap=True)
        row.addWidget(name, 1)
        close = icon_button("close", "Fermer la fiche", 16)
        close.clicked.connect(self.closed)
        row.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        self._layout.addLayout(row)
        self._layout.addSpacing(4)

    def row(self, key: str, value: str, color: str | None = None) -> None:
        if self._grid is None:
            self._grid = QGridLayout()
            self._grid.setHorizontalSpacing(12)
            self._grid.setVerticalSpacing(5)
            self._grid.setColumnStretch(1, 1)
            self._layout.addLayout(self._grid)
        line = self._grid.rowCount()
        self._grid.addWidget(label(key, "muted"), line, 0, Qt.AlignmentFlag.AlignTop)
        text = label(value, wrap=True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if color:
            text.setStyleSheet(f"color: {color};")
        self._grid.addWidget(text, line, 1)

    def section(self, title: str) -> None:
        self._grid = None
        self._layout.addSpacing(8)
        self._layout.addWidget(label(title.upper(), "overline"))

    def item(self, left: str, right: str = "", color: str | None = None, swatch_color: str | None = None) -> None:
        self._grid = None
        line = QHBoxLayout()
        line.setSpacing(8)
        if swatch_color:
            chip = label()
            chip.setFixedSize(10, 10)
            chip.setStyleSheet(f"background: {swatch_color}; border-radius: 3px;")
            line.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
        line.addWidget(label(left, wrap=True), 1)
        if right:
            value = label(right, "muted")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if color:
                value.setStyleSheet(f"color: {color};")
            line.addWidget(value)
        self._layout.addLayout(line)

    def note(self, text: str) -> None:
        self._grid = None
        self._layout.addWidget(label(text, "faint", wrap=True))

    def action(self, text: str, icon_name: str, x: int, z: int) -> None:
        self._grid = None
        go = button(text, icon_name, "ghost")
        go.clicked.connect(lambda: self.showRequested.emit(x, z))
        self._layout.addWidget(go, 0, Qt.AlignmentFlag.AlignLeft)

    def finish(self) -> None:
        self._layout.addStretch(1)
        self.verticalScrollBar().setValue(0)


def _empty(layout) -> None:
    """Retire tout le contenu tout de suite (deleteLater seul laisse l'ancienne fiche affichée
    jusqu'au prochain tour de la boucle d'événements)."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _empty(item.layout())
            item.layout().deleteLater()


class IntelPage(QWidget):
    refreshRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.world = World()
        self.panel_kind = ""

        self.search = SearchField("Pays ou joueur…")
        self.search.textChanged.connect(self._render_list)
        self.count = label("", "faint")
        self.table: QTableWidget = make_table(["Pays", "Chunks"], 0)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemClicked.connect(self._list_clicked)
        side = QWidget()
        side.setFixedWidth(250)
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(8)
        side_layout.addWidget(self.search)
        side_layout.addWidget(self.count)
        side_layout.addWidget(self.table, 1)

        self.map = MapView()
        self.map.countryClicked.connect(self._map_clicked)
        self.map.markerClicked.connect(self.show_marker)
        self.map.eventClicked.connect(self.show_event)
        self.layer_boxes: dict[str, QCheckBox] = {}
        layers = FlowWidget(spacing=14)
        for key, (text, default) in LAYERS.items():
            box = QCheckBox(text)
            box.setChecked(default)
            box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            box.toggled.connect(lambda checked, k=key: self.map.set_layer(k, checked))
            self.layer_boxes[key] = box
            layers.add(box)
        fit = icon_button("grid", "Tout voir")
        fit.clicked.connect(self.map.fit)
        world = icon_button("globe", "Infos monde : heure et météo du jeu, régions, biomes")
        world.clicked.connect(self.show_world)
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(layers, 1)
        bar.addWidget(fit, 0, Qt.AlignmentFlag.AlignTop)
        bar.addWidget(world, 0, Qt.AlignmentFlag.AlignTop)

        self.events_banner = Banner("warning")
        self.events_banner.hide()
        self.stale = label("", "faint")
        self.panel = InfoPanel()
        self.panel.closed.connect(self.close_panel)
        self.panel.showRequested.connect(lambda x, z: self.map.show_block(x, z))
        self.panel.hide()

        map_column = QVBoxLayout()
        map_column.setSpacing(10)
        map_column.addLayout(bar)
        map_column.addWidget(self.events_banner)
        map_frame = QFrame()
        map_frame.setStyleSheet(f"QFrame {{ border-radius: 12px; background: {COLORS.surface}; }}")
        frame_layout = QVBoxLayout(map_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.addWidget(self.map)
        map_column.addWidget(map_frame, 1)
        map_column.addWidget(self.stale)

        content = QWidget()
        body = QHBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)
        body.addWidget(side)
        body.addLayout(map_column, 1)
        body.addWidget(self.panel)

        self.empty = EmptyState(
            "map",
            "Carte pas encore disponible",
            "Le serveur du pays récupère la carte d'Iris (iris.nationsglory.fr) toutes les 30 minutes. "
            "Reviens dans un instant, ou demande à l'équipe de lancer une mise à jour (Administration › NationsGlory).",
        )
        self._stack = QStackedLayout()
        self._stack.addWidget(content)
        self._stack.addWidget(self.empty)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 20)
        layout.addLayout(self._stack)
        self._stack.setCurrentWidget(self.empty)

    # -- données -------------------------------------------------------------------------

    def set_world(self, world: World, offline: bool = False) -> None:
        self.world = world
        self.map.set_world(world)
        self._stack.setCurrentIndex(1 if world.empty else 0)
        self._render_list()
        self._show_events()
        stamp = world.fetched.get("territories") or world.fetched.get("frontiers")
        when = format_datetime(stamp) if stamp else "—"
        self.stale.setText(f"Carte d'Iris du {when}" + (" · hors ligne : dernières données gardées" if offline else ""))
        if self.panel.isVisible():
            self._refresh_panel()

    def _render_list(self) -> None:
        query = self.search.text()
        names = self.world.matches(query)
        rows = []
        for name in names:
            chunks = self.world.chunks_of(name)
            rows.append(
                [
                    text_cell(name, sort_key=name.lower(), icon=swatch(self.world.color_of(name)), key=name),
                    muted_cell(str(chunks) if chunks else "", chunks),
                ]
            )
        fill_rows(self.table, rows)
        total = len(self.world.names)
        self.count.setText(f"{len(names)} / {total} pays" if query.strip() else f"{total} pays")
        self._highlight_list()

    def _highlight_list(self) -> None:
        self.table.blockSignals(True)
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(KEY_ROLE) == self.map.selected and self.map.selected:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                break
        self.table.blockSignals(False)

    def _show_events(self) -> None:
        active = [e for e in self.world.events if e.active]
        if not active:
            self.events_banner.hide()
            return
        parts = [f"{e.title} ({e.x}, {e.z})" if e.x is not None and e.z is not None else e.title for e in active[:4]]
        more = f" et {len(active) - 4} autre(s)" if len(active) > 4 else ""
        self.events_banner.set_text("Événement en cours : " + " · ".join(parts) + more)
        self.events_banner.show()

    # -- sélection -----------------------------------------------------------------------

    def _list_clicked(self, item) -> None:
        name = self.table.item(item.row(), 0).data(KEY_ROLE)
        if name:
            self.select(name, fly=True)

    def _map_clicked(self, name: str) -> None:
        if name:
            self.select(name)
        else:
            self.close_panel()

    def select(self, name: str, fly: bool = False) -> None:
        self.map.select(name)
        if fly:
            self.map.fly_to(name)
        self.show_country(name)
        self._highlight_list()

    def find(self, query: str) -> bool:
        """Ouvre un pays (ou le pays d'un joueur) depuis l'extérieur (recherche globale, alerte)."""
        name = query if query in self.world.names else self.world.country_of_player(query)
        if not name:
            self.search.setText(query)
            return False
        self.select(name, fly=True)
        return True

    def close_panel(self) -> None:
        self.map.select("")
        self.panel.hide()
        self.panel_kind = ""
        self._highlight_list()

    def _refresh_panel(self) -> None:
        if self.panel_kind == "country" and self.map.selected:
            self.show_country(self.map.selected)
        elif self.panel_kind == "world":
            self.show_world()

    # -- fiches --------------------------------------------------------------------------

    def show_country(self, name: str) -> None:
        world = self.world
        faction, frontier = world.faction(name), world.frontier(name)
        atlas = world.countries.get(name)
        members = world.members.get(name)
        region = world.region_of(name)
        panel = self.panel
        panel.heading(name, world.color_of(name))
        if atlas and atlas.get("nameEn") and atlas.get("nameEn") != name:
            panel.row("Nom (EN)", str(atlas["nameEn"]))
        if faction and faction.kind:
            panel.row("Type", faction.kind)
        if faction:
            panel.row("Chunks claim", thousands(faction.chunks))
        if atlas and atlas.get("chunks") is not None:
            panel.row("Chunks (atlas)", thousands(atlas.get("chunks")))
        elif frontier:
            panel.row("Chunks (frontières)", thousands(frontier.chunks))
        if region:
            panel.row("Région", str(region.get("name") or "—"))
            panel.row("Pétrole (région)", f"{thousands(region.get('oilMax') or 0)}  {dots(region.get('oilDots'))}")
            panel.row("Gaz (région)", f"{thousands(region.get('gasMax') or 0)}  {dots(region.get('gasDots'))}")
        elif atlas:
            panel.row("Région", str(atlas.get("region") or "—"))
        if atlas and atlas.get("x") is not None:
            panel.row("Coordonnées (atlas)", f"{atlas.get('x')}, {atlas.get('z')}")
        for home in faction.homes if faction else []:
            panel.row(home.name, f"{home.x}, {home.z}")
        if (faction and faction.flag) or (atlas and atlas.get("flag")):
            panel.row("Drapeau", "oui")
        if faction and faction.id:
            panel.row("Identifiant", faction.id)
        if members is not None:
            incomplete = members.get("complete") is False or members.get("truncated")
            panel.row("Membres", f"{members.get('total', 0)}" + (" (liste incomplète)" if incomplete else ""))
        if faction and faction.homes:
            home = faction.homes[0]
            panel.action("Voir sur la carte", "map-pin", home.x, home.z)
        roster = [m for m in (members or {}).get("members", []) if isinstance(m, dict)]
        if roster:
            panel.section("Membres")
            counts = Counter(str(m.get("rank") or "?") for m in roster)
            panel.note(" · ".join(f"{rank} {count}" for rank, count in counts.items()))
            for member in roster:
                star = "★ " if member.get("leader") else ""
                rank_color = str(member.get("rankColor") or "")
                panel.item(
                    star + str(member.get("name") or "?"),
                    str(member.get("rank") or ""),
                    rank_color if rank_color.startswith("#") and len(rank_color) in (4, 7) else None,
                )
        elif members is None:
            panel.note("Pas de liste de membres pour ce pays.")
        panel.finish()
        panel.show()
        self.panel_kind = "country"

    def show_marker(self, marker: Marker) -> None:
        self.map.select("")
        self._highlight_list()
        biome = self.world.biomes.get(marker.biome, {"name": marker.biome})
        panel = self.panel
        panel.heading(str(biome.get("nameFr") or biome.get("name") or "Biome"), str(biome.get("color") or "#fbbf24"))
        panel.section("Ressources du biome")
        solar = biome.get("solar")
        panel.row(
            "Ensoleillement",
            f"× {str(solar).replace('.', ',')}  {dots(biome.get('solarDots'))}" if solar is not None else "—",
        )
        region = self.world.atlas_regions.get(marker.region.lower()) if marker.region else None
        if region:
            panel.section(f"Ressources de {region.get('name') or marker.region}")
            panel.row("Pétrole", f"{thousands(region.get('oilMax') or 0)}  {dots(region.get('oilDots'))}")
            panel.row("Gaz", f"{thousands(region.get('gasMax') or 0)}  {dots(region.get('gasDots'))}")
        else:
            panel.note("Pas de région associée (zone maritime).")
        panel.row("Position", f"{round(marker.x)}, {round(marker.z)}")
        panel.finish()
        panel.show()
        self.panel_kind = "marker"

    def show_event(self, event: Event) -> None:
        self.map.select("")
        self._highlight_list()
        panel = self.panel
        panel.heading(event.title, EVENT_COLORS[event.kind], EVENT_ICONS[event.kind])
        panel.row("Type", EVENT_NAMES[event.kind])
        panel.row("État", "en cours" if event.active else "terminé")
        if event.x is not None and event.z is not None:
            panel.row("Position", f"x {event.x} · z {event.z}")
            panel.row("Chunk", f"{event.x // CHUNK}, {event.z // CHUNK}")
            owner = self.map.pick_country(self.map.to_screen(event.x / CHUNK, event.z / CHUNK))
            if owner:
                panel.row("Sur le territoire de", owner)
            panel.action("Centrer la carte", "map-pin", event.x, event.z)
        panel.finish()
        panel.show()
        self.panel_kind = "event"

    def show_world(self) -> None:
        self.map.select("")
        self._highlight_list()
        world = self.world
        atlas = world.atlas
        panel = self.panel
        panel.heading(str(atlas.get("title") or "Monde"), icon_name="globe")
        worlds = world.state.get("worlds") if isinstance(world.state, dict) else None
        first = worlds[0] if isinstance(worlds, list) and worlds and isinstance(worlds[0], dict) else {}
        if world.game_time():
            panel.row("Heure du jeu", world.game_time())
        if first.get("time") is not None:
            panel.row("Temps de jeu (ticks)", thousands(first.get("time")))
        config = world.state.get("config") if isinstance(world.state.get("config"), dict) else {}
        if config.get("maxPlayers") is not None:
            panel.row("Joueurs max", str(config["maxPlayers"]))
        if config.get("playersVisible") is False:
            panel.row("Joueurs connectés", "masqués par le site")
        total = sum(int(m.get("total") or 0) for m in world.members.values())
        panel.row("Pays (territoires)", str(len(world.factions)))
        panel.row("Pays (frontières)", str(len(world.frontiers)))
        panel.row("Pays avec membres", str(len(world.members)))
        panel.row("Membres au total", thousands(total))
        panel.row("Marqueurs de biome", str(len(world.markers)))
        panel.row("Régions", str(len(world.atlas_regions)))
        source = atlas.get("source") if isinstance(atlas.get("source"), dict) else {}
        if source.get("exportedAt"):
            panel.row("Atlas exporté le", str(source["exportedAt"])[:10])
        if source.get("regionsUpdatedAt"):
            panel.row("Régions mises à jour", str(source["regionsUpdatedAt"]))
        if atlas.get("version"):
            panel.row("Version de l'atlas", str(atlas["version"]))
        panel.section("Météo / événements")
        active = [e for e in world.events if e.active]
        for event in active:
            where = f"{event.x}, {event.z}" if event.x is not None else ""
            panel.item(event.title, where, swatch_color=EVENT_COLORS[event.kind])
        if not active:
            panel.note("Aucun événement en cours." if not world.weather_raw else f"{len(world.weather_raw)} en cours.")
        panel.section("Régions")
        for region in world.atlas_regions.values():
            panel.item(
                str(region.get("name") or region.get("slug")),
                f"{region.get('countries') or 0} pays · pétrole {thousands(region.get('oilMax') or 0)}"
                f" · gaz {thousands(region.get('gasMax') or 0)}",
            )
        panel.section("Biomes (ensoleillement)")
        for biome in world.biomes.values():
            solar = str(biome.get("solar")).replace(".", ",") if biome.get("solar") is not None else "—"
            panel.item(
                str(biome.get("nameFr") or biome.get("name")),
                f"× {solar}  {dots(biome.get('solarDots'))}",
                swatch_color=str(biome.get("color") or "#888888"),
            )
        panel.section("Données récupérées")
        for kind, title in KIND_LABELS.items():
            stamp = world.fetched.get(kind)
            panel.item(title, format_datetime(stamp) if stamp else "pas encore")
        panel.finish()
        panel.show()
        self.panel_kind = "world"

    def refresh_live(self) -> None:
        """Heure, météo et événements mis à jour sans toucher au reste de la carte."""
        self.map.set_world(self.world)
        self._show_events()
        if self.panel_kind == "world":
            self.show_world()
