# Audit de sécurité — Syncron 4.3, mis à jour en 4.5, 5.1, 5.2 et 5.3

Revue du serveur (FastAPI, PostgreSQL), du client (PySide6), du déploiement (Docker, Caddy) et de la mise à jour automatique. Chaque point corrigé est couvert par un test (`tests/server/test_security.py`, `tests/client/test_units.py`, `tests/client/test_systems_ui.py`).

## Corrigé dans la 4.3

| # | Gravité | Problème | Correction |
|---|---|---|---|
| 1 | Moyenne | **Image « bombe de décompression »** : un PNG minuscule déclarant 30 000 × 30 000 pixels était décodé en mémoire (plusieurs Go) avant d'être réduit. Un éditeur, ou un compte d'éditeur volé, pouvait faire tomber l'API. | Dimensions vérifiées **avant** décodage (4096 × 4096 au plus), `DecompressionBombError` interceptée. |
| 2 | Moyenne | **Client connecté en HTTP** : une adresse `http://` vers un serveur distant était acceptée (Paramètres, `syncron.json`, variable d'environnement). Les jetons circulaient alors en clair. | HTTPS obligatoire ; HTTP accepté seulement vers cette machine (`127.0.0.1`, `localhost`) pour le développement. |
| 3 | Moyenne | **Pas de limite de débit sur la connexion** : essais en rafale possibles sur `/auth/token`, `/auth/refresh` et `/auth/discord/*`. | 30 requêtes par minute et par adresse IP (`SYNCRON_AUTH_RATE_LIMIT`), réponse 429 avec `Retry-After`. |
| 4 | Faible | **Texte des membres interprété comme du HTML** : un titre d'annonce, d'événement ou d'objet contenant `<b>`, `<a href>` ou `<img>` était mis en forme par Qt (liens trompeurs, mise en page cassée). Même chose dans le rapport d'import JSON. | Tous les textes s'affichent tels quels (`PlainText`), y compris dans les boîtes de confirmation ; le rapport d'import échappe les identifiants et les messages. |
| 5 | Faible | **Taille des requêtes** limitée seulement par Caddy : une API exposée sans Caddy acceptait des corps JSON énormes (import). | Limite dans l'application aussi : 5 Mo, portée à 10 Mo en 4.5 pour les images (`SYNCRON_MAX_REQUEST_BYTES`), réponse 413. |
| 6 | Faible | **Image envoyée pour un objet inexistant** : le fichier était écrit sur le disque avant la vérification, et l'identifiant n'était pas contrôlé. | Identifiant et existence vérifiés avant toute écriture. |
| 7 | Faible | **Mise à jour automatique** : l'archive pouvait venir de n'importe quel hôte indiqué par la Release, sans limite de taille, et l'extraction faisait confiance aux chemins du zip. | Téléchargements uniquement depuis GitHub en HTTPS (redirections comprises), 400 Mo au plus, 1 Go une fois extrait, chemins vérifiés un par un avant extraction. |

## Vérifié en 5.3 (carte Iris)

- **Un seul client vers Iris** : c'est le serveur qui interroge iris.nationsglory.fr, pas chaque logiciel. Adresse en `https://` obligatoire (refusée au démarrage sinon), monde limité à `[a-z0-9_-]`, identifiants de pays encodés dans l'URL, **aucune redirection suivie**, réponse plafonnée à 40 Mo et lue en flux, JSON invalide rejeté. Fréquences bornées dans la configuration (météo ≥ 20 s, carte ≥ 5 min, membres ≥ 1 h) et pause entre deux pays, pour rester correct envers le site.
- **Relances manuelles** réservées au système « nationsglory », 6 par 10 minutes et par compte, inscrites au journal.
- **Données du site affichées telles quelles** dans le logiciel (noms de pays, joueurs, grades, événements) : textes en `PlainText`, couleurs acceptées seulement au format `#rrggbb`, info-bulle de la carte en texte brut.
- **Alertes** : personnelles, gardées sur le poste (types suivis, événements déjà vus) ; rien n'est publié dans la messagerie.

## Vérifié en 5.2

- **Banque** : lecture par les membres connectés, écriture réservée au système « bank » (et aux administrateurs) ; montants bornés et non nuls, catégories fixées, membre lié vérifié, chaque ajout, correction et suppression au journal. Textes (motifs, pseudos) affichés tels quels, info-bulles échappées.
- **Rubrique Pays** : simple regroupement côté client, aucun nouveau droit.

## Corrigé dans la 5.1

| # | Gravité | Problème | Correction |
|---|---|---|---|
| 1 | Moyenne | **Réglages ignorés en production** : `docker-compose.yml` ne transmettait à l'API qu'une liste fixe de variables. Les limites ajoutées depuis la 4.3 (`SYNCRON_AUTH_RATE_LIMIT`, tailles et quotas d'images) restaient à leur valeur par défaut, quoi qu'on mette dans `.env`. | `env_file: .env` : tout `SYNCRON_*` de `.env` arrive à l'API. |
| 2 | Moyenne | **Adresse du client usurpable** : uvicorn faisait confiance à `X-Forwarded-For` venant de n'importe où. Une API joignable sans passer par Caddy permettait de contourner la limite de connexions en changeant d'adresse à chaque essai. | Seuls le réseau Docker et la machine locale peuvent la transmettre (`SYNCRON_FORWARDED_ALLOW_IPS`). |
| 3 | Faible | **HTML dans les info-bulles** : Qt interprète le HTML d'une info-bulle. Un nom d'objet, un titre d'image ou d'événement, une description de profil contenant `<img src=…>` ou un lien s'affichait mis en forme au survol. | Toutes les info-bulles qui reprennent un texte saisi l'échappent (`plain_tooltip`). |
| 4 | Faible | **Téléchargements du client sans restriction** : le client téléchargeait toute adresse renvoyée par le serveur (avatars, images). | Seulement les fichiers du serveur Syncron et les avatars `https://cdn.discordapp.com/avatars/`. |
| 5 | Faible | **Avatar Discord non vérifié** : l'identifiant d'avatar reçu de Discord entrait tel quel dans une adresse. | Format vérifié (`[a_]` + 32 caractères hexadécimaux), sinon ignoré. |
| 6 | Faible | **Envoi d'images en rafale** : seul le quota total freinait un membre ; chaque envoi décode et réencode l'image (processeur). | 30 envois par 10 minutes et par membre (`SYNCRON_HOSTED_IMAGE_UPLOADS_PER_10_MINUTES`), réponse 429. |
| 7 | Faible | **Fichiers média** : servis sans politique de contenu. | `Content-Security-Policy: default-src 'none'; sandbox` sur `/media/*` (Caddy). |
| 8 | Info | **Dépendances** : bornes basses anciennes (`python-multipart` 0.0.9, `h11` non borné) qui ont connu des failles. | `python-multipart>=0.0.20`, `h11>=0.16`. `pip-audit` : aucune vulnérabilité connue. |

Nouveautés vérifiées : **profils** (chacun ne modifie que le sien, longueurs et formats contrôlés, comptes suspendus absents de l'annuaire, pseudo Discord masquable) ; **NationsGlory** (clé uniquement côté serveur et jamais renvoyée, HTTPS obligatoire, routes construites à partir de paramètres validés puis encodés, pas de redirection suivie, 2 Mo par réponse, 20 appels directs par minute et par compte, historique plafonné).

## Hébergement d'images (4.5)

- **Contenu** : chaque image est décodée puis réencodée par le serveur (PNG, JPEG ou GIF animé) ; rien d'autre que les pixels n'est gardé (EXIF, position GPS, données cachées dans le fichier). Fichier qui n'est pas une image : refusé. Dimensions vérifiées avant décodage (4096 × 4096), animation limitée (300 images, 64 Mpx au total).
- **Adresse** : `/media/images/<jeton>` avec 12 octets aléatoires (`secrets.token_urlsafe`) : impossible de deviner ou d'énumérer les images. Seuls les membres connectés voient la galerie ; un lien partagé, lui, est public par nature (c'est le but).
- **Abus** : 8 Mo par image, 200 images par membre, 2 Go au total (réglables), journal de chaque envoi, renommage et suppression. L'équipe qui gère « Images » peut supprimer n'importe quelle image ; un membre, seulement les siennes.
- **Serveur** : servies en statique avec le bon type et `X-Content-Type-Options: nosniff` (Caddy) ; extensions limitées à `.png`, `.jpg`, `.gif`.

## Vérifié, sans problème

- **Connexion Discord** : PKCE S256, état signé (10 min), code à usage unique haché (2 min), adresse de retour limitée à la boucle locale, secret Discord jamais transmis au client.
- **Jetons** : JWT signé HS256 avec algorithme et audience imposés, 15 minutes ; jeton de rafraîchissement opaque, haché en base, rotatif, avec révocation de toutes les sessions s'il est rejoué.
- **Droits** : le rôle et les systèmes confiés sont relus en base à **chaque** requête. Un compte rétrogradé ou suspendu perd ses droits immédiatement, même avec un jeton encore valide (test ajouté).
- **Injection SQL** : toutes les requêtes passent par SQLAlchemy avec paramètres liés.
- **Fichiers** : les images sont réencodées en PNG et nommées par empreinte ; la suppression refuse tout chemin hors du dossier média.
- **Production** : documentation de l'API désactivée, connexion de développement refusée au démarrage, secret JWT de 32 caractères minimum, HSTS et `nosniff` posés par Caddy.
- **Messagerie** : chaque compte ne voit et ne modifie que sa boîte ; les annonces exigent la gestion de la messagerie ; les messages « équipe » ne sont visibles que des éditeurs et administrateurs.

## Recommandations (hors code)

1. **Réserver Syncron au serveur Discord du pays** avec `SYNCRON_DISCORD_REQUIRED_GUILD_ID`. Sans ce réglage, tout compte Discord peut entrer en simple membre et lire le calendrier, la R&D et les annonces.
2. **Signer l'exécutable Windows** (certificat Authenticode) et publier la somme de contrôle signée. Aujourd'hui, l'intégrité de la mise à jour repose sur la sécurité du compte GitHub : activez la double authentification sur les comptes qui peuvent pousser des tags.
3. **Ne pas exposer le port 8000** de l'API : laissez Caddy seul en façade (c'est le cas du `docker-compose.yml` fourni). La limite de débit s'appuie sur l'adresse transmise par Caddy.
4. **Sauvegardes chiffrées** hors du serveur (`backup.sh` + copie distante).
