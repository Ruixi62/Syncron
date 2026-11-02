"""Page Images : galerie du pays, envoi (bouton, glisser-déposer, Ctrl+V) et lien à copier."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QGuiApplication, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from syncron_client.tools.images.model import IMAGE_FILTER, IMAGE_SUFFIXES, HostedImage, matches
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import (
    Chip,
    ElidedLabel,
    EmptyState,
    FlowWidget,
    SearchField,
    SegmentedControl,
    button,
    icon_button,
    label,
    plain_tooltip,
)

CARD_WIDTH = 220
THUMB_HEIGHT = 150


class ImageCard(QFrame):
    """Vignette, titre, détails, et les actions : copier le lien, ouvrir, renommer, supprimer."""

    actionRequested = Signal(str, str)  # action, id de l'image

    def __init__(self, image: HostedImage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image = image
        self.setObjectName("ImageCard")
        self.setFixedWidth(CARD_WIDTH)
        self.setStyleSheet(
            f"QFrame#ImageCard {{ background: {COLORS.surface}; border-radius: 14px; }}"
            f"QLabel#Thumb {{ background: {COLORS.surface_alt}; border-radius: 10px; }}"
        )
        self.thumb = QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(CARD_WIDTH - 16, THUMB_HEIGHT)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setPixmap(icons.pixmap("image", COLORS.text_faint, 28))
        self.thumb.setToolTip(plain_tooltip(image.title))
        self.title = ElidedLabel(image.title, "heading")
        self.title.setToolTip(plain_tooltip(image.title))
        self.details = ElidedLabel(image.details(), "faint")
        self.details.setToolTip(plain_tooltip(image.details()))

        self.copy_button = button("Copier", "copy", "primary")
        self.copy_button.setToolTip("Copier le lien public de l'image (à coller sur Discord…)")
        self.copy_button.clicked.connect(lambda: self.actionRequested.emit("copy", image.id))
        actions = QHBoxLayout()
        actions.setSpacing(2)
        actions.addWidget(self.copy_button, 1)
        open_button = icon_button("external", "Ouvrir dans le navigateur", 16)
        open_button.clicked.connect(lambda: self.actionRequested.emit("open", image.id))
        actions.addWidget(open_button)
        self.rename_button = self.delete_button = None
        if image.can_delete:
            self.rename_button = icon_button("edit", "Renommer", 16)
            self.rename_button.clicked.connect(lambda: self.actionRequested.emit("rename", image.id))
            self.delete_button = icon_button("trash", "Supprimer l'image (le lien ne marchera plus)", 16)
            self.delete_button.clicked.connect(lambda: self.actionRequested.emit("delete", image.id))
            actions.addWidget(self.rename_button)
            actions.addWidget(self.delete_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 10)
        layout.setSpacing(6)
        layout.addWidget(self.thumb)
        texts = QVBoxLayout()
        texts.setContentsMargins(4, 2, 4, 0)
        texts.setSpacing(1)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(self.title, 1)
        if image.animated:
            title_row.addWidget(Chip("GIF", "violet"))
        texts.addLayout(title_row)
        texts.addWidget(self.details)
        layout.addLayout(texts)
        layout.addLayout(actions)

    def set_thumbnail(self, path: Path) -> None:
        source = QPixmap(str(path))
        if source.isNull():
            return
        ratio = self.devicePixelRatioF() or 1.0
        target = QSize(round((CARD_WIDTH - 24) * ratio), round((THUMB_HEIGHT - 8) * ratio))
        upscale = source.width() < target.width() and source.height() < target.height()
        mode = Qt.TransformationMode.FastTransformation if upscale else Qt.TransformationMode.SmoothTransformation
        scaled = source.scaled(target, Qt.AspectRatioMode.KeepAspectRatio, mode)
        scaled.setDevicePixelRatio(ratio)
        self.thumb.setPixmap(scaled)


class ImagesPage(QWidget):
    filesDropped = Signal(list)  # list[Path]
    dataPasted = Signal(str, bytes)  # nom, contenu PNG
    actionRequested = Signal(str, str)  # action, id
    filterChanged = Signal(bool)  # True : seulement les miennes

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._images: list[HostedImage] = []
        self._cards: dict[str, ImageCard] = {}
        self._thumbnails: dict[str, Path] = {}
        self._online = True
        self._unavailable: str | None = None

        self.scope = SegmentedControl([("Toutes", None), ("Les miennes", None)])
        self.scope.currentChanged.connect(lambda index: self.filterChanged.emit(index == 1))
        self.search = SearchField("Rechercher une image…")
        self.search.setMaximumWidth(280)
        self.search.textChanged.connect(self._render)
        self.quota = label("", "faint")
        self.upload_button = button("Envoyer une image", "upload", "primary")
        self.upload_button.clicked.connect(self.choose_files)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(self.scope)
        toolbar.addWidget(self.search, 1)
        toolbar.addStretch(0)
        toolbar.addWidget(self.quota)
        toolbar.addWidget(self.upload_button)
        self.hint = label(
            "Glisse des images ici ou colle-les avec Ctrl+V. Le lien est copié dès l'envoi : colle-le sur Discord. "
            "Toute personne qui a le lien peut voir l'image.",
            "faint",
            wrap=True,
        )

        self.grid = FlowWidget(spacing=14)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.addWidget(self.grid)
        content_layout.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(content)
        self.empty = EmptyState("image", "Aucune image", "Envoie une image pour obtenir un lien à partager.")
        self.empty.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(12)
        layout.addLayout(toolbar)
        layout.addWidget(self.hint)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(self.empty, 1)

        paste = QShortcut(QKeySequence.StandardKey.Paste, self)
        paste.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        paste.activated.connect(self.paste)

    # -- état -------------------------------------------------------------------------------

    @property
    def images(self) -> list[HostedImage]:
        return self._images

    @property
    def cards(self) -> dict[str, ImageCard]:
        return self._cards

    @property
    def mine_only(self) -> bool:
        return self.scope.current_index() == 1

    def set_online(self, online: bool) -> None:
        self._online = online
        self._unavailable = None
        self.upload_button.setEnabled(online)
        self._render()

    def set_unavailable(self, server_version: str) -> None:
        """Serveur trop ancien : pas de route d'envoi. On le dit au lieu d'afficher « Not Found »."""
        version = f" (version {server_version})" if server_version else ""
        self._unavailable = (
            f"Le serveur du pays{version} n'a pas encore l'hébergement d'images. "
            "Préviens l'équipe : il faut mettre le serveur à jour (git pull puis docker compose up -d --build)."
        )
        self._images = []
        self.upload_button.setEnabled(False)
        self.quota.clear()
        self._render()

    def set_images(self, images: list[HostedImage], mine_count: int, limit: int) -> None:
        self._images = images
        self.quota.setText(f"{mine_count} / {limit} images" if limit else f"{mine_count} image(s)")
        self.quota.setToolTip("Images que tu as envoyées, sur le maximum autorisé par membre")
        self._render()

    def set_thumbnail(self, image_id: str, path: Path) -> None:
        self._thumbnails[image_id] = path
        card = self._cards.get(image_id)
        if card is not None:
            card.set_thumbnail(path)

    # -- envoi ------------------------------------------------------------------------------

    def choose_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, "Envoyer des images", "", IMAGE_FILTER)
        if names:
            self.filesDropped.emit([Path(name) for name in names])

    def paste(self) -> None:
        self.receive(QGuiApplication.clipboard().mimeData())

    def receive(self, mime: QMimeData | None) -> bool:
        """Fichiers images, ou image copiée (capture d'écran) : transmis pour envoi."""
        if mime is None or not self._online or self._unavailable:
            return False
        files = [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]
        files = [path for path in files if path.suffix.lower() in IMAGE_SUFFIXES]
        if files:
            self.filesDropped.emit(files)
            return True
        if mime.hasImage():
            image = mime.imageData()
            if isinstance(image, QImage) and not image.isNull():
                data = QByteArray()
                buffer = QBuffer(data)
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                image.save(buffer, "PNG")
                self.dataPasted.emit("capture.png", bytes(data))
                return True
        return False

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        has_files = any(Path(u.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES for u in mime.urls())
        if self._online and not self._unavailable and (has_files or mime.hasImage()):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        if self.receive(event.mimeData()):
            event.acceptProposedAction()

    # -- rendu ------------------------------------------------------------------------------

    def _render(self) -> None:
        self.grid.clear()
        self._cards = {}
        query = self.search.text().strip()
        shown = [image for image in self._images if not query or matches(image, query)]
        for image in shown:
            card = ImageCard(image)
            card.actionRequested.connect(self.actionRequested)
            if image.id in self._thumbnails:
                card.set_thumbnail(self._thumbnails[image.id])
            self._cards[image.id] = card
            self.grid.add(card)
        self.scroll.setVisible(bool(shown))
        self.empty.setVisible(not shown)
        if self._unavailable:
            self.empty.body_label.setText(self._unavailable)
        elif not self._online:
            self.empty.body_label.setText("Hors ligne : la galerie revient dès la reconnexion.")
        elif query and self._images:
            self.empty.body_label.setText("Aucune image ne correspond à cette recherche.")
        elif self.mine_only:
            self.empty.body_label.setText("Tu n'as encore envoyé aucune image.")
        else:
            self.empty.body_label.setText("Envoie une image pour obtenir un lien à partager.")
