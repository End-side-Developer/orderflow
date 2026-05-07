from __future__ import annotations

import base64
import hashlib

import bcrypt


_BCRYPT_ROUNDS = 12
_BCRYPT_SHA256_PREFIX = "bcrypt_sha256$"
_BCRYPT_PREFIXES = ("$2a$", "$2b$", "$2y$")


def _bcrypt_sha256_secret(plain: str) -> bytes:
    digest = hashlib.sha256(plain.encode("utf-8")).digest()
    # Base64 keeps us in ASCII and well below bcrypt's 72-byte limit.
    return base64.b64encode(digest)


def _extract_bcrypt_rounds(hashed: str) -> int | None:
    parts = hashed.split("$")
    if len(parts) < 4:
        return None
    try:
        return int(parts[2])
    except (TypeError, ValueError):
        return None


def hash_password(plain: str) -> str:
    raw = plain.encode("utf-8")
    use_sha256 = len(raw) > 72
    secret = _bcrypt_sha256_secret(plain) if use_sha256 else raw
    hashed = bcrypt.hashpw(secret, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")
    if use_sha256:
        return f"{_BCRYPT_SHA256_PREFIX}{hashed}"
    return hashed


def verify_password(plain: str, hashed: str) -> bool:
    core_hash = hashed
    use_sha256 = False
    if hashed.startswith(_BCRYPT_SHA256_PREFIX):
        core_hash = hashed[len(_BCRYPT_SHA256_PREFIX) :]
        use_sha256 = True

    if not core_hash.startswith(_BCRYPT_PREFIXES):
        return False

    secret = _bcrypt_sha256_secret(plain) if use_sha256 else plain.encode("utf-8")
    try:
        return bool(bcrypt.checkpw(secret, core_hash.encode("utf-8")))
    except ValueError:
        return False


def needs_rehash(hashed: str) -> bool:
    core_hash = (
        hashed[len(_BCRYPT_SHA256_PREFIX) :] if hashed.startswith(_BCRYPT_SHA256_PREFIX) else hashed
    )
    rounds = _extract_bcrypt_rounds(core_hash)
    if rounds is None:
        return True
    return rounds != _BCRYPT_ROUNDS
