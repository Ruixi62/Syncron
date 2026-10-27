# Syncron 4

La boîte à outils des joueurs NationsGlory : un **logiciel téléchargeable** (Windows, Linux, macOS) connecté à une **API hébergée**. La connexion se fait avec **Discord**, et un **mode admin** permet de gérer le catalogue en ligne.

```
┌──────────────────────┐      HTTPS / JSON       ┌────────────────────────┐      ┌────────────┐
│ Client PySide6       │ ──────────────────────▶ │ API FastAPI            │ ───▶ │ PostgreSQL │
│ • Craft (hors ligne) │  OAuth2 Discord + PKCE  │ • auth, rôles, jetons  │      └────────────┘
│ • Administration     │ ◀────────────────────── │ • catalogue validé     │      ┌────────────┐
│ • cache local        │   ETag, images /media   │ • images, journal      │ ───▶ │ /media     │
└──────────────────────┘                         └────────────────────────┘      └────────────┘
                                  Caddy (HTTPS automatique) devant l'API
```

| Dossier | Contenu |
|---|---|
| `src/syncron_core/` | Métier partagé, sans dépendance : modèles, moteur de calcul, validation, format JSON, exports |
| `src/syncron_server/` | API : FastAPI, SQLAlchemy 2 async, Alembic, Discord OAuth2, JWT, mode admin |
| `src/syncron_client/` | Client de bureau : connexion, session, cache, plateforme d'outils, Craft, Administration |
| `deploy/` | Dockerfile, docker-compose (PostgreSQL + API + Caddy), `.env.example`, sauvegardes, catalogue d'exemple |
| `tests/` | 108 tests : noyau, API sur PostgreSQL réel, client de bout en bout contre un vrai serveur |
| `docs/` | `DEPLOIEMENT.md` (mise en ligne pas à pas) et `ARCHITECTURE.md` |

## Démarrage rapide (développement)

```bash
python -m venv .venv && . .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
export SYNCRON_ENV=development SYNCRON_DEV_LOGIN=true SYNCRON_JWT_SECRET=$(openssl rand -hex 32)
export SYNCRON_DATABASE_URL=postgresql+asyncpg://syncron:syncron@localhost:5432/syncron
PYTHONPATH=src python -m syncron_server   # API + migrations
python src/main.py                        # client
```

Tests (PostgreSQL requis, base jetable créée automatiquement) :

```bash
SYNCRON_TEST_DATABASE_URL=postgresql+asyncpg://syncron@127.0.0.1:5432/postgres pytest
ruff check . && ruff format --check .
```

## Production

Voir [`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md) : application Discord, `docker compose up -d --build`, build du client avec `python build_client.py --server-url https://…`, rôles, mises à jour, sauvegardes.

## Ce qui a changé par rapport à la version 3 (locale)

- Les données de jeu sont sur le serveur : tout le monde voit le même catalogue, mis à jour instantanément par les éditeurs.
- On ne remplit plus les JSON à la main : on passe par le mode admin. Il comprend des éditeurs (objets, recettes, ateliers, compétences, images), un tableau de bord, la gestion des comptes, le journal des modifications et l'import / export JSON (même format qu'avant).
- Le calcul de craft reste local et instantané. Il fonctionne aussi **hors ligne** sur le dernier catalogue reçu.
- L'API expose aussi `POST /api/v1/craft/plan`, réutilisable par d'autres intégrations (un bot Discord, par exemple).
