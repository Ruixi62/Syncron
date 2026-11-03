# Syncron 5.3 — Architecture

Syncron est le logiciel interne d'un pays de NationsGlory : un client de bureau réservé aux membres, connecté à une API hébergée.

## 1. Vue d'ensemble

Trois paquets Python dans un même dépôt, avec une seule règle de dépendance : **`syncron_core` ne dépend de rien**, et le serveur comme le client dépendent de lui.

```
syncron_core      modèles, moteur de calcul, validation, format JSON, exports, convertisseur   (Python pur)
   ▲        ▲
   │        └──── syncron_server   FastAPI · SQLAlchemy 2 async · PostgreSQL · Alembic · Discord OAuth2
   └───────────── syncron_client   PySide6 · httpx · keyring · cache disque
```

Le **même code** valide le catalogue côté serveur, avant chaque écriture, et calcule les crafts côté client. Un plan de fabrication est donc identique partout, y compris hors ligne.

### Systèmes

Tout est découpé en **systèmes**. Chacun a ses tables, ses routes de lecture, ses routes de gestion, son résumé dans la vue d'ensemble, son outil dans le client et ses écrans dans l'Administration.

| Système | Lecture (membres) | Gestion | Outil client |
|---|---|---|---|
| `craft` | `/api/v1/catalog`, `/api/v1/craft/plan` | `/api/v1/admin/craft/…` | Craft |
| `research` | `/api/v1/research` | `/api/v1/admin/research/…` | R&D |
| `calendar` | `/api/v1/calendar/events` | `/api/v1/admin/calendar/…` | Calendrier |
| `bank` | `/api/v1/bank` | `/api/v1/admin/bank/transactions[/{id}]` | Pays › Banque |
| `messages` | `/api/v1/inbox` | `/api/v1/admin/messages` | Messagerie |
| `images` | `/api/v1/images` (envoi par tout membre) | suppression de toute image | Images |
| `nationsglory` | `/api/v1/nationsglory/country`, `/api/v1/iris/{map,live,members,events}` | `/api/v1/admin/nationsglory/…`, `/api/v1/admin/iris[/refresh]` | Recherche, Mes alertes, Administration › NationsGlory |
| — | `/api/v1/profile`, `/api/v1/members` | chacun son profil | Membres, Paramètres › Profil |
| — | — | — | Convertisseur (local) |

Un éditeur gère les systèmes listés dans `users.permissions` ; un administrateur les gère tous, plus les comptes (`accounts` dans le journal).

## 2. Serveur

### Base de données (PostgreSQL)

```mermaid
erDiagram
    users ||--o{ refresh_tokens : "sessions"
    users ||--o{ audit_log : "auteur"
    users ||--o{ message_receipts : "lu / supprimé"
    messages ||--o{ message_receipts : "accusés"
    stations ||--o{ items : "atelier"
    items ||--o{ recipe_ingredients : "recette"
    items ||--o{ item_requirements : "prérequis"
    skills ||--o{ item_requirements : "compétence"
    research_categories ||--o{ research_tiers : "paliers"
    research_tiers ||--o{ research_lines : "conditions, récompenses"
    users ||--o{ calendar_events : "auteur"
    users {
        uuid id PK
        string discord_id UK
        string role "player | editor | admin"
        json permissions "systèmes confiés"
        bool is_banned
    }
    audit_log {
        bigint id PK
        string system "craft | research | calendar | messages | accounts"
        string action
        string summary
    }
    research_categories {
        string id PK
        int tier_count
        int completed "paliers validés en jeu"
        string skill_id "compétence Craft liée"
    }
    research_lines {
        bigint progress "quantité réunie (380 / 1 000)"
        string kind "condition | reward"
        string text "seul champ d'une récompense"
        bigint quantity
        string item_id "objet du catalogue (conditions)"
        bool done "seulement si progress ≥ quantity"
    }
    calendar_events {
        uuid id PK
        string category "meeting | war | event | economy | other"
        timestamptz starts_at
        timestamptz ends_at
        bool all_day
        string recurrence "none | daily | weekly | monthly"
        int recurrence_days "jours de la semaine (masque)"
        date recurrence_until
        json skipped_dates "dates annulées"
    }
    users ||--o{ bank_transactions : "contribue"
    bank_transactions {
        bigint id PK
        bigint amount "positif : entrée, négatif : sortie"
        string label
        string category "contribution | sale | purchase | tax | war | salary | other"
        string member_name "pseudo libre sans compte"
        timestamptz occurred_at
    }
    users ||--o| user_profiles : "profil"
    users ||--o{ ng_snapshots : "appelle"
    user_profiles {
        uuid user_id PK
        string nickname "pseudo en jeu"
        string title "grade"
        text bio
        json specialties
        string color
        bool show_discord
    }
    ng_snapshots {
        bigint id PK
        string kind "country | notations | …"
        string target "country/blue/levant"
        int status
        json payload "réponse brute"
    }
    users ||--o{ hosted_images : "envoie"
    hosted_images {
        uuid id PK
        string path UK "images/<jeton aléatoire>.png|jpg|gif"
        string title
        string content_type "image/png | image/jpeg | image/gif"
        int size_bytes
    }
    messages {
        bigint id PK
        string system
        string audience "all | staff | direct"
        string link_tool
        string link_key
    }
```

