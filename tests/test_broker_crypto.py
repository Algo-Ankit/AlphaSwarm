"""
Broker key encryption tests.

Locks in the per-record random salt (v2 envelope) and that legacy static-salt
ciphertext still decrypts. Runnable with pytest OR directly:
    python tests/test_broker_crypto.py
"""
import os

os.environ.setdefault("BROKER_KEY_ENCRYPTION_SECRET", "x" * 40)

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.services import broker_crypto as bc  # noqa: E402


def test_roundtrip():
    ct = bc.encrypt_key("alpaca-api-key-123")
    assert ct.startswith("v2:")
    assert bc.decrypt_key(ct) == "alpaca-api-key-123"


def test_per_record_random_salt():
    # Same plaintext encrypted twice must differ — proves salt is per-record,
    # not the old single static salt.
    a = bc.encrypt_key("same-plaintext")
    b = bc.encrypt_key("same-plaintext")
    assert a != b
    salt_a = a.split(":", 2)[1]
    salt_b = b.split(":", 2)[1]
    assert salt_a != salt_b
    assert bc.decrypt_key(a) == bc.decrypt_key(b) == "same-plaintext"


def test_legacy_static_salt_still_decrypts():
    # Pre-v2 ciphertext (raw Fernet token, no v2: prefix) must remain readable.
    legacy = bc._legacy_fernet().encrypt(b"legacy-secret").decode()
    assert not legacy.startswith("v2:")
    assert bc.decrypt_key(legacy) == "legacy-secret"


def test_corrupted_ciphertext_raises_valueerror():
    try:
        bc.decrypt_key("v2:notbase64:garbage")
    except ValueError:
        return
    raise AssertionError("expected ValueError on corrupted ciphertext")


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    raise SystemExit(0 if passed == len(fns) else 1)
