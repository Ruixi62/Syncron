"""Mise à jour automatique du client Windows (build PyInstaller --onedir).

Principe : lire la dernière Release GitHub, télécharger le zip, vérifier son SHA-256,
l'extraire dans un dossier temporaire, puis lancer un script .bat détaché qui attend la
fermeture de l'application, copie les fichiers par-dessus l'installation et relance Syncron.exe.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from syncron_client.config import version_tuple
from syncron_core import __version__

LATEST_RELEASE_URL = "https://api.github.com/repos/Ruixi62/Syncron/releases/latest"
ARCHIVE_NAME = "Syncron-windows.zip"
EXE_NAME = "Syncron.exe"
TIMEOUT = httpx.Timeout(30.0, connect=8.0)
TRUSTED_HOSTS = frozenset(
    {"api.github.com", "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com"}
)
MAX_ARCHIVE_BYTES = 400 * 1024 * 1024
MAX_EXTRACTED_BYTES = 1024 * 1024 * 1024


class UpdateError(Exception):
    pass


def _check_url(url: str | httpx.URL) -> None:
    """Téléchargements uniquement depuis GitHub, en HTTPS (redirections comprises)."""
    parsed = httpx.URL(str(url))
    if parsed.scheme != "https" or parsed.host not in TRUSTED_HOSTS:
        raise UpdateError(f"Adresse de téléchargement refusée : {parsed.host}")


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    version: str
    url: str
    sha256: str


def app_dir() -> Path:
    return Path(sys.executable).parent


def can_self_update() -> bool:
    """Uniquement pour le .exe installé dans un dossier modifiable (pas en développement/tests)."""
    return sys.platform == "win32" and getattr(sys, "frozen", False) and os.access(app_dir(), os.W_OK)


def check_for_update() -> UpdateInfo | None:
    if not can_self_update():
        return None
    response = httpx.get(
        LATEST_RELEASE_URL,
        headers={"Accept": "application/vnd.github+json"},
        timeout=TIMEOUT,
        follow_redirects=True,
    )
    response.raise_for_status()
    release = response.json()
    version = str(release["tag_name"]).lstrip("v")
    if version_tuple(version) <= version_tuple(__version__):
        return None
    assets = {asset["name"]: asset["browser_download_url"] for asset in release.get("assets", [])}
    if ARCHIVE_NAME not in assets or f"{ARCHIVE_NAME}.sha256" not in assets:
        return None
    _check_url(assets[ARCHIVE_NAME])
    _check_url(assets[f"{ARCHIVE_NAME}.sha256"])
    checksum = httpx.get(assets[f"{ARCHIVE_NAME}.sha256"], timeout=TIMEOUT, follow_redirects=True)
    _check_url(checksum.url)
    checksum.raise_for_status()
    return UpdateInfo(version, assets[ARCHIVE_NAME], checksum.text.split()[0].lower())


def download_and_stage(info: UpdateInfo) -> Path:
    """Télécharge, vérifie et extrait. Retourne le dossier de travail temporaire."""
    workdir = Path(tempfile.mkdtemp(prefix="syncron-update-"))
    archive = workdir / ARCHIVE_NAME
    digest = hashlib.sha256()
    _check_url(info.url)
    size = 0
    with httpx.stream("GET", info.url, timeout=TIMEOUT, follow_redirects=True) as response:
        _check_url(response.url)
        response.raise_for_status()
        with archive.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 16):
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise UpdateError("Archive anormalement volumineuse.")
                handle.write(chunk)
                digest.update(chunk)
    if digest.hexdigest() != info.sha256:
        raise UpdateError("Archive corrompue (somme de contrôle invalide).")
    staged = (workdir / "staged").resolve()
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if sum(member.file_size for member in members) > MAX_EXTRACTED_BYTES:
            raise UpdateError("Archive invalide : contenu trop volumineux.")
        for member in members:
            if not (staged / member.filename).resolve().is_relative_to(staged):
                raise UpdateError(f"Archive invalide : chemin interdit ({member.filename}).")
        bundle.extractall(staged)
    archive.unlink()
    if not any((workdir / "staged").rglob(EXE_NAME)):
        raise UpdateError("Archive invalide : Syncron.exe introuvable.")
    return workdir


def apply_and_restart(workdir: Path) -> None:
    """Lance le script de remplacement ; l'appelant doit ensuite quitter l'application."""
    source = next((workdir / "staged").rglob(EXE_NAME)).parent
    target = app_dir()
    pid = os.getpid()
    script = Path(tempfile.gettempdir()) / f"syncron-apply-{pid}.bat"
    script.write_text(
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto wait\r\n"
        ")\r\n"
        f'robocopy "{source}" "{target}" /E /R:10 /W:1 >nul\r\n'
        f'start "" "{target / EXE_NAME}"\r\n'
        f'rd /s /q "{workdir}"\r\n'
        '(goto) 2>nul & del "%~f0"\r\n',
        encoding="utf-8",
    )
    subprocess.Popen(
        ["cmd", "/c", str(script)],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