- Le catalogue Craft est **normalisé** et protégé par des clés étrangères et des contraintes `CHECK`. `catalog_state.revision` sert d'**ETag** au client et de **verrou** d'écriture. Un temps de fabrication absent vaut « instantané ».
- R&D : `completed ≤ tier_count`. Les paliers se **valident dans l'ordre** (`POST …/tiers/{n}/validate` exige le palier n-1 validé et toutes les conditions du palier n remplies) ; seul le dernier palier validé peut être annulé. Les conditions, elles, se suivent sur tous les paliers à la fois.
- Calendrier : une série est **une seule ligne** ; `/calendar/events` la déroule en occurrences (même heure locale de Paris, été comme hiver) avec `syncron_core.recurrence`, sans les dates annulées.
- R&D : les lignes gardent leur identifiant quand un palier est réenregistré, donc leur progression. Une condition chiffrée ne peut être cochée que si `progress ≥ quantity` (contrainte `done_reached`) ; une récompense n'a qu'un texte (contrainte `reward_text`). La R&D ne publie aucun message.
- Messagerie : les messages `direct` ont un accusé par destinataire créé à l'envoi ; ceux pour `all` / `staff` ont leur accusé créé à la première lecture. Un nouveau compte voit les annonces des 30 derniers jours.

### Un service commun : la messagerie

Tout système publie une nouvelle avec `messaging.post_message(session, system=…, title=…, body=…, audience=…, link_tool=…, link_key=…)`, dans sa propre transaction. Aujourd'hui :

| Déclencheur | Message |
|---|---|
| Premier login | « Bienvenue » au membre ; « Nouveau compte » à l'équipe |
| Rôle ou systèmes modifiés | message direct à la personne concernée |
| Événement créé, modifié ou annulé (« prévenir ») | à tout le pays, avec lien vers l'événement |
| Annonce | à tout le pays, à l'équipe ou à des membres choisis |

### Ajouter un système côté serveur

1. Ajouter son identifiant à `systems.SYSTEMS`.
2. Modèles dans `models.py` et migration Alembic (`alembic revision --autogenerate`).
3. Un routeur `routers/<système>.py` avec `router` (lecture, `UserDep`) et `admin_router` (gestion, `Depends(manager("<système>"))`), inclus dans `app.py`.
4. Un résumé `@overview_provider("<système>")` pour la vue d'ensemble, et `audit.record(…, "<système>", …)` à chaque écriture.

### NationsGlory

