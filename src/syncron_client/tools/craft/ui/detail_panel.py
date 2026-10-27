"""Fiche d'analyse d'un objet : en-tête, chiffres clés, prérequis, vues détaillées."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from syncron_client.ui.item_icons import IconProvider
from syncron_client.ui.tables import KEY_ROLE, fill_rows, make_table, muted_cell, quantity_cell, text_cell
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import (
    Banner,
    Card,
    Chip,
    EmptyState,
    FlowWidget,
    QuantityStepper,
    SegmentedControl,
    StatTile,
    button,
    label,
)
from syncron_core.calculator import CraftCalculator
from syncron_core.catalog_service import CatalogService
from syncron_core.duration import format_duration
from syncron_core.errors import AppError
from syncron_core.models.craft_plan import CraftNode, CraftPlan
from syncron_core.models.item import Item
from syncron_core.models.reference import SkillKind
from syncron_core.text import format_quantity, normalize

HEADER_ICON = 64
VIEWS_MIN_HEIGHT = 320
STATS_ONE_ROW_MIN_WIDTH = 860
COMPACT_VIEWS_WIDTH = 820
COPY_LABEL = "Copier la liste"
ROW_ICON = 24
TREE_AUTO_EXPAND_LIMIT = 400
SKILL_TONES = {
    SkillKind.JOB: ("accent", "user"),
    SkillKind.RESEARCH: ("info", "flask"),
    SkillKind.OTHER: ("violet", "award"),
}
VIEWS = (
    ("Ressources", "gem"),
    ("Étapes", "list"),
    ("Ateliers", "station"),
    ("Arbre", "tree"),
    ("Recette", "recipe"),
    ("Utilisé dans", "link"),
)


class DetailPanel(QWidget):
    planChanged = Signal(object)  # CraftPlan | None
    navigateRequested = Signal(str)

    def __init__(self, catalog: CatalogService, calculator: CraftCalculator, icon_provider: IconProvider, parent=None):
        super().__init__(parent)
        self._catalog = catalog
        self._calculator = calculator
        self._icons = icon_provider
        self._item_id: str | None = None
        self._plan: CraftPlan | None = None

        self._stack = QStackedWidget()
        self._stack.addWidget(
            EmptyState(
                "hammer",
                "Choisis un objet à fabriquer",
                "Sélectionne un objet dans le catalogue, ou tape « Machine X x10 » puis Entrée.",
            )
        )
        self._stack.addWidget(self._build_content())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

    # -- API -------------------------------------------------------------------

    @property
    def plan(self) -> CraftPlan | None:
        return self._plan

    @property
    def item_id(self) -> str | None:
        return self._item_id

    def quantity(self) -> int:
        return self._stepper.value()

    def show_item(self, item_id: str, quantity: int = 1) -> None:
        item = self._catalog.get(item_id)
        if item is None:
            self.clear()
            return
        self._item_id = item_id
        self._fill_header(item)
        self._stepper.set_value(quantity, emit=False)
        self._fill_used_in(item)
        self._stack.setCurrentIndex(1)
        self._recalculate()

    def set_quantity(self, quantity: int) -> None:
        self._stepper.set_value(quantity)

    def refresh(self) -> None:
        if self._item_id and self._catalog.get(self._item_id):
            self.show_item(self._item_id, self._stepper.value())
        else:
            self.clear()

    def clear(self) -> None:
        self._item_id = None
        self._set_plan(None)
        self._stack.setCurrentIndex(0)

    def focus_quantity(self) -> None:
        if self._item_id:
            self._stepper.focus_input()

    def raw_materials_text(self) -> str | None:
        if not self._plan:
            return None
        name = self._catalog.display_name
        lines = [f"{name(self._plan.target_id)} × {format_quantity(self._plan.quantity)}"]
        lines += [f"{format_quantity(r.missing)} × {name(r.item_id)}" for r in self._plan.raw_materials]
        return "\n".join(lines)

    def copy_raw_materials(self) -> bool:
        text = self.raw_materials_text()
        if text:
            QGuiApplication.clipboard().setText(text)
        return bool(text)

    # -- construction ----------------------------------------------------------

    def _build_content(self) -> QWidget:
        """Le contenu défile verticalement quand la fenêtre est trop basse :
        aucun bloc n'est jamais écrasé sous sa taille minimale."""
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(12)
        layout.addWidget(self._build_header())
        self._error = Banner("danger")
        self._error.hide()
        layout.addWidget(self._error)
        layout.addLayout(self._build_stats())
        self._requirements_card = Card(flat=True, padding=14, spacing=8)
        self._requirements_card.body.addWidget(label("PRÉREQUIS POUR TOUT LE PLAN", "overline"))
        self._requirements_flow = FlowWidget(spacing=6)
        self._requirements_card.body.addWidget(self._requirements_flow)
        layout.addWidget(self._requirements_card)
        views = self._build_views()
        views.setMinimumHeight(VIEWS_MIN_HEIGHT)
        layout.addWidget(views, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    def _build_header(self) -> Card:
        card = Card(padding=18, spacing=0)
        self._header_card = card
        tile = QFrame()
        tile.setObjectName("IconTile")
        tile.setFixedSize(HEADER_ICON + 20, HEADER_ICON + 20)
        self._image = QLabel(tile)
        self._image.setGeometry(10, 10, HEADER_ICON, HEADER_ICON)
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._title = label("", "title")
        self._title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._title.setWordWrap(True)
        self._identifier = label("", "faint")
        self._identifier.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._chips = FlowWidget(spacing=6)
        self._description = label("", "muted", wrap=True)

        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(self._title)
        texts.addWidget(self._identifier)
        texts.addSpacing(6)
        texts.addWidget(self._chips)
        texts.addSpacing(2)
        texts.addWidget(self._description)

        self._stepper = QuantityStepper()
        self._stepper.valueChanged.connect(self._recalculate)
        quantity = QVBoxLayout()
        quantity.setSpacing(6)
        quantity.addWidget(label("QUANTITÉ", "overline"), 0, Qt.AlignmentFlag.AlignRight)
        quantity.addWidget(self._stepper)
        quantity.addStretch(1)

        row = QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(tile, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(texts, 1)
        row.addLayout(quantity)
        card.body.addLayout(row)
        return card

    def _build_stats(self) -> QGridLayout:
        self._stat_raw = StatTile("gem", "Ressources primaires", "accent")
        self._stat_crafts = StatTile("hammer", "Crafts à réaliser", "success")
        self._stat_time = StatTile("clock", "Temps de fabrication", "info")
        self._stat_stations = StatTile("station", "Ateliers", "violet")
        self._stats_grid = QGridLayout()
        self._stats_grid.setSpacing(12)
        self._stats_columns = 0
        self._arrange_stats(4)
        return self._stats_grid

    def _arrange_stats(self, columns: int) -> None:
        """4 indicateurs sur une ligne, ou 2×2 quand la fiche est étroite."""
        if columns == self._stats_columns:
            return
        tiles = (self._stat_raw, self._stat_crafts, self._stat_time, self._stat_stations)
        for tile in tiles:
            self._stats_grid.removeWidget(tile)
        for index, tile in enumerate(tiles):
            self._stats_grid.addWidget(tile, index // columns, index % columns)
        for column in range(4):
            self._stats_grid.setColumnStretch(column, 1 if column < columns else 0)
        self._stats_columns = columns

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._arrange_stats(4 if self.width() >= STATS_ONE_ROW_MIN_WIDTH else 2)
        compact = self.width() < COMPACT_VIEWS_WIDTH
        self._segments.set_compact(compact)
        self._copy_button.setText("" if compact else COPY_LABEL)
        self._copy_button.setToolTip(COPY_LABEL if compact else "")

    def _build_views(self) -> Card:
        card = Card(padding=14, spacing=10)
        self._views_card = card
        self._segments = SegmentedControl(VIEWS)
        self._copy_button = button(COPY_LABEL, "copy", "ghost")
        self._copy_button.clicked.connect(self.copy_raw_materials)
        bar = QHBoxLayout()
        bar.addWidget(self._segments)
        bar.addStretch(1)
        bar.addWidget(self._copy_button)
        card.body.addLayout(bar)

        self._raw_table = make_table(["Ressource", "Quantité"], sortable=True)
        self._steps_table = make_table(["#", "Objet", "Atelier", "Crafts", "Produit", "Surplus", "Temps"], 1, True)
        self._stations_table = make_table(["Atelier", "Crafts", "Temps", "Objets fabriqués"], 3)
        self._tree = self._make_tree()
        self._direct_info = label("", "muted")
        self._direct_table = make_table(["Ingrédient", "Quantité"])
        self._used_table = make_table(["Objet", "Quantité par craft", "Atelier"])
        self._raw_total = label("", "muted")

        raw_page = _page(self._raw_table, footer=self._raw_total)
        direct_page = _page(self._direct_table, header=self._direct_info)
        tree_hint = label("Vue par branche. Les totaux exacts (besoins fusionnés) sont dans « Ressources ».", "faint")
        self._views = QStackedWidget()
        for page in (
            raw_page,
            _page(
                self._steps_table,
                header=label("Ordre conseillé : chaque étape n'utilise que les précédentes.", "faint"),
            ),
            _page(self._stations_table),
            _page(self._tree, header=tree_hint),
            direct_page,
            _page(self._used_table),
        ):
            self._views.addWidget(page)
        card.body.addWidget(self._views, 1)

        self._segments.currentChanged.connect(self._on_view_changed)
        for table in (self._raw_table, self._steps_table, self._direct_table, self._used_table):
            table.itemDoubleClicked.connect(self._on_table_double_clicked)
        self._tree.itemDoubleClicked.connect(self._on_tree_double_clicked)
        return card

    @staticmethod
    def _make_tree() -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(["OBJET", "QUANTITÉ", "CRAFTS", "ATELIER"])
        tree.setUniformRowHeights(True)
        tree.setIconSize(QSize(ROW_ICON, ROW_ICON))
        tree.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tree.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        tree.setIndentation(22)
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        return tree

    # -- calcul ----------------------------------------------------------------

    def _recalculate(self) -> None:
        if not self._item_id:
            return
        try:
            plan = self._calculator.calculate(self._item_id, self._stepper.value())
        except AppError as exc:
            self._error.set_text(f"Calcul impossible : {exc}\nCorrige items.json : l'outil recharge automatiquement.")
            self._error.show()
            self._set_plan(None)
            return
        self._error.hide()
        self._set_plan(plan)

    def _set_plan(self, plan: CraftPlan | None) -> None:
        self._plan = plan
        if plan is None:
            for table in (self._raw_table, self._steps_table, self._stations_table, self._direct_table):
                fill_rows(table, [])
            self._tree.clear()
            for tile in (self._stat_raw, self._stat_crafts, self._stat_time, self._stat_stations):
                tile.set_value("—")
            self._requirements_card.hide()
        else:
            self._fill_stats(plan)
            self._fill_requirements(plan)
            self._fill_raw(plan)
            self._fill_steps(plan)
            self._fill_stations(plan)
            self._fill_tree(plan)
            self._fill_direct(plan)
        self._copy_button.setEnabled(plan is not None)
        self.planChanged.emit(plan)

    # -- remplissage -------------------------------------------------------------

    def _fill_header(self, item: Item) -> None:
        self._image.setPixmap(self._icons.item_pixmap(item.id, HEADER_ICON))
        self._title.setText(item.name)
        self._identifier.setText(item.id)
        self._description.setText(item.description)
        self._description.setVisible(bool(item.description))
        self._chips.clear()
        recipe = item.recipe
        if recipe is None:
            self._chips.add(Chip("Ressource primaire", "neutral", "gem"))
        else:
            self._chips.add(Chip(self._catalog.station_name(recipe.station_id), "info", "station"))
            self._chips.add(Chip(format_duration(recipe.time_seconds), "accent", "clock"))
            if recipe.output > 1:
                self._chips.add(Chip(f"{recipe.output} par craft", "success", "layers"))
            for requirement in recipe.requirements:
                skill = self._catalog.skill(requirement.skill_id)
                tone, icon_name = SKILL_TONES[skill.kind] if skill else ("violet", "award")
                name = self._catalog.skill_name(requirement.skill_id)
                self._chips.add(Chip(f"{name} · niv. {requirement.level}", tone, icon_name))
        if item.category:
            self._chips.add(Chip(item.category, "neutral", "layers"))

    def _fill_stats(self, plan: CraftPlan) -> None:
        self._stat_raw.set_value(format_quantity(plan.total_missing_units), f"{len(plan.raw_materials)} type(s)")
        self._stat_crafts.set_value(format_quantity(plan.total_crafts), f"{len(plan.steps)} étape(s)")
        self._stat_time.set_value(format_duration(plan.total_time, compact=True), "Temps machine")
        busiest = self._catalog.station_name(plan.workloads[0].station_id) if plan.workloads else ""
        self._stat_stations.set_value(str(len(plan.workloads)), f"Le plus chargé : {busiest}" if busiest else "")

    def _fill_requirements(self, plan: CraftPlan) -> None:
        self._requirements_flow.clear()
        for summary in plan.requirements:
            skill = self._catalog.skill(summary.skill_id)
            tone, icon_name = SKILL_TONES[skill.kind] if skill else ("violet", "award")
            chip = Chip(f"{self._catalog.skill_name(summary.skill_id)} · niv. {summary.level}", tone, icon_name)
            users = ", ".join(self._catalog.display_name(i) for i in summary.needed_by)
            kind = f"{skill.kind.label}\n" if skill else ""
            chip.setToolTip(f"{kind}Requis pour : {users}")
            self._requirements_flow.add(chip)
        self._requirements_card.setVisible(bool(plan.requirements))

    def _item_cell(self, item_id: str):
        name = self._catalog.display_name(item_id)
        return text_cell(name, normalize(name), self._icons.item_icon(item_id, ROW_ICON), item_id)

    def _station_cell(self, station_id: str | None):
        name = self._catalog.station_name(station_id)
        cell = text_cell(name, normalize(name), self._icons.station_icon(station_id, 18))
        if not station_id:
            cell.setForeground(QColor(COLORS.text_faint))
        return cell

    def _fill_raw(self, plan: CraftPlan) -> None:
        self._raw_table.sortByColumn(1, Qt.SortOrder.DescendingOrder)
        fill_rows(
            self._raw_table,
            [[self._item_cell(r.item_id), quantity_cell(r.missing, strong=True)] for r in plan.raw_materials],
        )
        self._raw_total.setText(
            f"Total : {format_quantity(plan.total_missing_units)} unité(s) · {len(plan.raw_materials)} ressource(s)"
        )

    def _fill_steps(self, plan: CraftPlan) -> None:
        rows = []
        for index, step in enumerate(plan.steps, start=1):
            rows.append(
                [
                    muted_cell(str(index), index),
                    self._item_cell(step.item_id),
                    self._station_cell(step.station_id),
                    quantity_cell(step.crafts, strong=True),
                    quantity_cell(step.produced),
                    quantity_cell(step.surplus, tone=COLORS.text_faint if not step.surplus else COLORS.warning),
                    muted_cell(format_duration(step.total_time, compact=True), step.total_time),
                ]
            )
        self._steps_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        fill_rows(self._steps_table, rows)

    def _fill_stations(self, plan: CraftPlan) -> None:
        rows = []
        for workload in plan.workloads:
            objects = ", ".join(self._catalog.display_name(i) for i in workload.item_ids)
            rows.append(
                [
                    self._station_cell(workload.station_id),
                    quantity_cell(workload.crafts, strong=True),
                    muted_cell(format_duration(workload.total_time, compact=True), workload.total_time),
                    muted_cell(objects),
                ]
            )
        fill_rows(self._stations_table, rows)

    def _fill_tree(self, plan: CraftPlan) -> None:
        self._tree.setUpdatesEnabled(False)
        self._tree.clear()
        self._tree.addTopLevelItem(self._tree_item(plan.tree))
        if plan.tree.count_nodes() <= TREE_AUTO_EXPAND_LIMIT:
            self._tree.expandAll()
        else:
            self._tree.expandToDepth(1)
        self._tree.setUpdatesEnabled(True)

    def _tree_item(self, node: CraftNode) -> QTreeWidgetItem:
        item = self._catalog.get(node.item_id)
        station = self._catalog.station_name(item.station_id) if item and item.recipe else ""
        entry = QTreeWidgetItem(
            [
                self._catalog.display_name(node.item_id),
                format_quantity(node.quantity),
                format_quantity(node.crafts) if node.crafts else "",
                station,
            ]
        )
        entry.setIcon(0, self._icons.item_icon(node.item_id, ROW_ICON))
        entry.setData(0, KEY_ROLE, node.item_id)
        for column in (1, 2):
            entry.setTextAlignment(column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        entry.setForeground(3, QColor(COLORS.text_faint))
        if node.is_leaf:
            entry.setForeground(1, QColor(COLORS.accent))
        for child in node.children:
            entry.addChild(self._tree_item(child))
        return entry

    def _fill_direct(self, plan: CraftPlan) -> None:
        target = self._catalog.get(plan.target_id)
        if not plan.direct_recipe:
            self._direct_info.setText("Ressource primaire : elle ne se fabrique pas.")
        elif target and target.recipe and target.recipe.output > 1:
            produced = plan.target_crafts * target.recipe.output
            self._direct_info.setText(
                f"{format_quantity(plan.target_crafts)} craft(s) × {target.recipe.output} = "
                f"{format_quantity(produced)} produit(s) pour {format_quantity(plan.quantity)} demandé(s)."
            )
        else:
            self._direct_info.setText(f"{format_quantity(plan.target_crafts)} craft(s).")
        fill_rows(
            self._direct_table,
            [[self._item_cell(line.item_id), quantity_cell(line.quantity, strong=True)] for line in plan.direct_recipe],
        )

    def _fill_used_in(self, item: Item) -> None:
        rows = []
        for consumer in self._catalog.used_in(item.id):
            per_craft = next(i.quantity for i in consumer.recipe.ingredients if i.item_id == item.id)
            rows.append(
                [self._item_cell(consumer.id), quantity_cell(per_craft), self._station_cell(consumer.station_id)]
            )
        fill_rows(self._used_table, rows)
        self._segments.set_text(5, f"Utilisé dans ({len(rows)})")

    # -- navigation ------------------------------------------------------------

    def _on_view_changed(self, index: int) -> None:
        self._views.setCurrentIndex(index)
        self._copy_button.setVisible(index == 0)

    def _on_table_double_clicked(self, cell) -> None:
        table: QTableWidget = cell.tableWidget()
        for column in range(table.columnCount()):
            item_id = table.item(cell.row(), column).data(KEY_ROLE)
            if item_id:
                self.navigateRequested.emit(item_id)
                return

    def _on_tree_double_clicked(self, entry: QTreeWidgetItem, _column: int) -> None:
        item_id = entry.data(0, KEY_ROLE)
        if item_id and item_id != self._item_id:
            self.navigateRequested.emit(item_id)


def _page(body: QWidget, header: QWidget | None = None, footer: QWidget | None = None) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 4, 0, 0)
    layout.setSpacing(8)
    if header is not None:
        layout.addWidget(header)
    layout.addWidget(body, 1)
    if footer is not None:
        layout.addWidget(footer)
    return page
