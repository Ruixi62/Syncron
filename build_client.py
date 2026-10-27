"""Construit le client téléchargeable : `python build_client.py --server-url https://api.mondomaine.fr`

Produit dist/Syncron/ (Syncron.exe sous Windows) avec syncron.json, qui fixe
l'adresse du serveur pour tous les joueurs. PyInstaller ne fait pas de
compilation croisée : construire sous Windows pour un .exe.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "Syncron"
ASSETS = ROOT / "src" / "syncron_client" / "ui" / "assets"
EXCLUDED = [
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtPdf",
    "syncron_server",
    "fastapi",
    "sqlalchemy",
    "asyncpg",
    "uvicorn",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Build du client {NAME}")
    parser.add_argument("--server-url", required=True, help="Adresse publique de l'API, ex. https://api.mondomaine.fr")
    parser.add_argument("--onefile", action="store_true", help="Un seul exécutable (démarrage plus lent)")
    arguments = parser.parse_args()
    if not arguments.server_url.startswith(("https://", "http://")):
        parser.error("--server-url doit commencer par https://")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        NAME,
        "--paths",
        str(ROOT / "src"),
        "--add-data",
        f"{ASSETS}{os.pathsep}syncron_client/ui/assets",
        "--icon",
        str(ASSETS / "syncron.ico"),
        "--hidden-import",
        "keyring.backends.Windows",
        "--hidden-import",
        "keyring.backends.SecretService",
        "--hidden-import",
        "keyring.backends.macOS",
        "--onefile" if arguments.onefile else "--onedir",
    ]
    for module in EXCLUDED:
        command += ["--exclude-module", module]
    command.append(str(ROOT / "src" / "main.py"))
    subprocess.run(command, check=True, cwd=ROOT)

    output = ROOT / "dist" if arguments.onefile else ROOT / "dist" / NAME
    config = {"server_url": arguments.server_url.rstrip("/")}
    (output / "syncron.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(f"Client construit : {output}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
