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
    min_client_version: str = "4.3.0"
    nation_name: str = Field("", max_length=60, description="Nom du pays affiché dans le client")
    dev_login: bool = Field(False, description="Connexion sans Discord, réservée au développement local")
    auth_rate_limit: int = Field(30, ge=0, description="Requêtes de connexion par minute et par adresse (0 = illimité)")
    max_request_bytes: int = Field(5 * 1024 * 1024, ge=64 * 1024)

    @model_validator(mode="after")
    def _check(self) -> Settings:
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
