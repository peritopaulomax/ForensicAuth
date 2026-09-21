"""Unit tests for Redis login throttle / lockout."""

from __future__ import annotations

import time
from typing import Any


class FakeRedis:
    """Minimal Redis stand-in for LoginThrottle tests."""

    def __init__(self):
        self.store: dict[str, Any] = {}
        self.expiry: dict[str, float] = {}

    def _alive(self, key: str) -> bool:
        exp = self.expiry.get(key)
        if exp is not None and exp <= time.time():
            self.store.pop(key, None)
            self.expiry.pop(key, None)
            return False
        return key in self.store

    def exists(self, *keys: str) -> int:
        return sum(1 for k in keys if self._alive(k))

    def incr(self, key: str) -> int:
        if not self._alive(key):
            self.store[key] = 0
        self.store[key] = int(self.store[key]) + 1
        return int(self.store[key])

    def ttl(self, key: str) -> int:
        if not self._alive(key):
            return -2
        exp = self.expiry.get(key)
        if exp is None:
            return -1
        return max(0, int(exp - time.time()))

    def expire(self, key: str, seconds: int) -> bool:
        if not self._alive(key) and key not in self.store:
            return False
        self.expiry[key] = time.time() + seconds
        return True

    def setex(self, key: str, seconds: int, value: str) -> bool:
        self.store[key] = value
        self.expiry[key] = time.time() + seconds
        return True

    def delete(self, *keys: str) -> int:
        n = 0
        for k in keys:
            if k in self.store or k in self.expiry:
                self.store.pop(k, None)
                self.expiry.pop(k, None)
                n += 1
        return n

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, redis: FakeRedis):
        self.redis = redis
        self.ops: list[tuple] = []

    def incr(self, key: str):
        self.ops.append(("incr", key))
        return self

    def ttl(self, key: str):
        self.ops.append(("ttl", key))
        return self

    def expire(self, key: str, seconds: int):
        self.ops.append(("expire", key, seconds))
        return self

    def execute(self):
        out = []
        for op in self.ops:
            if op[0] == "incr":
                out.append(self.redis.incr(op[1]))
            elif op[0] == "ttl":
                out.append(self.redis.ttl(op[1]))
            elif op[0] == "expire":
                out.append(self.redis.expire(op[1], op[2]))
        self.ops.clear()
        return out


def test_lockout_after_max_failures(monkeypatch):
    from app.config import get_settings
    from core.login_throttle import LoginThrottle

    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_MAX_FAILURES", "3")
    monkeypatch.setenv("AUTH_FAILURE_WINDOW_SECONDS", "900")
    monkeypatch.setenv("AUTH_LOCKOUT_SECONDS", "1800")
    get_settings.cache_clear()

    fake = FakeRedis()
    throttle = LoginThrottle(redis_client=fake)

    assert throttle.is_locked(username="alice", ip="10.0.0.1") is False
    for _ in range(2):
        d = throttle.record_failure(username="alice", ip="10.0.0.1")
        assert d.just_locked is False
        assert throttle.is_locked(username="alice", ip="10.0.0.1") is False

    d = throttle.record_failure(username="alice", ip="10.0.0.1")
    assert d.just_locked is True
    assert throttle.is_locked(username="alice", ip="10.0.0.1") is True

    # Same username from another IP still locked by username key
    assert throttle.is_locked(username="alice", ip="10.0.0.99") is True

    throttle.clear(username="alice", ip="10.0.0.1")
    assert throttle.is_locked(username="alice", ip="10.0.0.1") is False


def test_clear_on_success_path(monkeypatch):
    from app.config import get_settings
    from core.login_throttle import LoginThrottle

    get_settings.cache_clear()
    monkeypatch.setenv("AUTH_MAX_FAILURES", "5")
    get_settings.cache_clear()

    fake = FakeRedis()
    throttle = LoginThrottle(redis_client=fake)
    throttle.record_failure(username="bob", ip="1.2.3.4")
    throttle.record_failure(username="bob", ip="1.2.3.4")
    throttle.clear(username="bob", ip="1.2.3.4")
    assert fake.exists("auth:fail:user:bob") == 0
    assert fake.exists("auth:fail:ip:1.2.3.4") == 0
