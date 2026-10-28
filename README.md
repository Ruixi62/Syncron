# Syncron 4.1

Les outils internes de notre pays sur NationsGlory : un **logiciel téléchargeable** (Windows, Linux, macOS) réservé aux membres du pays, connecté à une **API hébergée**. La connexion se fait avec **Discord** (limitée au serveur Discord du pays), et une **administration découpée par système** permet à l'équipe de tout tenir à jour.

| Outil | Pour qui | Ce qu'il fait |
|---|---|---|
| **Messagerie** | tous | annonces de l'équipe et nouvelles du pays, avec notifications |
| **Craft** | tous | ressources, étapes, ateliers, prérequis et temps de fabrication (calcul local, hors ligne possible) |
| **R&D** | tous | les cinq domaines (global, militaire, ressources, industrie, technologie), leurs paliers, conditions, récompenses et l'avancement du pays |
| **Calendrier** | tous | réunions, guerres, événements, économie, en vue mensuelle |
| **Convertisseur** | tous | une quantité en stacks (64), lignes (576), coffres (1 728) et doubles coffres (3 456) |
| **Administration** | éditeurs, admins | une section par système, plus les comptes et le journal |

```
┌──────────────────────────┐      HTTPS / JSON       ┌───────────────────────────┐      ┌────────────┐
│ Client PySide6           │ ──────────────────────▶ │ API FastAPI               │ ───▶ │ PostgreSQL │
│ • outils du pays         │  OAuth2 Discord + PKCE  │ • comptes, rôles, droits  │      └────────────┘
│ • notifications          │ ◀────────────────────── │ • craft, R&D, calendrier  │      ┌────────────┐
│ • cache hors ligne       │   ETag, images /media   │ • messagerie, journal     │ ───▶ │ /media     │
└──────────────────────────┘                         └───────────────────────────┘      └────────────┘
                                  Caddy (HTTPS automatique) devant l'API
```

| Dossier | Contenu |
|---|---|
| `src/syncron_core/` | Métier partagé, sans dépendance : modèles, moteur de calcul, validation, format JSON, exports, convertisseur |
| `src/syncron_server/` | API : FastAPI, SQLAlchemy 2 async, Alembic, Discord OAuth2, JWT, un routeur par système |
| `src/syncron_client/` | Client de bureau : connexion, session, notifications, plateforme d'outils, un paquet par outil |
| `deploy/` | Dockerfile, docker-compose (PostgreSQL + API + Caddy), `.env.example`, sauvegardes, catalogue d'exemple |
| `tests/` | 152 tests : noyau, API sur PostgreSQL réel, client de bout en bout contre un vrai serveur |
| `docs/` | `DEPLOIEMENT.md` (mise en ligne, passage 4.0 → 4.1) et `ARCHITECTURE.md` (systèmes, ajouter un outil) |

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

Voir [`docs/DEPLOIEMENT.md`](docs/DEPLOIEMENT.md) : application Discord, `docker compose up -d --build`, build du client avec `python build_client.py --server-url https://…`, rôles et systèmes confiés, mises à jour, sauvegardes.

## Nouveautés de la 4.1

- Textes revus : Syncron est l'outil interne **du pays** (nom configurable avec `SYNCRON_NATION_NAME`), le rôle de base s'appelle **Membre**.
- **Calendrier** et **R&D** opérationnels ; nouvel outil **Convertisseur** (les quantités du Craft affichent aussi leur équivalent en contenants au survol).
- **Messagerie et notifications** : cloche avec compteur, bulles, notifications du bureau ; tous les systèmes peuvent y publier.
- **Administration par système** : chaque outil apporte ses écrans ; les éditeurs ne gèrent que les systèmes qui leur sont confiés ; vue d'ensemble et journal par système.
- Accueil épuré : plus de barre de recherche, plus de carte Administration (elle reste dans « Gestion »).
- « À compléter » du Craft : la ligne « Recettes sans temps de fabrication » disparaît (sans temps = instantané).
