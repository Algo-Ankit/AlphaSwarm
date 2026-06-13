import base64
import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Pre-v2 records were all encrypted with this single static salt. Kept ONLY so
# existing ciphertext stays decryptable — never used to encrypt new keys.
_PBKDF2_SALT_LEGACY = b"alphaswarm-broker-key-v1"
_PBKDF2_ITERATIONS = 390_000  # NIST 2023 recommendation for PBKDF2-SHA256
_SALT_BYTES = 16

# v2 envelope: "v2:<urlsafe-b64 salt>:<fernet token>". Each record carries its
# own random salt so two keys with the same secret derive different Fernet keys.
_V2_PREFIX = "v2:"


def _validated_secret() -> str:
    secret = get_settings().broker_key_encryption_secret
    if not secret:
        raise RuntimeError(
            "BROKER_KEY_ENCRYPTION_SECRET is not set. "
            'Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    if len(secret) < 32:
        raise RuntimeError(
            "BROKER_KEY_ENCRYPTION_SECRET is too short — minimum 32 characters required."
        )
    return secret


def _derive_fernet(secret: str, salt: bytes) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return Fernet(key)


@lru_cache(maxsize=1)
def _legacy_fernet() -> Fernet:
    """Static-salt Fernet — decrypt-only path for pre-v2 ciphertext."""
    return _derive_fernet(_validated_secret(), _PBKDF2_SALT_LEGACY)


def encrypt_key(plaintext: str) -> str:
    secret = _validated_secret()
    salt = os.urandom(_SALT_BYTES)
    token = _derive_fernet(secret, salt).encrypt(plaintext.encode()).decode()
    return f"{_V2_PREFIX}{base64.urlsafe_b64encode(salt).decode()}:{token}"


def decrypt_key(ciphertext: str) -> str:
    try:
        if ciphertext.startswith(_V2_PREFIX):
            # v2:<b64salt>:<token> — derive with the record's own salt.
            _, b64salt, token = ciphertext.split(":", 2)
            salt = base64.urlsafe_b64decode(b64salt)
            return _derive_fernet(_validated_secret(), salt).decrypt(token.encode()).decode()
        # Legacy record encrypted with the old static salt.
        return _legacy_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError) as exc:  # ValueError covers bad split / b64
        logger.error("Broker key decryption failed — wrong secret or corrupted ciphertext")
        raise ValueError("Broker key decryption failed — wrong secret or corrupted data") from exc
