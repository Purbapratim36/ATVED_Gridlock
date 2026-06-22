"""
Security utilities: AES-256-GCM encryption, bcrypt hashing, JWT tokens.

All PII fields (license plates, appellant identifiers) are encrypted
at the application layer before database storage, using AES-256-GCM
which provides both confidentiality and authenticity. The encryption
key is loaded from the ATVED_ENCRYPTION_KEY environment variable
(base64-encoded 32-byte key).
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt
from passlib.context import CryptContext

import structlog

logger = structlog.get_logger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Encryption key ──────────────────────────────────────────────────

_ENCRYPTION_KEY: bytes | None = None


def _get_encryption_key() -> bytes:
    """Load and cache the encryption key from environment."""
    global _ENCRYPTION_KEY
    if _ENCRYPTION_KEY is None:
        raw = os.environ.get("ATVED_ENCRYPTION_KEY", "")
        if not raw:
            raise RuntimeError(
                "ATVED_ENCRYPTION_KEY environment variable is not set. "
                "Generate one with: python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\""
            )
        _ENCRYPTION_KEY = base64.b64decode(raw)
        if len(_ENCRYPTION_KEY) != 32:
            raise RuntimeError(
                f"ATVED_ENCRYPTION_KEY must decode to exactly 32 bytes, got {len(_ENCRYPTION_KEY)}"
            )
    return _ENCRYPTION_KEY


# ── AES-256-GCM field-level encryption ──────────────────────────────


def encrypt_pii(plaintext: str, key: bytes | None = None) -> bytes:
    """
    Encrypt a PII string with AES-256-GCM.

    Returns ``nonce (12 bytes) || ciphertext || tag (16 bytes)``.
    The nonce is randomly generated per encryption call, ensuring
    identical plaintexts produce different ciphertexts.
    """
    k = key or _get_encryption_key()
    aesgcm = AESGCM(k)
    nonce = os.urandom(12)  # 96-bit nonce as recommended by NIST
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext  # nonce is prepended for decryption


def decrypt_pii(ciphertext_blob: bytes, key: bytes | None = None) -> str:
    """
    Decrypt a PII blob previously encrypted with ``encrypt_pii``.

    Extracts the 12-byte nonce prefix, then decrypts and authenticates
    the remainder.
    """
    k = key or _get_encryption_key()
    if len(ciphertext_blob) < 28:  # 12 nonce + 16 tag minimum
        raise ValueError("Ciphertext blob is too short to be valid AES-256-GCM")
    nonce = ciphertext_blob[:12]
    ciphertext = ciphertext_blob[12:]
    aesgcm = AESGCM(k)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")


# ── Password hashing ────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return _pwd_context.verify(password, hashed)


# ── JWT tokens ──────────────────────────────────────────────────────


def create_jwt(
    data: dict,
    secret: str,
    algorithm: str = "HS256",
    expires_minutes: int = 60,
) -> str:
    """Create a signed JWT token with an expiry claim."""
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload["iat"] = datetime.now(timezone.utc)
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_jwt(
    token: str,
    secret: str,
    algorithm: str = "HS256",
) -> dict:
    """
    Decode and validate a JWT token.

    Raises ``jose.JWTError`` on invalid/expired tokens.
    """
    return jwt.decode(token, secret, algorithms=[algorithm])
