"""Catalogue côté client : synchronisé avec l'API, mis en cache sur disque.

- démarrage : le cache local est chargé immédiatement (affichage instantané, mode hors ligne) ;
- synchronisation : requête conditionnelle (ETag) -> 304 si rien n'a changé ;
- images : téléchargées en arrière-plan dans cache/media/, nommées comme sur le serveur
  (le nom contient une empreinte : une image modifiée a une nouvelle URL).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from syncron_client.api.client import ApiClient, CatalogResponse
from syncron_client.api.errors import ApiError
from syncron_client.tasks import TaskRunner
from syncron_core.catalog import CraftData
from syncron_core.catalog_format import parse_catalog
from syncron_core.io import atomic_write_text

MEDIA_PREFIX = "/media/"


class CatalogStore(QObject):
    changed = Signal(int)
    syncFailed = Signal(object)
    imagesUpdated = Signal()

    def __init__(self, api: ApiClient, cache_file: Path, media_dir: Path, runner: TaskRunner) -> None:
        super().__init__()
        self._api = api
        self._cache_file = cache_file
        self._media_dir = media_dir
        self._runner = runner
        self._data = CraftData()
        self._revision = -1
        self._etag: str | None = None
        self._syncing = False
        self._downloading = False

    @property
    def data(self) -> CraftData:
        return self._data

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def loaded(self) -> bool:
        return self._revision >= 0

    # -- cache disque ----------------------------------------------------------------

    def load_cache(self) -> bool:
        try:
            cached = json.loads(self._cache_file.read_text(encoding="utf-8"))
            document = cached["document"]
        except (OSError, ValueError, KeyError, TypeError):
            return False
        return self._apply(document, cached.get("etag"), save=False)

    def _apply(self, document: dict[str, Any], etag: str | None, save: bool) -> bool:
        result = parse_catalog(document, "serveur")
        if result.has_errors:
            return False
        self._data = result.data
        self._revision = int(document.get("revision", 0))
        self._etag = etag
        if save:
            atomic_write_text(self._cache_file, json.dumps({"etag": etag, "document": document}, ensure_ascii=False))
        self.changed.emit(self._revision)
        return True

    # -- synchronisation ----------------------------------------------------------------

    def sync(self, on_done=None) -> None:
        """Met à jour depuis le serveur ; `on_done(changed: bool)` est appelé en fin de synchronisation."""
        if self._syncing:
            return
        self._syncing = True
        etag = self._etag if self.loaded else None

        def finished(response: CatalogResponse) -> None:
            self._syncing = False
            changed = False
            if not response.not_modified and response.document is not None:
                changed = self._apply(response.document, response.etag, save=True)
                if not changed:
                    self.syncFailed.emit(ApiError("Catalogue reçu illisible."))
            self.fetch_missing_images()
            if on_done is not None:
                on_done(changed)

        def failed(error: Exception) -> None:
            self._syncing = False
            self.syncFailed.emit(error)
            if on_done is not None:
                on_done(False)

        self._runner.run(lambda: self._api.catalog(etag), finished, failed)

    # -- images -------------------------------------------------------------------------

    def image_path(self, url: str | None) -> Path | None:
        path = self._local(url)
        return path if path is not None and path.is_file() else None

    def _local(self, url: str | None) -> Path | None:
        if not url or not url.startswith(MEDIA_PREFIX):
            return None
        relative = Path(url.removeprefix(MEDIA_PREFIX))
        if relative.is_absolute() or ".." in relative.parts:
            return None
        return self._media_dir / relative

    def fetch_missing_images(self) -> None:
        urls = {e.image for e in (*self._data.items, *self._data.stations) if e.image}
        missing = sorted(url for url in urls if self._local(url) is not None and self.image_path(url) is None)
        if not missing or self._downloading:
            return
        self._downloading = True

        def download() -> int:
            count = 0
            for url in missing:
                try:
                    content = self._api.download(url)
                except ApiError:
                    continue
                target = self._local(url)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                count += 1
            return count

        def finished(count: int) -> None:
            self._downloading = False
            if count:
                self.imagesUpdated.emit()

        def failed(_error: Exception) -> None:
            self._downloading = False

        self._runner.run(download, finished, failed)

    def clear_cache(self) -> None:
        self._cache_file.unlink(missing_ok=True)
        if self._media_dir.is_dir():
            for path in sorted(self._media_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                else:
                    path.rmdir()
