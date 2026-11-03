"""Outil Images : héberger une image sur le serveur du pays et partager son lien.

Tout membre envoie des images (bouton, glisser-déposer, Ctrl+V d'une capture) ; le lien
public est copié dès l'envoi. Chacun renomme et supprime les siennes ; l'équipe qui gère
le système « images » peut supprimer n'importe laquelle. Vignettes gardées en cache.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QInputDialog, QWidget

from syncron_client.api.errors import ApiError
from syncron_client.platform.admin import call_api
from syncron_client.platform.tool import NotifyLevel, Tool, ToolHost, ToolInfo
from syncron_client.tools.images.model import HostedImage, format_size
from syncron_client.tools.images.page import ImagesPage
from syncron_client.ui import icons
from syncron_client.ui.theme import COLORS
from syncron_client.ui.widgets import ask

THUMB_DIR = "hosted"


class ImagesTool(Tool):
    _INFO = ToolInfo(
        id="images",
        name="Images",
        description="Héberge tes images sur le serveur du pays et partage leur lien, sur Discord ou ailleurs.",
        icon="image",
        version="5.3.0",
        system="images",
    )

    def __init__(self) -> None:
        self._host: ToolHost | None = None
        self._page: ImagesPage | None = None
        self._images: list[HostedImage] = []
        self._max_bytes = 8 * 1024 * 1024
        self._actions: list[QAction] = []
        self.last_link: str | None = None

    @property
    def info(self) -> ToolInfo:
        return self._INFO

    @property
    def page(self) -> ImagesPage | None:
        return self._page

    @property
    def images(self) -> list[HostedImage]:
        return self._images

    def setup(self, host: ToolHost) -> None:
        self._host = host
        self._thumbs = host.app_paths.cache_dir / THUMB_DIR

    def create_page(self) -> QWidget:
        self._page = ImagesPage()
        self._page.filesDropped.connect(self.upload_files)
        self._page.dataPasted.connect(self.upload_data)
        self._page.actionRequested.connect(self._on_action)
        self._page.filterChanged.connect(lambda _mine: self.refresh())
        refresh = QAction(icons.icon("refresh", COLORS.text_muted, 16), "Actualiser", self._page)
        refresh.setToolTip("Recharger la galerie")
        refresh.triggered.connect(self.refresh)
        self._actions = [refresh]
        return self._page

    def activated(self) -> None:
        self.refresh()

    def page_actions(self) -> Sequence[QAction]:
        return self._actions

    # -- galerie ----------------------------------------------------------------------------

    def refresh(self) -> None:
        online = self._host.session.online
        if self._page is not None:
            self._page.set_online(online)
        if not online:
            return
        mine = self._page.mine_only if self._page is not None else False

        def done(document: dict[str, Any]) -> None:
            self._images = [HostedImage.from_api(raw) for raw in document.get("images", [])]
            self._max_bytes = int(document.get("max_bytes") or self._max_bytes)
            if self._page is not None:
                self._page.set_images(self._images, int(document["mine_count"]), int(document["per_user_limit"]))
            self._load_thumbnails()

        self._host.runner.run(
            lambda: self._host.api.images(mine), done, lambda error: self._host.handle_error(error, "Images")
        )

    def _thumb_path(self, image: HostedImage) -> Path:
        name = hashlib.sha256(image.url.encode("utf-8")).hexdigest()[:24]
        return self._thumbs / f"{name}{Path(image.url).suffix}"

    def _load_thumbnails(self) -> None:
        cached = [(image, self._thumb_path(image)) for image in self._images]
        for image, path in cached:
            if path.is_file() and self._page is not None:
                self._page.set_thumbnail(image.id, path)
        missing = [(image, path) for image, path in cached if not path.is_file()]
        if not missing:
            return

        def download() -> list[tuple[str, Path]]:
            fetched = []
            for image, path in missing:
                try:
                    content = self._host.api.download(image.url)
                except ApiError:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                fetched.append((image.id, path))
            return fetched

        def done(fetched: list[tuple[str, Path]]) -> None:
            if self._page is not None:
                for image_id, path in fetched:
                    self._page.set_thumbnail(image_id, path)

        self._host.runner.run(download, done, lambda _error: None)

    # -- envoi ------------------------------------------------------------------------------

    def upload_files(self, paths: list[Path]) -> None:
        files = []
        for path in paths:
            try:
                content = path.read_bytes()
            except OSError:
                self._host.notify(f"Impossible de lire « {path.name} ».", NotifyLevel.ERROR)
                continue
            if len(content) > self._max_bytes:
                self._host.notify(
                    f"« {path.name} » est trop lourde ({format_size(len(content))}, "
                    f"maximum {format_size(self._max_bytes)}).",
                    NotifyLevel.ERROR,
                )
                continue
            files.append((path.name, content))
        self._upload(files)

    def upload_data(self, name: str, content: bytes) -> None:
        self._upload([(name, content)])

    def _upload(self, files: list[tuple[str, bytes]]) -> None:
        if not files:
            return

        def send() -> list[dict[str, Any]]:
            return [self._host.api.upload_image(name, content) for name, content in files]

        def done(uploaded: list[dict[str, Any]]) -> None:
            self.copy_link(HostedImage.from_api(uploaded[-1]))
            count = len(uploaded)
            message = "Image envoyée" if count == 1 else f"{count} images envoyées"
            self._host.notify(f"{message} : lien copié.", NotifyLevel.SUCCESS)
            self.refresh()

        call_api(self._host, send, done, on_failed=lambda _error: self.refresh())

    # -- actions ----------------------------------------------------------------------------

    def find(self, image_id: str) -> HostedImage | None:
        return next((image for image in self._images if image.id == image_id), None)

    def link(self, image: HostedImage) -> str:
        return self._host.api.absolute_url(image.url)

    def copy_link(self, image: HostedImage) -> None:
        self.last_link = self.link(image)
        QGuiApplication.clipboard().setText(self.last_link)

    def rename(self, image_id: str, title: str) -> None:
        call_api(
            self._host,
            lambda: self._host.api.rename_image(image_id, title),
            lambda _raw: self.refresh(),
            success="Image renommée.",
        )

    def delete(self, image_id: str) -> None:
        call_api(
            self._host,
            lambda: self._host.api.delete_hosted_image(image_id),
            lambda _result: self.refresh(),
            success="Image supprimée.",
        )

    def _on_action(self, action: str, image_id: str) -> None:
        image = self.find(image_id)
        if image is None:
            return
        if action == "copy":
            self.copy_link(image)
            self._host.notify("Lien copié.", NotifyLevel.SUCCESS)
        elif action == "open":
            QDesktopServices.openUrl(QUrl(self.link(image)))
        elif action == "rename":
            title, accepted = QInputDialog.getText(self._page, "Renommer l'image", "Nouveau titre :", text=image.title)
            if accepted and title.strip() and title.strip() != image.title:
                self.rename(image_id, title.strip())
        elif action == "delete":
            question = f"Supprimer « {image.title} » ? Le lien ne fonctionnera plus, y compris sur Discord."
            if ask(self._page, "Supprimer l'image", question):
                self.delete(image_id)
