"""Erreurs renvoyées par l'API, avec un message affichable."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Issue:
    severity: str
    message: str
    entity_id: str | None = None
    section: str = "items"

    def __str__(self) -> str:
        return f"{self.entity_id} : {self.message}" if self.entity_id else self.message


@dataclass(eq=False)
class ApiError(Exception):
    message: str
    status: int = 0
    issues: list[Issue] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def __str__(self) -> str:
        if not self.issues:
            return self.message
        details = "\n".join(f"• {issue}" for issue in self.issues[:8])
        more = f"\n… et {len(self.issues) - 8} autre(s)." if len(self.issues) > 8 else ""
        return f"{self.message}\n{details}{more}"


class NetworkError(ApiError):
    """Serveur injoignable (pas de réseau, serveur arrêté, délai dépassé)."""


class SessionExpired(ApiError):
    """Jetons invalides : il faut se reconnecter."""
