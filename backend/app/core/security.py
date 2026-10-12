"""Owner PIN hashing, verification, and brute-force throttling (stdlib only).

Stored format: ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``.
Comparisons use hmac.compare_digest so verification time does not leak how many bytes matched.
"""

import hashlib
import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

PIN_PATTERN = re.compile(r"^\d{4,8}$")
_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000

# Throttle: at most MAX_FAILED_ATTEMPTS wrong PINs per tenant within LOCKOUT_WINDOW_SECONDS.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 300
_failed_attempts: Dict[str, Deque[float]] = defaultdict(deque)


def is_valid_pin_format(pin: Optional[str]) -> bool:
    return bool(pin) and bool(PIN_PATTERN.match(pin))


def hash_pin(pin: str, *, iterations: int = _ITERATIONS) -> str:
    if not is_valid_pin_format(pin):
        raise ValueError("PIN must be 4 to 8 digits")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${salt.hex()}${digest.hex()}"


def verify_pin(pin: Optional[str], stored_hash: Optional[str]) -> bool:
    """Constant-time check of a PIN against a stored hash. Missing PIN/hash is never valid."""
    if not pin or not stored_hash:
        return False
    try:
        algo, iterations_s, salt_hex, hash_hex = stored_hash.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations_s))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


def _prune(tenant_id: str, now: float) -> Deque[float]:
    attempts = _failed_attempts[tenant_id]
    while attempts and now - attempts[0] > LOCKOUT_WINDOW_SECONDS:
        attempts.popleft()
    return attempts


def is_pin_locked(tenant_id: str) -> bool:
    return len(_prune(tenant_id, time.monotonic())) >= MAX_FAILED_ATTEMPTS


def record_pin_failure(tenant_id: str) -> None:
    _prune(tenant_id, time.monotonic()).append(time.monotonic())


def clear_pin_failures(tenant_id: str) -> None:
    _failed_attempts.pop(tenant_id, None)
