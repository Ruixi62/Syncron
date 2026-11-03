# Syncron 5.3

Les outils internes de notre pays sur NationsGlory : un **logiciel téléchargeable** (Windows, Linux, macOS) réservé aux membres du pays, connecté à une **API hébergée**. La connexion se fait avec **Discord** (limitée au serveur Discord du pays), et une **administration découpée par système** permet à l'équipe de tout tenir à jour.

| Outil | Pour qui | Ce qu'il fait |
|---|---|---|
| **Messagerie** | tous | annonces de l'équipe et nouvelles du pays, avec notifications |
| **Craft** | tous | ressources, étapes, ateliers, prérequis et temps de fabrication (calcul local, hors ligne possible) |
| **Pays** | tous | l'accueil du pays, avec les onglets R&D, Membres et Banque |
| **R&D** (Pays) | tous | les cinq domaines (global, militaire, ressources, industrie, technologie), leurs paliers, conditions, récompenses et l'avancement du pays (380 / 1 000…), paliers validés dans l'ordre |
| **Calendrier** | tous | réunions, guerres, événements, économie ; vue du mois ou liste ; événements récurrents |
| **Convertisseur** | tous | stacks (64), lignes (576), coffres (1 728), doubles coffres (3 456) : division euclidienne ou unité unique |
| **Membres** (Pays) | tous | l'annuaire du pays : profils, pseudos en jeu, grades, spécialités, disponibilités |
| **Banque** (Pays) | tous, saisie par l'équipe | solde, opérations, contributeurs |
| **Recherche** | tous | la carte NationsGlory (Iris) : territoires, frontières, ressources, membres de chaque pays, événements en cours |
| **Images** | tous | héberger une image (bouton, glisser-déposer, Ctrl+V) et copier son lien public à partager sur Discord |
| **Mes alertes** | tous | alerte dès qu'une météorite, une faille ou un volcan apparaît sur la carte |
| **Administration** | éditeurs, admins | une rubrique par système (onglets), les comptes, NationsGlory et le journal |

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
| `tests/` | 208 tests : noyau, API sur PostgreSQL réel, client de bout en bout contre un vrai serveur |
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

## Nouveautés de la 5.3

- **Recherche** : la carte NationsGlory dans le logiciel. Pays à gauche (recherche par pays ou par joueur), carte au centre (déplacer, zoomer, couches Frontières, Claims, Régions, Marqueurs, Noms, Événements), fiche à droite : chunks, région, pétrole et gaz, maisons, membres avec leur grade et le chef ★. Clic sur un marqueur : ressources du biome ; « Infos monde » : heure et météo du jeu, régions, biomes. Gardée sur le disque pour le hors-ligne.
- **Mes alertes** : alerte dès qu'une **météorite**, une **faille** ou un **volcan** apparaît sur la carte (notification dans le logiciel et sur le bureau, pastille) ; chacun choisit ses types ; un clic ouvre la carte à l'endroit de l'événement. Liste des événements en cours et des 7 derniers jours.
- **Serveur** : collecteur de la carte Iris (météo chaque minute, carte toutes les 30 minutes, membres deux fois par jour) et écran Administration › NationsGlory › Carte Iris.
- **Message « Not Found »** plus clair : il indique la version du serveur qui répond et la route manquante.

## Nouveautés de la 5.2.1

- **Thème Noël renforcé** : guirlande lumineuse qui clignote en haut de la fenêtre, neige dans la barre latérale et sur l'accueil, titres dorés, « Joyeux Noël » sur l'accueil, rouge et vert plus francs.
- Serveur à jour : les vérifications de version temporaires (Images, Profil, Membres, Banque, Pays) sont retirées.

## Nouveautés de la 5.2

- **Pays** : nouvelle rubrique, la page d'accueil du pays (avancement de la R&D, membres, solde de la banque) avec les onglets **R&D**, **Membres** et **Banque**.
- **Banque** : solde du pays, entrées et sorties sur 30 jours, opérations (motif, catégorie, membre, date) saisies par l'équipe, classement des contributeurs.
- **Recherche** : page en travaux pour les informations des autres pays récupérées sur NationsGlory.
- **Thème Noël** : rouge, vert sapin et or, avec de la neige qui tombe sur l'accueil.
- **Mes alertes** : nouveau nom de l'outil Alertes.
- **Corrigé** : texte qui débordait sous les titres (Membres, Images) ; le profil se recharge bien à l'ouverture ; message clair au lieu d'une erreur quand le serveur n'a pas encore les profils.

## Nouveautés de la 5.1

- **Profils et annuaire** : Paramètres › Profil (pseudo en jeu, grade, description, spécialités, disponibilités, couleur, pseudo Discord visible ou non) avec aperçu ; nouvel outil **Membres** pour chercher qui fait quoi.
- **Paramètres refaits** en rubriques : Profil, Apparence, Notifications, Compte, Serveur, Stockage, Outils, À propos.
- **Thèmes** : clair adouci (plus de blanc éclatant), **Forêt** (sombre aux reflets verts) et **Cerisier** (rose pâle), choisis sur des vignettes.
- **Administration réorganisée** : rubriques en haut, onglets de la rubrique dessous, écrans en pleine largeur ; vue d'ensemble avec la liste de tout ce qui reste à faire.
- **NationsGlory** : connexion à l'API publique préparée côté serveur (clé jamais transmise au client, routes vérifiées, cache, historique en base) et écran Administration › NationsGlory pour tester et lire les réponses.
- **Images** : message clair si le serveur n'est pas à jour, au lieu de « Not Found ».
- **R&D** : la ligne d'aide sous l'avancement est retirée.
- **Sécurité** : voir [`docs/SECURITE.md`](docs/SECURITE.md) (section 5.1).

## Nouveautés de la 4.5

- **Interface épurée**, même identité turquoise : fonds unis, cartes sans contour, boutons et champs sans bordure jusqu'au survol.
- **Thème clair et thème sombre** : Paramètres › Apparence (Système, Sombre, Clair), appliqué tout de suite.
- **Images** : nouvel outil d'hébergement. Chaque membre envoie ses images (bouton, glisser-déposer, Ctrl+V d'une capture), le lien public est copié aussitôt ; galerie du pays, « Les miennes », recherche, renommage, suppression. Images réencodées (métadonnées et position GPS retirées), GIF animés conservés, adresse impossible à deviner, quota par membre et espace total plafonné.
- **R&D** : une condition à compteur tient sur une ligne, image de l'objet, texte de la condition, compteur à droite ; plus de barre de progression.
- **Craft** : les images des objets ne sont plus aplaties dans la liste (proportions conservées).

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
