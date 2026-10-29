"""Syncron — noyau métier partagé (sans Qt, sans base de données, sans réseau).

Utilisé à l'identique par le serveur (validation, calcul côté API) et par le
client (calcul instantané et hors ligne sur le catalogue mis en cache).
"""

__version__ = "4.3.4"
APP_NAME = "Syncron"
APP_DISPLAY_NAME = "Syncron"
APP_TAGLINE = "Les outils internes de notre pays sur NationsGlory"


def tagline(nation_name: str = "") -> str:
    """Accroche, avec le nom du pays quand le serveur le fournit (SYNCRON_NATION_NAME)."""
    return f"Les outils internes de {nation_name} sur NationsGlory" if nation_name else APP_TAGLINE


# Version du contrat HTTP entre le client et le serveur.
API_VERSION = 1
