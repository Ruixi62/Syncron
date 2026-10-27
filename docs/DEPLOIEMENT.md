# Mise en ligne de Syncron

Ce guide va d'un serveur vide jusqu'au client distribué aux joueurs. Compter environ 30 minutes.

## 1. Prérequis

- Un VPS Linux (2 vCPU, 2 Go de RAM suffisent) avec **Docker** et **Docker Compose**.
- Un nom de domaine, par exemple `api.syncron.mondomaine.fr`, avec un enregistrement DNS **A** (et **AAAA** si IPv6) pointant vers le VPS.
- Les ports **80** et **443** ouverts : Caddy les utilise pour obtenir le certificat HTTPS.

## 2. Application Discord

1. Va sur <https://discord.com/developers/applications> et clique sur **New Application** (nom : Syncron).
2. Dans l'onglet **OAuth2**, copie le **Client ID**, puis **Reset Secret** et copie le **Client Secret**.
3. Toujours dans **OAuth2**, ajoute ce **Redirect** : `https://api.syncron.mondomaine.fr/api/v1/auth/discord/callback`.
4. Pour réserver Syncron aux membres d'un serveur Discord, active le mode développeur de Discord, fais un clic droit sur le serveur, choisis **Copier l'identifiant**, puis renseigne cet identifiant dans `SYNCRON_DISCORD_REQUIRED_GUILD_ID`.
5. Récupère de la même façon ton propre identifiant Discord (clic droit sur ton profil, **Copier l'identifiant**) pour `SYNCRON_ADMIN_DISCORD_IDS`.

## 3. Démarrage

```bash
git clone <dépôt> /opt/syncron && cd /opt/syncron/deploy
cp .env.example .env
openssl rand -base64 32   # → POSTGRES_PASSWORD
openssl rand -hex 32      # → SYNCRON_JWT_SECRET
nano .env                 # domaine, secrets, Discord, admins
docker compose up -d --build
docker compose logs -f api   # « Application startup complete »
```

Le schéma de base est créé ou mis à jour automatiquement au démarrage (Alembic).

Vérifie ensuite que `https://api.syncron.mondomaine.fr/health` répond `{"status":"ok"}`.

## 4. Client

Sur un PC **Windows**, avec Python 3.12 :

```bash
pip install -r requirements-dev.txt
python build_client.py --server-url https://api.syncron.mondomaine.fr
```

Zippe le dossier `dist/Syncron/` puis distribue-le, par exemple en releases GitHub ou sur Discord. Le fichier `syncron.json` placé à côté de l'exe indique l'adresse du serveur : les joueurs n'ont rien à configurer.

Les données personnelles (préférences, cache du catalogue) sont rangées dans `%APPDATA%\Syncron`. La session de connexion est conservée dans le Gestionnaire d'identification de Windows.

## 5. Premier catalogue

1. Lance le client et connecte-toi avec Discord. Ton compte est administrateur s'il figure dans `SYNCRON_ADMIN_DISCORD_IDS`.
2. Va dans **Administration**, puis **Import / export**. Choisis `deploy/seed/catalogue-exemple.json` ou ton propre fichier, clique **Analyser**, puis **Appliquer**.
3. Ensuite, tout se modifie depuis **Administration**, dans les onglets **Objets**, **Ateliers** et **Compétences**. Chaque enregistrement est visible par tous les joueurs à leur prochaine actualisation (F5, ou ouverture de l'outil).

Le format du fichier JSON est le même que celui des versions locales. Son schéma pour VS Code est dans `deploy/seed/catalogue.schema.json`.

## 6. Rôles

| Rôle | Peut |
|---|---|
| Joueur | consulter et calculer |
| Éditeur | modifier objets, ateliers, compétences et images ; importer en fusion ; voir le journal |
| Administrateur | tout, plus gérer les comptes (rôles, suspension) et importer en remplacement total |

Les rôles se changent dans **Administration**, onglet **Comptes**. Suspendre un compte coupe immédiatement toutes ses sessions.

## 7. Mises à jour

- **Serveur** : `git pull && docker compose up -d --build`. Les migrations s'appliquent toutes seules.
- **Client** : publie le nouveau build. Pour obliger les joueurs à mettre à jour, augmente `SYNCRON_MIN_CLIENT_VERSION` dans `.env`, puis lance `docker compose up -d`. Les anciens clients affichent alors « Mise à jour requise ».

## 8. Sauvegardes

```bash
cd /opt/syncron/deploy && ./backup.sh         # base (pg_dump) + images, conservation 14 jours
crontab -e   # 0 4 * * * cd /opt/syncron/deploy && ./backup.sh >> backup.log 2>&1
```

Pour restaurer la base :

```bash
docker compose exec -T db pg_restore -U syncron -d syncron --clean < backups/syncron-<date>.dump
```

Exporte aussi régulièrement le catalogue (JSON) depuis le mode admin : c'est une sauvegarde lisible et réimportable.

## 9. Développement local

```bash
# PostgreSQL local, puis :
export SYNCRON_ENV=development SYNCRON_DEV_LOGIN=true SYNCRON_JWT_SECRET=$(openssl rand -hex 32)
export SYNCRON_DATABASE_URL=postgresql+asyncpg://syncron:syncron@localhost:5432/syncron
python -m syncron_server             # API sur http://127.0.0.1:8000 (docs : /docs)
python src/main.py                   # client ; « Connexion de développement » visible
```

`SYNCRON_DEV_LOGIN` permet de se connecter sans Discord avec le rôle de son choix. Le serveur refuse de démarrer si cette option est activée en production.