`nationsglory.py` : client de l'API publique (https://publicapi.nationsglory.fr). Routes connues : `playercount`, `country/{serveur}/{pays}`, `country/list/{serveur}`, `notations`, `mmr`, `hdv/{serveur}`, `planning`, `user/{pseudo}`. Chaque appel passe par des paramètres validés, sans redirection, 2 Mo au plus, avec un cache en mémoire ; la réponse est gardée dans `ng_snapshots` (100 par route, 5 000 au total). Les futurs outils (Alertes…) liront ces données en base plutôt que d'appeler l'API eux-mêmes.

### Carte Iris

`iris.py` : collecteur d'https://iris.nationsglory.fr, la carte publique du serveur. Une tâche de fond lancée avec l'API ; un **verrou PostgreSQL** (`pg_try_advisory_lock`) fait qu'un seul processus interroge le site.

| Tâche | Fréquence (`.env`) | Routes d'Iris | Gardé dans |
|---|---|---|---|
| météo | 60 s (`SYNCRON_IRIS_WEATHER_SECONDS`) | `/api/weather/<monde>`, `/api/state` | `iris_snapshots` (`weather`, `state`) et `iris_events` |
| carte | 30 min (`SYNCRON_IRIS_MAP_MINUTES`) | `/api/{territories,atlas,frontiers,regions}/<monde>` | `iris_snapshots` |
| membres | 12 h (`SYNCRON_IRIS_MEMBERS_HOURS`) | `/api/countries/<id>/members`, pause entre deux pays | `iris_snapshots` (`members`) |

