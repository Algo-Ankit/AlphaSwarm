import base64
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_PBKDF2_SALT = b"alphaswarm-broker-key-v1"
_PBKDF2_ITERATIONS = 390_000  # NIST 2023 recommendation for PBKDF2-SHA256


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
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
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_PBKDF2_SALT,
        iterations=_PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return Fernet(key)


def encrypt_key(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        logger.error("Broker key decryption failed — wrong secret or corrupted ciphertext")
        raise ValueError("Broker key decryption failed — wrong secret or corrupted data") from exc
