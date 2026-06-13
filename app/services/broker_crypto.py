import base64
import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Pre-v2 records were all encrypted with this single static salt. Kept ONLY so
# existing ciphertext stays decryptable — never used to encrypt new keys.
_PBKDF2_SALT_LEGACY = b"alphaswarm-broker-key-v1"
_PBKDF2_ITERATIONS = 390_000  # NIST 2023 recommendation for PBKDF2-SHA256
_SALT_BYTES = 16

# v2 envelope: "v2:<urlsafe-b64 salt>:<fernet token>". PBKDF2-derived. Kept as a
# decrypt-only fallback for records written before the v3 cutover.
_V2_PREFIX = "v2:"

# v3 envelope: "v3:<urlsafe-b64 salt>:<fernet token>". HKDF-derived. BROKER_KEY_
# ENCRYPTION_SECRET is a high-entropy 32+ char key, not a human password, so the
# right primitive is HKDF (extract-and-expand) — not PBKDF2's password-stretching.
# HKDF is ~constant-time, removing the 390k-iteration CPU cost per encrypt/decrypt.
# All NEW keys use this; v2/legacy remain decryptable so no migration is required.
_V3_PREFIX = "v3:"
_HKDF_INFO = b"alphaswarm-broker-key-v3"


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


def _derive_fernet_hkdf(secret: str, salt: bytes) -> Fernet:
    """v3 derivation — HKDF, for the high-entropy BROKER_KEY_ENCRYPTION_SECRET."""
    kdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=_HKDF_INFO)
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return Fernet(key)


def _derive_fernet_pbkdf2(secret: str, salt: bytes) -> Fernet:
    """v2 / legacy derivation — PBKDF2. Decrypt-only path for pre-v3 ciphertext."""
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
    """Static-salt PBKDF2 Fernet — decrypt-only path for pre-v2 ciphertext."""
    return _derive_fernet_pbkdf2(_validated_secret(), _PBKDF2_SALT_LEGACY)


def encrypt_key(plaintext: str) -> str:
    secret = _validated_secret()
    salt = os.urandom(_SALT_BYTES)
    token = _derive_fernet_hkdf(secret, salt).encrypt(plaintext.encode()).decode()
    return f"{_V3_PREFIX}{base64.urlsafe_b64encode(salt).decode()}:{token}"


def decrypt_key(ciphertext: str) -> str:
    try:
        if ciphertext.startswith(_V3_PREFIX):
            # v3:<b64salt>:<token> — HKDF, current scheme.
            _, b64salt, token = ciphertext.split(":", 2)
            salt = base64.urlsafe_b64decode(b64salt)
            return _derive_fernet_hkdf(_validated_secret(), salt).decrypt(token.encode()).decode()
        if ciphertext.startswith(_V2_PREFIX):
            # v2:<b64salt>:<token> — PBKDF2 with the record's own salt.
            _, b64salt, token = ciphertext.split(":", 2)
            salt = base64.urlsafe_b64decode(b64salt)
            return _derive_fernet_pbkdf2(_validated_secret(), salt).decrypt(token.encode()).decode()
        # Legacy record encrypted with the old static PBKDF2 salt.
        return _legacy_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError) as exc:  # ValueError covers bad split / b64
        logger.error("Broker key decryption failed — wrong secret or corrupted ciphertext")
        raise ValueError("Broker key decryption failed — wrong secret or corrupted data") from exc
