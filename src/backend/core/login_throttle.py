"""Login / first-access brute-force throttle via Redis."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import get_settings
from app.utils import utc_now

logger = logging.getLogger("forensicauth.security")


@dataclass
class ThrottleDecision:
    allowed: bool
    just_locked: bool = False


class LoginThrottle:
    """Count auth failures per username and IP; temporary lockout after threshold."""

    def __init__(self, redis_client=None):
        self.settings = get_settings()
        self._client = redis_client

    def _redis(self):
        if self._client is not None:
            return self._client
        import redis

        return redis.Redis.from_url(self.settings.REDIS_URL, decode_responses=True)

    @property
    def max_failures(self) -> int:
        return int(self.settings.AUTH_MAX_FAILURES)

    @property
    def window_seconds(self) -> int:
        return int(self.settings.AUTH_FAILURE_WINDOW_SECONDS)

    @property
    def lockout_seconds(self) -> int:
        return int(self.settings.AUTH_LOCKOUT_SECONDS)

    def _fail_user_key(self, username: str) -> str:
        return f"auth:fail:user:{username}"

    def _fail_ip_key(self, ip: str) -> str:
        return f"auth:fail:ip:{ip}"

    def _lock_user_key(self, username: str) -> str:
        return f"auth:lock:user:{username}"

    def _lock_ip_key(self, ip: str) -> str:
        return f"auth:lock:ip:{ip}"

    def is_locked(self, *, username: str, ip: str) -> bool:
        username = (username or "").strip().lower()
        ip = (ip or "").strip() or "unknown"
        try:
            client = self._redis()
            return bool(
                client.exists(self._lock_user_key(username))
                or client.exists(self._lock_ip_key(ip))
            )
        except Exception:
            logger.exception(
                "AUTH_THROTTLE_REDIS_ERROR op=is_locked username=%s ip=%s",
                username,
                ip,
            )
            # Fail-open if Redis is down so legitimate logins are not bricked.
            return False

    def record_failure(self, *, username: str, ip: str) -> ThrottleDecision:
        """Increment failure counters; set lockout when threshold is reached."""
        username = (username or "").strip().lower()
        ip = (ip or "").strip() or "unknown"
        try:
            client = self._redis()
            pipe = client.pipeline()
            u_key = self._fail_user_key(username)
            i_key = self._fail_ip_key(ip)
            pipe.incr(u_key)
            pipe.incr(i_key)
            pipe.ttl(u_key)
            pipe.ttl(i_key)
            u_count, i_count, u_ttl, i_ttl = pipe.execute()

            pipe2 = client.pipeline()
            if u_ttl is None or u_ttl < 0:
                pipe2.expire(u_key, self.window_seconds)
            if i_ttl is None or i_ttl < 0:
                pipe2.expire(i_key, self.window_seconds)
            pipe2.execute()

            just_locked = False
            if u_count >= self.max_failures or i_count >= self.max_failures:
                already = bool(
                    client.exists(self._lock_user_key(username))
                    or client.exists(self._lock_ip_key(ip))
                )
                client.setex(self._lock_user_key(username), self.lockout_seconds, "1")
                client.setex(self._lock_ip_key(ip), self.lockout_seconds, "1")
                just_locked = not already
                if just_locked:
                    self._audit_lockout(
                        username=username,
                        ip=ip,
                        user_failures=int(u_count),
                        ip_failures=int(i_count),
                    )
            return ThrottleDecision(allowed=False, just_locked=just_locked)
        except Exception:
            logger.exception(
                "AUTH_THROTTLE_REDIS_ERROR op=record_failure username=%s ip=%s",
                username,
                ip,
            )
            return ThrottleDecision(allowed=True, just_locked=False)

    def clear(self, *, username: str, ip: str) -> None:
        username = (username or "").strip().lower()
        ip = (ip or "").strip() or "unknown"
        try:
            client = self._redis()
            client.delete(
                self._fail_user_key(username),
                self._fail_ip_key(ip),
                self._lock_user_key(username),
                self._lock_ip_key(ip),
            )
        except Exception:
            logger.exception(
                "AUTH_THROTTLE_REDIS_ERROR op=clear username=%s ip=%s",
                username,
                ip,
            )

    def _audit_lockout(
        self,
        *,
        username: str,
        ip: str,
        user_failures: int,
        ip_failures: int,
    ) -> None:
        # Structured security audit event (logs → journald/docker logs).
        logger.warning(
            "AUTH_LOCKOUT username=%s ip=%s at=%s user_failures=%s ip_failures=%s "
            "window_s=%s lockout_s=%s",
            username,
            ip,
            utc_now().isoformat(),
            user_failures,
            ip_failures,
            self.window_seconds,
            self.lockout_seconds,
        )
