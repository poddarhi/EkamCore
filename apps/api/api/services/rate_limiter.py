"""Brute-force protection: progressive delays and account lockout via Redis."""

import asyncio
import hashlib

import structlog

from api.errors import AccountLockedError
from api.services.redis_client import REDIS_DB_SESSIONS, get_redis

logger = structlog.get_logger()

_KEY_PREFIX = "auth:failed:"
_TTL_SECONDS = 3600  # 1 hour

# Progressive delay thresholds: (failures, delay_seconds)
_DELAY_THRESHOLDS = [
    (10, 30),
    (5, 5),
    (3, 1),
]

_LOCKOUT_THRESHOLD = 20


def _key_for_email(email: str) -> str:
    return f"{_KEY_PREFIX}{email}"


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()


async def check_brute_force(email: str) -> None:
    """Check failure count; raise AccountLockedError if locked, else apply progressive delay."""
    r = get_redis(REDIS_DB_SESSIONS)
    key = _key_for_email(email)
    count_str = await r.get(key)
    if count_str is None:
        return

    count = int(count_str)

    if count >= _LOCKOUT_THRESHOLD:
        ttl = await r.ttl(key)
        retry_after = max(ttl, 0)
        logger.warning("auth_account_locked", email_hash=_hash_email(email), failure_count=count)
        raise AccountLockedError(
            error_code="AUTH_ACCOUNT_LOCKED",
            message="Account temporarily locked due to too many failed login attempts.",
            details={"retry_after_seconds": retry_after},
        )

    for threshold, delay in _DELAY_THRESHOLDS:
        if count >= threshold:
            logger.info("auth_progressive_delay", email_hash=_hash_email(email), failure_count=count, delay_seconds=delay)
            await asyncio.sleep(delay)
            return


async def record_failed_login(email: str) -> int:
    """Increment failure counter and set/refresh TTL. Returns new count."""
    r = get_redis(REDIS_DB_SESSIONS)
    key = _key_for_email(email)

    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, _TTL_SECONDS)
    results = await pipe.execute()
    return results[0]  # new count from INCR


async def clear_failed_logins(email: str) -> None:
    """Delete failure counter on successful login."""
    r = get_redis(REDIS_DB_SESSIONS)
    await r.delete(_key_for_email(email))


async def audit_login_attempt(*, email: str, success: bool, ip: str) -> None:
    """Log login attempt to structured logs. Never logs plaintext email."""
    logger.info(
        "object_audit_log",
        action="login_attempt",
        success=success,
        email_hash=_hash_email(email),
        ip=ip,
    )
