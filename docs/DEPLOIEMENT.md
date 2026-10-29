# Mise en ligne de Syncron

Syncron est le logiciel interne du pays : il est réservé à ses membres. Ce guide va d'un serveur vide jusqu'au client distribué aux membres. Compter environ 30 minutes.

> **Tu passes de la 4.0 à la 4.1 ?** Lis directement la [section 8](#8-passer-de-la-40-à-la-41).

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
| **R&D** · Domaines et paliers | nombre de paliers, paliers terminés, recherche en cours ; conditions et récompenses de chaque palier |
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

## 8. Passer à la 4.3

La migration `0003` ajoute le suivi des conditions de R&D et la récurrence des événements ; elle conserve toutes les données.

1. Sur le serveur : dans `.env`, mets `SYNCRON_MIN_CLIENT_VERSION=4.3.0`, puis `git pull && docker compose up -d --build`.
2. Publie le client : pousse le tag `v4.3.0` ; le workflow GitHub construit `Syncron-windows.zip` et la Release. Les clients 4.2 se mettent à jour tout seuls au prochain lancement.

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
