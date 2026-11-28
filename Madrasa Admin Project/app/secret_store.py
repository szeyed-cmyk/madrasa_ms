"""1.0.5: encryption for secrets kept in the database (SMTP password, payment gateway and SMS API secrets).

Values are encrypted with Fernet (AES-128-CBC + HMAC-SHA256, from the `cryptography` package). The key is
derived with HKDF-SHA256 from the app's SECRET_KEY (env var or data/.secret_key), so a copy of the database
alone does not reveal the secrets. Consequence: if SECRET_KEY changes, stored secrets can no longer be read;
the settings page then shows them as "not set" and the administrator enters them again.
Secrets are never returned by the API; the browser only learns whether a value is set.
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .config import settings

PREFIX = "enc:v1:"


def _fernet(secret_key: str | None = None) -> Fernet:
    material = (secret_key or settings.secret_key).encode("utf-8")
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"madrasa-pro-app-settings", info=b"v1").derive(material)
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str, secret_key: str | None = None) -> str:
    return PREFIX + _fernet(secret_key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(token: str | None, secret_key: str | None = None) -> str | None:
    """Plain text, or None when the value is missing or cannot be decrypted (e.g. SECRET_KEY changed)."""
    if not token or not token.startswith(PREFIX):
        return None
    try:
        return _fernet(secret_key).decrypt(token[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def mask(is_set: bool) -> str:
    """What the UI shows for a stored secret (never any part of the value itself)."""
    return "••••••••" if is_set else ""
