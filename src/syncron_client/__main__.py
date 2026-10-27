"""Point d'entrée du client : `python -m syncron_client [--user DOSSIER] [--server URL]`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from syncron_client.paths import AppPaths
from syncron_client.shell.application import Launcher, configure_application
from syncron_core import APP_DISPLAY_NAME, APP_NAME


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_NAME, description=APP_DISPLAY_NAME)
    parser.add_argument("--user", type=Path, help="Dossier des données locales (défaut : dossier applicatif)")
    parser.add_argument("--server", help="Adresse de l'API (remplace la configuration)")
    arguments, _qt_arguments = parser.parse_known_args(argv[1:])
    return arguments


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    arguments = parse_arguments(argv)
    if arguments.server:
        os.environ["SYNCRON_SERVER_URL"] = arguments.server
    app = QApplication(argv)
    configure_application(app)
    launcher = Launcher(AppPaths.resolve(arguments.user))
    launcher.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
