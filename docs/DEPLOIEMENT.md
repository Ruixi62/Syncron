# Mise en ligne de Syncron

Syncron est le logiciel interne du pays : il est réservé à ses membres. Ce guide va d'un serveur vide jusqu'au client distribué aux membres. Compter environ 30 minutes.

> **Tu mets à jour un serveur existant ?** Lis directement la [section 8](#8-passer-à-la-52).

## 1. Prérequis

- Un VPS Linux (2 vCPU, 2 Go de RAM suffisent) avec **Docker** et **Docker Compose**.
- Un nom de domaine, par exemple `api.syncron.mondomaine.fr`, avec un enregistrement DNS **A** (et **AAAA** si IPv6) pointant vers le VPS.
- Les ports **80** et **443** ouverts : Caddy les utilise pour obtenir le certificat HTTPS.

## 2. Application Discord

1. Va sur <https://discord.com/developers/applications> et clique sur **New Application** (nom : Syncron).
2. Dans l'onglet **OAuth2**, copie le **Client ID**, puis **Reset Secret** et copie le **Client Secret**.
3. Toujours dans **OAuth2**, ajoute ce **Redirect** : `https://api.syncron.mondomaine.fr/api/v1/auth/discord/callback`.
4. **Réserve Syncron au pays** : active le mode développeur de Discord, fais un clic droit sur le serveur Discord du pays, choisis **Copier l'identifiant**, puis renseigne cet identifiant dans `SYNCRON_DISCORD_REQUIRED_GUILD_ID`. Sans ce réglage, n'importe quel compte Discord peut se connecter (en simple membre).
5. Récupère de la même façon ton propre identifiant Discord (clic droit sur ton profil, **Copier l'identifiant**) pour `SYNCRON_ADMIN_DISCORD_IDS`.

## 3. Démarrage

```bash
git clone https://github.com/Ruixi62/Syncron.git /opt/syncron && cd /opt/syncron/deploy
cp .env.example .env
openssl rand -base64 32   # → POSTGRES_PASSWORD
openssl rand -hex 32      # → SYNCRON_JWT_SECRET
nano .env                 # domaine, secrets, Discord, admins, nom du pays
docker compose up -d --build
docker compose logs -f api   # « Application startup complete »
```

Le schéma de base est créé ou mis à jour automatiquement au démarrage (Alembic). Les cinq domaines de R&D (global, militaire, ressources, industrie, technologie) sont créés à ce moment-là.

Vérifie ensuite que `https://api.syncron.mondomaine.fr/health` répond `{"status":"ok"}`.

`SYNCRON_NATION_NAME` est affiché dans le logiciel (« Les outils internes de … »). Laisse-le vide pour afficher « notre pays ».

## 4. Client

Sur un PC **Windows**, avec Python 3.12 :

```bash
pip install -r requirements-dev.txt
python build_client.py --server-url https://api.syncron.mondomaine.fr
```

Zippe le dossier `dist/Syncron/` puis distribue-le aux membres, par exemple dans un salon du Discord du pays. Le fichier `syncron.json` placé à côté de l'exe indique l'adresse du serveur : les membres n'ont rien à configurer.

Les données personnelles (préférences, dernières données reçues pour le hors-ligne) sont rangées dans `%APPDATA%\Syncron`. La session de connexion est conservée dans le Gestionnaire d'identification de Windows.

## 5. Premier remplissage

Connecte-toi avec Discord : ton compte est administrateur s'il figure dans `SYNCRON_ADMIN_DISCORD_IDS`. Tout se fait ensuite dans **Administration**, découpée par système :

| Section | Ce qu'on y fait |
|---|---|
| **Général** · Vue d'ensemble | une carte par système (chiffres, éléments à compléter), comptes, activité récente |
| **Général** · Comptes | rôles, systèmes confiés aux éditeurs, suspension (administrateurs) |
| **Général** · Journal | qui a modifié quoi, filtrable par système |
| **Craft** · Objets, Ateliers, Compétences | le catalogue ; **Import / export** pour charger `deploy/seed/catalogue-exemple.json` ou ton fichier (Analyser, puis Appliquer) |
| **R&D** · Domaines et paliers | nombre de paliers, paliers validés (pour corriger l'avancement) ; conditions et récompenses de chaque palier. Au quotidien, l'équipe suit les conditions et valide les paliers depuis la page R&D |
| **Calendrier** · Événements | réunions, guerres, événements, économie ; « Prévenir tout le pays » envoie un message à chacun |
| **Messagerie** · Annonces | message à tout le pays, à l'équipe ou à des membres choisis |

Les temps de fabrication non renseignés valent « instantané ». Le format du fichier JSON du catalogue est le même que celui des versions locales ; son schéma pour VS Code est dans `deploy/seed/catalogue.schema.json`.

Les nombres de paliers de R&D sont ceux du wiki NationsGlory au moment de la mise à jour (global 16, militaire 16, ressources 15, industrie 12, technologie 7). S'ils changent en jeu, modifie-les dans **R&D · Domaines et paliers**.

## 6. Rôles et droits

| Rôle | Peut |
|---|---|
| Membre | consulter tous les outils, recevoir les messages |
| Éditeur | gérer **les systèmes qui lui sont confiés** (Craft, R&D, Calendrier, Messagerie), voir leur vue d'ensemble et leur journal |
| Administrateur | tout gérer, plus les comptes et le remplacement total du catalogue Craft |

Dans **Comptes**, passe un membre en Éditeur, puis choisis ses systèmes dans la colonne **Systèmes gérés**. La personne est prévenue dans sa messagerie. Suspendre un compte coupe immédiatement toutes ses sessions.

## 7. Mises à jour

- **Serveur** : `git pull && docker compose up -d --build`. Les migrations s'appliquent toutes seules.
- **Client** : publie le nouveau build. Pour obliger les membres à mettre à jour, augmente `SYNCRON_MIN_CLIENT_VERSION` dans `.env`, puis lance `docker compose up -d`. Les anciens clients affichent alors « Mise à jour requise ».

## 8. Passer à la 5.3

La migration `0008` crée les tables de la carte Iris (`iris_snapshots`, `iris_events`). Au démarrage, l'API lance le **collecteur Iris** : météo et heure du jeu chaque minute, carte toutes les 30 minutes, membres des pays toutes les 12 heures (réglages `SYNCRON_IRIS_*` dans `.env`, voir `.env.example`). Un seul processus de l'API interroge le site (verrou PostgreSQL).

1. Sur le serveur : `git pull && docker compose up -d --build`.
2. Vérifie `https://<ton domaine>/api/v1/meta` : `"version"` doit valoir `5.3.0`.
3. Administration › NationsGlory › **Carte Iris** : chaque donnée doit avoir une « Dernière réponse » après une minute (la carte peut prendre jusqu'à 30 minutes, ou bouton « Carte » pour la lancer tout de suite).
4. Publie le client : pousse sur `main`, la Release `v5.3.0` se crée et les clients se mettent à jour seuls.

**Le logiciel affiche « Le serveur du pays … ne connaît pas cette fonction » (ou « Not Found ») ?** C'est toujours l'ancienne API qui répond. Le message indique la version qui répond ; si elle est plus ancienne que le logiciel :

1. `curl https://<ton domaine>/api/v1/meta` : quelle `version` répond ?
2. `docker ps` : une seule pile Syncron doit tourner. Une ancienne pile (autre dossier, autre nom de projet) qui occupe encore les ports 80/443 répond à la place de la nouvelle : l'arrêter (`docker compose down` dans son dossier, ou `docker stop <id>`).
3. Dans le bon dossier : `git log -1` (le dernier commit doit être celui de la mise à jour), puis `docker compose build --no-cache api && docker compose up -d`.
4. `docker compose logs api --tail 50` : les migrations doivent s'appliquer sans erreur (`Running upgrade 0007 -> 0008`).

### Passer à la 5.2

La migration `0007` crée la table de la banque. Rien d'autre ne change côté serveur.

1. Sur le serveur : `git pull && docker compose up -d --build`, puis vérifie `https://<ton domaine>/api/v1/meta` : `"version"` doit valoir `5.2.0`. **Tant que ce n'est pas le cas, le profil, l'annuaire, les images et la banque ne fonctionnent pas** (le client l'indique en clair).
2. Publie le client : pousse sur `main`, la Release `v5.2.0` se crée et les clients se mettent à jour seuls.
3. Confie la **Banque** aux trésoriers : Administration › Comptes, cocher « Banque » dans leurs systèmes.

### Passer à la 5.1

La migration `0006` ajoute les profils des membres et l'historique de l'API NationsGlory.

1. Sur le serveur : `git pull && docker compose up -d --build`. Le `docker-compose.yml` lit maintenant **tout** `deploy/.env` (`env_file`) : les réglages facultatifs (images, NationsGlory, limites) y sont enfin pris en compte. Caddy reçoit aussi une protection supplémentaire sur `/media`.
2. Publie le client : pousse sur `main`, la Release `v5.1.0` se crée et les clients se mettent à jour seuls. `SYNCRON_MIN_CLIENT_VERSION` peut rester à `4.4.0`.

**L'outil Images affichait « Not Found » ?** C'est le signe d'un serveur resté en 4.4 : la route d'envoi n'existe pas encore. Après l'étape 1, vérifie `https://<ton domaine>/api/v1/meta` : `"version"` doit valoir `5.1.0` et `"systems"` contenir `images`. Le client 5.1 l'explique désormais en clair au lieu d'afficher « Not Found ».

**Relier le pays à NationsGlory** : dans `.env`, décommente et remplis `SYNCRON_NG_API_KEY`, `SYNCRON_NG_SERVER` (ex. `blue`) et `SYNCRON_NG_COUNTRY`, puis `docker compose up -d`. Teste dans Administration › NationsGlory (« Nombre de joueurs », puis « Pays »). Si la clé est refusée, essaie `SYNCRON_NG_API_AUTH_SCHEME=` (vide) ou un autre en-tête avec `SYNCRON_NG_API_AUTH_HEADER` : la documentation de NationsGlory ne précise pas le format attendu.

### Passer à la 4.5

La migration `0005` crée la table des images hébergées ; rien d'autre ne change dans la base.

1. Sur le serveur : `git pull && docker compose up -d --build`. **Recrée bien le conteneur Caddy** (`docker compose up -d` suffit) : la taille maximale des requêtes passe à 10 Mo pour l'envoi d'images.
2. Publie le client : pousse sur `main`, le workflow crée la Release `v4.5.0` et les clients se mettent à jour seuls. Pas besoin de changer `SYNCRON_MIN_CLIENT_VERSION` : un client 4.4 reste compatible (il n'a simplement pas l'outil Images).

Nouveaux réglages facultatifs (`.env`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `SYNCRON_MAX_HOSTED_IMAGE_BYTES` | 8 Mo | poids maximal d'une image envoyée |
| `SYNCRON_HOSTED_IMAGES_PER_USER` | 200 | images par membre (0 = illimité) |
| `SYNCRON_HOSTED_IMAGES_TOTAL_BYTES` | 2 Go | espace total réservé aux images (0 = illimité) |
| `SYNCRON_MAX_REQUEST_BYTES` | 10 Mo | taille maximale d'une requête (doit dépasser l'image la plus lourde) |

Les images sont dans le volume média (`media/images/`), déjà sauvegardé par `backup.sh`.

### Passer à la 4.4

La migration `0004` retire la « recherche en cours » de la R&D, réécrit en texte les récompenses qui citaient un objet (« 64 × Lingot de fer ») et décoche les conditions chiffrées cochées avant d'avoir atteint leur quantité. Le reste est conservé.

1. Sur le serveur : dans `.env`, mets `SYNCRON_MIN_CLIENT_VERSION=4.4.0`, puis `git pull && docker compose up -d --build`.
2. Publie le client : pousse sur `main` (la version est nouvelle, le workflow crée la Release). Les clients se mettent à jour tout seuls au prochain lancement.

Un client 4.3 enverrait encore la « recherche en cours » et des récompenses avec objet, que l'API 4.4 ignore ou refuse : d'où la version minimale.

### Passer à la 4.3

La migration `0003` ajoute le suivi des conditions de R&D et la récurrence des événements ; elle conserve toutes les données.

1. Sur le serveur : dans `.env`, mets `SYNCRON_MIN_CLIENT_VERSION=4.3.0`, puis `git pull && docker compose up -d --build`.
2. Publie le client : le workflow GitHub construit `Syncron-windows.zip` et la Release dès qu'une nouvelle version arrive sur `main`. Les clients 4.2 se mettent à jour tout seuls au prochain lancement.

Un client 4.2 resterait utilisable en lecture, mais l'écran de gestion de la R&D d'avant la 4.3 effacerait les quantités réunies en enregistrant un palier : d'où la version minimale.

Nouveaux réglages facultatifs : `SYNCRON_AUTH_RATE_LIMIT` (connexions par minute et par adresse, 30 par défaut) et `SYNCRON_MAX_REQUEST_BYTES` (5 Mo par défaut).

### Passer de la 4.0 à la 4.1

Les routes de gestion du Craft ont changé de place (`/api/v1/admin/craft/…`) : un client 4.0 ne peut plus rien modifier. Dans l'ordre :

1. Construis le client 4.1 (section 4) et prépare sa distribution.
2. Sur le serveur : ajoute à `.env` les lignes `SYNCRON_NATION_NAME=…` et `SYNCRON_MIN_CLIENT_VERSION=4.1.0`, puis `git pull && docker compose up -d --build`.
3. Distribue le client 4.1. Les clients 4.0 affichent « Mise à jour requise ».

La migration conserve tout : catalogue, comptes, journal. Les éditeurs existants gardent la gestion du Craft ; confie-leur les autres systèmes dans **Comptes** si besoin.

## 9. Sauvegardes

```bash
cd /opt/syncron/deploy && ./backup.sh         # base (pg_dump) + images, conservation 14 jours
crontab -e   # 0 4 * * * cd /opt/syncron/deploy && ./backup.sh >> backup.log 2>&1
```

Pour restaurer la base :

```bash
docker compose exec -T db pg_restore -U syncron -d syncron --clean < backups/syncron-<date>.dump
```

Exporte aussi régulièrement le catalogue Craft (JSON) depuis l'administration : c'est une sauvegarde lisible et réimportable.

## 10. Développement local

```bash
# PostgreSQL local, puis :
export SYNCRON_ENV=development SYNCRON_DEV_LOGIN=true SYNCRON_JWT_SECRET=$(openssl rand -hex 32)
export SYNCRON_DATABASE_URL=postgresql+asyncpg://syncron:syncron@localhost:5432/syncron
python -m syncron_server             # API sur http://127.0.0.1:8000 (docs : /docs)
python src/main.py                   # client ; « Connexion de développement » visible
```

`SYNCRON_DEV_LOGIN` permet de se connecter sans Discord avec le rôle de son choix (un éditeur de développement gère tous les systèmes). Le serveur refuse de démarrer si cette option est activée en production.
