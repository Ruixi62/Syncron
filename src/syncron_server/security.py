"""Jetons : JWT d'accès courts, jetons de rafraîchissement opaques (hachés en base), PKCE."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

ALGORITHM = "HS256"
ACCESS_AUDIENCE = "syncron-api"
FLOW_AUDIENCE = "syncron-login-flow"


class TokenError(Exception):
    pass


def new_secret_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_pkce(verifier: str, challenge: str) -> bool:
    return 43 <= len(verifier) <= 128 and hmac.compare_digest(pkce_challenge(verifier), challenge)


def encode_access_token(secret: str, user_id: uuid.UUID, role: str, minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "role": role,
        "aud": ACCESS_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(secret: str, token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM], audience=ACCESS_AUDIENCE)
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc


def encode_flow(secret: str, data: dict[str, Any], minutes: int = 10) -> str:
    """État signé de la connexion Discord : rien n'est stocké côté serveur entre l'aller et le retour."""
    payload = {**data, "aud": FLOW_AUDIENCE, "exp": datetime.now(UTC) + timedelta(minutes=minutes)}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_flow(secret: str, token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM], audience=FLOW_AUDIENCE)
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
