"""Actor token generation and digesting.

Kept apart from app/security.py so the repository layer can hash a presented
token without importing the HTTP dependency layer.

Tokens are high-entropy random strings, so a plain SHA-256 digest is enough; no
password-style derivation is needed, and the token itself is never stored.
"""

import hashlib
import secrets

_TOKEN_BYTES = 32


def generate_actor_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_actor_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()