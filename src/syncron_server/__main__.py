"""`python -m syncron_server` : migre la base puis démarre l'API (derrière le reverse proxy)."""

from __future__ import annotations

import os
import sys

import uvicorn

from syncron_server.config import Settings
from syncron_server.migrate import upgrade

# Seul le reverse proxy (réseau Docker ou machine locale) peut indiquer l'adresse réelle du client :
# sinon n'importe qui contournerait la limite de connexions en inventant un en-tête X-Forwarded-For.
TRUSTED_PROXIES = "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"


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
        forwarded_allow_ips=os.environ.get("SYNCRON_FORWARDED_ALLOW_IPS", TRUSTED_PROXIES),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