- `iris_snapshots` : une ligne par donnée, la dernière réponse ; en cas d'échec, l'ancienne est gardée et l'erreur notée (Administration › NationsGlory › Carte Iris).
- `iris_events` : chaque événement météo (météorite, faille, volcan, autre), reconnu d'après ses mots et sa position (`x`/`z`, `pos`, `location`…), avec `first_seen`, `last_seen`, `ended_at`. Le format exact d'Iris n'étant pas documenté, `normalize_events` reste tolérant.
- HTTPS seulement, sans redirection, 40 Mo au plus par réponse. Les routes `/api/v1/iris/{map,live,members}` répondent avec un **ETag** (304 si rien n'a changé) et gardent le JSON assemblé en mémoire.
- Coordonnées : formes (territoires, frontières, régions) en **chunks** (1 chunk = 16 blocs) ; maisons, marqueurs, atlas et événements en **blocs**.

### Protections HTTP

`protection.py` : limite de débit par adresse sur `/api/v1/auth/*` (`SYNCRON_AUTH_RATE_LIMIT`, 30 par minute) et taille maximale des requêtes (`SYNCRON_MAX_REQUEST_BYTES`, 5 Mo). Les images sont refusées au-delà de 4096 × 4096 pixels avant décodage. Détails dans `SECURITE.md`.

### Authentification

1. Le client ouvre `GET /api/v1/auth/discord/start?redirect_uri=http://127.0.0.1:<port>/callback&state&code_challenge`.
2. L'API signe un état (JWT de 10 minutes) et redirige vers Discord.
3. Discord rappelle `/api/v1/auth/discord/callback`. L'API échange le code (le secret Discord ne quitte jamais le serveur), lit le profil, vérifie l'appartenance au serveur Discord du pays si c'est exigé, puis crée ou met à jour l'utilisateur.
4. L'API renvoie le navigateur sur `127.0.0.1` avec un **code à usage unique** de 2 minutes.
5. Le client échange ce code et son `code_verifier` (**PKCE S256**) contre un jeton d'accès JWT de 15 minutes et un jeton de rafraîchissement opaque de 30 jours, **haché** et **rotatif** (une réutilisation révoque toutes les sessions du compte).

### Endpoints

| Méthode | Route | Accès |
|---|---|---|
| GET | `/health`, `/api/v1/meta` (version, systèmes, nom du pays) | public |
| GET | `/api/v1/auth/discord/start`, `/callback` · POST `/token`, `/refresh`, `/logout` | public (jetons) |
| GET | `/api/v1/auth/me`, `/api/v1/catalog` (ETag), `/api/v1/research`, `/api/v1/calendar/events[/{id}]` | connecté |
| POST | `/api/v1/craft/plan` | connecté |
| GET, POST, DELETE | `/api/v1/inbox`, `/inbox/summary`, `/inbox/read`, `/inbox/{id}` | connecté (sa boîte) |
| GET | `/api/v1/admin/overview`, `/api/v1/admin/audit?system=` | éditeur (ses systèmes) |
| PUT, DELETE | `/api/v1/admin/craft/{items,stations,skills}/{id}[/image]` · POST `/import` · GET `/export` | Craft (`replace` : admin) |
| PUT, DELETE | `/api/v1/admin/research/categories/{id}[/tiers/{niveau}]` | R&D |
| PATCH | `/api/v1/admin/research/lines/{id}` (quantité réunie, condition cochée une fois atteinte) | R&D |
| POST, DELETE | `/api/v1/admin/research/categories/{id}/tiers/{niveau}/validate` (palier fait en jeu, ou annulation du dernier) | R&D |
| GET, POST, PUT, DELETE | `/api/v1/admin/calendar/events[/{id}]` (fiches, une ligne par série) | Calendrier |
| POST | `/api/v1/admin/calendar/events/{id}/skip` (annuler ou rétablir une date) | Calendrier |
| GET, POST, DELETE | `/api/v1/admin/messages[/{id}]`, `/recipients` | Messagerie |
| GET, POST | `/api/v1/images` (galerie, `?mine=true`, envoi multipart) | connecté |
| PATCH, DELETE | `/api/v1/images/{id}` | auteur de l'image, ou Images |
| GET, PUT | `/api/v1/profile` · GET `/api/v1/members[/{id}]` | connecté (son profil ; annuaire sans comptes suspendus) |
| GET | `/api/v1/nationsglory/country` (dernières données du pays) | connecté |
| GET | `/api/v1/iris/map`, `/live`, `/members` (ETag) · `/api/v1/iris/events` (en cours et 7 jours) | connecté |
| GET, POST | `/api/v1/admin/iris`, `/refresh` (`weather`, `map`, `members`) | NationsGlory |
| GET | `/api/v1/bank` (solde, 30 jours, opérations, contributeurs) | connecté |
| POST, PUT, DELETE | `/api/v1/admin/bank/transactions[/{id}]` | Banque |
| GET, POST | `/api/v1/admin/nationsglory`, `/fetch`, `/snapshots[/{id}]` | NationsGlory |
| GET, PATCH | `/api/v1/admin/users` | admin |
| GET | `/media/…` (dont `/media/images/<jeton>` : images partagées) | public, cache immuable |

## 3. Client

```
Launcher ──▶ LoginWindow ──(Discord / reprise / hors ligne)──▶ ShellWindow
   │                                                            │
   ├─ ApiClient (httpx, renouvellement des jetons)              ├─ Accueil (cartes des outils) · Paramètres
   ├─ TokenStore (coffre du système, ou fichier en repli)       ├─ Messagerie            (barre latérale, en haut)
   ├─ CatalogStore (cache disque, ETag, images)                 ├─ Pays (Accueil · R&D · Membres · Banque) · Craft · Calendrier · Recherche (carte)
   │                                                            ├─ Convertisseur · Images · Mes alertes
   ├─ NotificationCenter (cloche, bulles, bureau)               └─ Administration        (Gestion, éditeurs+)
   ├─ Session (utilisateur, rôle, systèmes confiés, en ligne)
   └─ TaskRunner (QThreadPool → retour dans le thread de l'interface)
```

- **Aucun appel réseau dans le thread de l'interface** : `TaskRunner` exécute les appels dans le pool de Qt.
- **Notifications** : `NotificationCenter` interroge `/inbox/summary` toutes les 60 secondes. Un message plus récent que le dernier vu (mémorisé par compte) déclenche une bulle, la pastille de la cloche et, si la fenêtre est en arrière-plan, une notification du bureau (désactivable dans Paramètres).
- **Alertes des outils** : `host.notifications.alert(titre, texte, outil, clé)` affiche une bulle et, fenêtre en arrière-plan, une notification du bureau ; un clic dessus ouvre `outil` sur `clé`. Mes alertes s'en sert pour les événements météo d'Iris (vérification toutes les 30 secondes, types choisis par chacun, un événement n'alerte qu'une fois).
- **Recherche** : carte dessinée avec `QPainter` (`tools/intel/map_view.py`) à partir des données d'Iris, gardées sur le disque pour le hors-ligne ; heure et météo du jeu rafraîchies chaque minute tant que la page est ouverte.
- **Thème** : `ui/theme.py` définit les palettes Sombre, Clair, Forêt et Cerisier ; `COLORS` est un seul objet dont les valeurs changent (`use_palette`). Changer de thème (Paramètres › Apparence, ou le système en mode « Système ») réapplique la feuille de style et reconstruit les fenêtres.
- **Hors ligne** : si le serveur est injoignable, l'application s'ouvre en lecture seule sur les dernières données reçues (catalogue, R&D, calendrier), avec une pastille « Hors ligne · Réessayer ».
- **Version minimale** : `/meta.min_client_version` bloque les clients trop anciens.

### Contrat d'un outil

`ToolInfo` : `id`, `name`, `icon`, `placement` (`MAIN` sous l'accueil, `TOOLS` dans « Outils » et sur l'accueil, `MANAGE` dans « Gestion »), `min_role`, `system`, `parent`.

**Rubriques** (`platform/hub.py`) : un `HubTool` (Pays) affiche dans des onglets les outils dont `ToolInfo.parent` vaut son identifiant, plus sa propre page d'accueil. Ces outils restent des outils à part entière (données, liens des messages, recherche, administration) ; la fenêtre redirige `show_page("research")` vers Pays › R&D et ne les montre pas dans la barre latérale.

`Tool` : `setup(host)`, `create_page()`, `activated()`, `open(clé)` (liens des messages et recherche), `status()` (pastille), `page_actions()`, et **`admin_sections()`** : les écrans de gestion du système, que l'outil Administration regroupe sous le nom de l'outil et ne montre qu'aux comptes qui gèrent `system`.

`ToolHost` : `api`, `session`, `runner`, `catalog`, `notifications`, `tools()`, `notify`, `handle_error`, `open_tool`.

### Ajouter un outil

1. Créer `src/syncron_client/tools/<outil>/` avec une sous-classe de `Tool`.
2. S'il a des données serveur : un système (section 2) et les méthodes correspondantes dans `ApiClient`.
3. S'il se gère : `admin_sections()` renvoie des `AdminSection(clé, titre, icône, fabrique)`. Un écran peut proposer `refresh()`, `open_key(clé)` et `is_dirty()`.
4. L'ajouter à `builtin_tools()`.

## 4. Tests

| Suite | Ce qui est vérifié |
|---|---|
| `tests/core` | calcul (arrondis fusionnés, temps, ateliers, prérequis, stock), format JSON, validation, convertisseur (décomposition, saisie libre) |
| `tests/server` | sur **PostgreSQL réel** : parcours Discord, jetons, droits par rôle **et par système**, catalogue (écritures refusées, suppressions expliquées, images, import / export), vue d'ensemble par système, R&D (paliers, limites, recherche unique, annonces), calendrier (périodes, fuseaux, annonces), messagerie (audiences, lu / supprimé, annonces retirées) |
| `tests/client` | contre un **vrai serveur uvicorn** : connexion, Craft, administration par système, comptes et systèmes confiés, notifications et messagerie, calendrier de bout en bout (création → message → lien), R&D (édition → suivi des conditions → validation dans l'ordre), page Alertes, convertisseur, hors-ligne |
