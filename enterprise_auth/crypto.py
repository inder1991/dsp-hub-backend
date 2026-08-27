"""Generation and comparison of short-lived public authentication secrets."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def new_opaque_value(n_bytes: int = 32) -> str:
    """Return a URL-safe value with at least 256 bits of entropy."""
    if n_bytes < 32:
        raise ValueError("Authentication values require at least 256 bits of entropy")
    return secrets.token_urlsafe(n_bytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_matches(presented_value: str, stored_hash: str) -> bool:
    if not presented_value or not stored_hash:
        return False
    return hmac.compare_digest(sha256_hex(presented_value), stored_hash)
