"""Syncron — noyau métier partagé (sans Qt, sans base de données, sans réseau).

Utilisé à l'identique par le serveur (validation, calcul côté API) et par le
client (calcul instantané et hors ligne sur le catalogue mis en cache).
"""

__version__ = "4.0.0"
APP_NAME = "Syncron"
APP_DISPLAY_NAME = "Syncron"
APP_TAGLINE = "La boîte à outils des joueurs NationsGlory"

# Version du contrat HTTP entre le client et le serveur.
API_VERSION = 1
