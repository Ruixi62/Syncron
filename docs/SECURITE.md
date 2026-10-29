# Audit de sécurité — Syncron 4.3

Revue du serveur (FastAPI, PostgreSQL), du client (PySide6), du déploiement (Docker, Caddy) et de la mise à jour automatique. Chaque point corrigé est couvert par un test (`tests/server/test_security.py`, `tests/client/test_units.py`, `tests/client/test_systems_ui.py`).

## Corrigé dans la 4.3

| # | Gravité | Problème | Correction |
|---|---|---|---|
| 1 | Moyenne | **Image « bombe de décompression »** : un PNG minuscule déclarant 30 000 × 30 000 pixels était décodé en mémoire (plusieurs Go) avant d'être réduit. Un éditeur, ou un compte d'éditeur volé, pouvait faire tomber l'API. | Dimensions vérifiées **avant** décodage (4096 × 4096 au plus), `DecompressionBombError` interceptée. |
| 2 | Moyenne | **Client connecté en HTTP** : une adresse `http://` vers un serveur distant était acceptée (Paramètres, `syncron.json`, variable d'environnement). Les jetons circulaient alors en clair. | HTTPS obligatoire ; HTTP accepté seulement vers cette machine (`127.0.0.1`, `localhost`) pour le développement. |
| 3 | Moyenne | **Pas de limite de débit sur la connexion** : essais en rafale possibles sur `/auth/token`, `/auth/refresh` et `/auth/discord/*`. | 30 requêtes par minute et par adresse IP (`SYNCRON_AUTH_RATE_LIMIT`), réponse 429 avec `Retry-After`. |
| 4 | Faible | **Texte des membres interprété comme du HTML** : un titre d'annonce, d'événement ou d'objet contenant `<b>`, `<a href>` ou `<img>` était mis en forme par Qt (liens trompeurs, mise en page cassée). Même chose dans le rapport d'import JSON. | Tous les textes s'affichent tels quels (`PlainText`), y compris dans les boîtes de confirmation ; le rapport d'import échappe les identifiants et les messages. |
| 5 | Faible | **Taille des requêtes** limitée seulement par Caddy : une API exposée sans Caddy acceptait des corps JSON énormes (import). | Limite dans l'application aussi : 5 Mo (`SYNCRON_MAX_REQUEST_BYTES`), réponse 413. |
| 6 | Faible | **Image envoyée pour un objet inexistant** : le fichier était écrit sur le disque avant la vérification, et l'identifiant n'était pas contrôlé. | Identifiant et existence vérifiés avant toute écriture. |
| 7 | Faible | **Mise à jour automatique** : l'archive pouvait venir de n'importe quel hôte indiqué par la Release, sans limite de taille, et l'extraction faisait confiance aux chemins du zip. | Téléchargements uniquement depuis GitHub en HTTPS (redirections comprises), 400 Mo au plus, 1 Go une fois extrait, chemins vérifiés un par un avant extraction. |

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
