# Syncron 4.4

Les outils internes de notre pays sur NationsGlory : un **logiciel téléchargeable** (Windows, Linux, macOS) réservé aux membres du pays, connecté à une **API hébergée**. La connexion se fait avec **Discord** (limitée au serveur Discord du pays), et une **administration découpée par système** permet à l'équipe de tout tenir à jour.

| Outil | Pour qui | Ce qu'il fait |
|---|---|---|
| **Messagerie** | tous | annonces de l'équipe et nouvelles du pays, avec notifications |
| **Craft** | tous | ressources, étapes, ateliers, prérequis et temps de fabrication (calcul local, hors ligne possible) |
| **R&D** | tous | les cinq domaines (global, militaire, ressources, industrie, technologie), leurs paliers, conditions, récompenses et l'avancement du pays (380 / 1 000…), paliers validés dans l'ordre |
| **Calendrier** | tous | réunions, guerres, événements, économie ; vue du mois ou liste ; événements récurrents |
| **Convertisseur** | tous | stacks (64), lignes (576), coffres (1 728), doubles coffres (3 456) : division euclidienne ou unité unique |
| **Alertes** | tous | page en travaux : arrivera avec l'intégration de l'API NationsGlory |
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
| `tests/` | 176 tests : noyau, API sur PostgreSQL réel, client de bout en bout contre un vrai serveur |
| `docs/` | `DEPLOIEMENT.md` (mise en ligne, mises à jour), `ARCHITECTURE.md` (systèmes, ajouter un outil), `SECURITE.md` (audit) |

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

## Nouveautés de la 4.4

- **R&D** :
  - une condition chiffrée ne se coche qu'une fois sa quantité atteinte (1 000 / 1 000), et se décoche si le compteur redescend ;
  - plus de « recherche en cours » ni de messages R&D : un seul bouton, « Valider le palier », quand il a été fait en jeu ;
  - récompenses en texte seul (les anciennes récompenses liées à un objet sont converties en texte) ;
  - les conditions se remplissent sur tous les paliers à la fois, mais les paliers se valident dans l'ordre : les récompenses du palier 2 ne s'obtiennent qu'après la validation du palier 1 ;
  - l'équipe voit dans la barre latérale les paliers prêts à valider.
- **Alertes** : nouvel outil, page en travaux en attendant l'intégration de l'API NationsGlory.

## Nouveautés de la 4.3

- **Calendrier** : grille du mois redessinée (plus aucun chevauchement, titres raccourcis avec « … » et complets au survol), vue **Liste**, événements **récurrents** (chaque jour, chaque semaine sur les jours choisis, chaque mois, avec date de fin) et annulation d'une seule date, événements sur une **journée** sans heure.
- **R&D** : suivi des conditions chiffrées (380 / 1 000) et cases à cocher directement dans la page R&D pour l'équipe, boutons « Lancer » et « Valider » sur les paliers, administration refaite (paliers en pastilles, lignes sur deux rangées, reprise du palier précédent, Ctrl+S). L'équipe est prévenue quand toutes les conditions d'un palier sont remplies.
- **Convertisseur** : deux modes, division euclidienne (648 = 1 ligne + 1 stack + 8 objets seuls, contenants au choix) ou unité unique (648 = 10 stacks + 8 objets seuls).
- **Notifications** : pastille avec le nombre de messages non lus sur l'icône de Syncron dans la barre des tâches, et icône qui clignote à l'arrivée d'un message.
- **Formulaires d'administration** sans débordement à droite, navigation réduite aux icônes quand la fenêtre est étroite.
- **Sécurité** : voir [`docs/SECURITE.md`](docs/SECURITE.md).

## Nouveautés de la 4.1

- Textes revus : Syncron est l'outil interne **du pays** (nom configurable avec `SYNCRON_NATION_NAME`), le rôle de base s'appelle **Membre**.
- **Calendrier** et **R&D** opérationnels ; nouvel outil **Convertisseur** (les quantités du Craft affichent aussi leur équivalent en contenants au survol).
- **Messagerie et notifications** : cloche avec compteur, bulles, notifications du bureau ; tous les systèmes peuvent y publier.
- **Administration par système** : chaque outil apporte ses écrans ; les éditeurs ne gèrent que les systèmes qui leur sont confiés ; vue d'ensemble et journal par système.
- Accueil épuré : plus de barre de recherche, plus de carte Administration (elle reste dans « Gestion »).
- « À compléter » du Craft : la ligne « Recettes sans temps de fabrication » disparaît (sans temps = instantané).
