"""Configuration du serveur, lue dans l'environnement (préfixe SYNCRON_) ou un fichier .env."""

from __future__ import annotations

from enum import StrEnum
from functools import cached_property
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TEST = "test"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SYNCRON_", env_file=".env", extra="ignore")

    env: Environment = Environment.PRODUCTION
    database_url: str = "postgresql+asyncpg://syncron:syncron@localhost:5432/syncron"
    public_url: str = Field("http://localhost:8000", description="URL publique de l'API, sans / final")

    jwt_secret: SecretStr = Field(..., min_length=32)
    access_token_minutes: int = Field(15, ge=1, le=240)
    refresh_token_days: int = Field(30, ge=1, le=365)

    discord_client_id: str = ""
    discord_client_secret: SecretStr = SecretStr("")
    discord_required_guild_id: str = Field("", description="Si renseigné, seuls les membres de ce serveur Discord")
    admin_discord_ids: str = Field("", description="IDs Discord toujours admins, séparés par des virgules")

    media_dir: Path = Path("media")
    max_image_bytes: int = 2 * 1024 * 1024
    min_client_version: str = "4.4.0"
    nation_name: str = Field("", max_length=60, description="Nom du pays affiché dans le client")
    dev_login: bool = Field(False, description="Connexion sans Discord, réservée au développement local")
    auth_rate_limit: int = Field(30, ge=0, description="Requêtes de connexion par minute et par adresse (0 = illimité)")
    max_request_bytes: int = Field(10 * 1024 * 1024, ge=64 * 1024)
    max_hosted_image_bytes: int = Field(8 * 1024 * 1024, ge=64 * 1024, description="Image hébergée : poids maximal")
    hosted_image_uploads_per_10_minutes: int = Field(30, ge=0, description="Envois d'images par membre (0 = illimité)")
    hosted_images_per_user: int = Field(200, ge=0, description="Images hébergées par membre (0 = illimité)")
    ng_api_url: str = Field("https://publicapi.nationsglory.fr", description="API publique NationsGlory")
    ng_api_key: SecretStr = Field(SecretStr(""), description="Clé de l'API NationsGlory (reste sur le serveur)")
    ng_api_auth_header: str = Field("Authorization", pattern=r"^[A-Za-z0-9-]{1,40}$")
    ng_api_auth_scheme: str = Field("Bearer", max_length=20, description="Préfixe de la clé (vide : clé seule)")
    ng_server: str = Field("", pattern=r"^[a-z0-9_-]{0,32}$", description="Serveur NationsGlory du pays (blue…)")
    ng_country: str = Field("", pattern=r"^[a-z0-9_-]{0,64}$", description="Identifiant du pays sur NationsGlory")
    ng_cache_seconds: int = Field(300, ge=0, le=86_400)
    ng_timeout_seconds: float = Field(10.0, gt=0, le=60)
    iris_enabled: bool = Field(True, description="Récupère la carte et la météo d'iris.nationsglory.fr")
    iris_url: str = Field("https://iris.nationsglory.fr", description="Site de la carte NationsGlory")
    iris_world: str = Field("earth", pattern=r"^[a-z0-9_-]{1,32}$")
    iris_weather_seconds: int = Field(60, ge=20, le=3600, description="Météo et état du jeu (alertes)")
    iris_map_minutes: int = Field(30, ge=5, le=1440, description="Territoires, atlas, frontières, régions")
    iris_members_hours: int = Field(12, ge=1, le=168, description="Membres de chaque pays")
    iris_pause_seconds: float = Field(0.2, ge=0.05, le=5, description="Pause entre deux requêtes de membres")
    hosted_images_total_bytes: int = Field(
        2 * 1024 * 1024 * 1024, ge=0, description="Espace total des images hébergées (0 = illimité)"
    )

    @model_validator(mode="after")
    def _check(self) -> Settings:
        if not self.iris_url.startswith("https://"):
            raise ValueError("SYNCRON_IRIS_URL doit commencer par https://.")
        if not self.ng_api_url.startswith("https://"):
            raise ValueError("SYNCRON_NG_API_URL doit commencer par https:// (la clé y est envoyée).")
        if self.dev_login and self.env is Environment.PRODUCTION:
            raise ValueError("SYNCRON_DEV_LOGIN est interdit quand SYNCRON_ENV=production.")
        if self.env is Environment.PRODUCTION and not (
            self.discord_client_id and self.discord_client_secret.get_secret_value()
        ):
            raise ValueError(
                "SYNCRON_DISCORD_CLIENT_ID et SYNCRON_DISCORD_CLIENT_SECRET sont obligatoires en production."
            )
        self.public_url = self.public_url.rstrip("/")
        return self

    @cached_property
    def admin_ids(self) -> frozenset[str]:
        return frozenset(part.strip() for part in self.admin_discord_ids.split(",") if part.strip())

    @property
    def discord_redirect_uri(self) -> str:
        return f"{self.public_url}/api/v1/auth/discord/callback"
