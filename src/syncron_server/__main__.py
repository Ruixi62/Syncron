"""`python -m syncron_server` : migre la base puis démarre l'API (derrière le reverse proxy)."""

from __future__ import annotations

import os
import sys

import uvicorn

from syncron_server.config import Settings
from syncron_server.migrate import upgrade


def main() -> int:
    settings = Settings()
    upgrade(settings.database_url)
    uvicorn.run(
        "syncron_server.app:create_app",
        factory=True,
        host=os.environ.get("SYNCRON_HOST", "0.0.0.0"),
        port=int(os.environ.get("SYNCRON_PORT", "8000")),
        workers=int(os.environ.get("SYNCRON_WORKERS", "2")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
