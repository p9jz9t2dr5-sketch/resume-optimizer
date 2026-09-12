"""Login failure throttling.

Slows down brute force / credential stuffing without locking an account for
good: failures are counted per (client IP, email) inside a fixed window and the
counter is cleared by the next successful login. Keying on the pair (rather than
the email alone) keeps an attacker from locking a victim out of their own
account.

Redis is used when configured so every worker shares the same state; otherwise
an in-process dict is used, which is fine for local development and tests but
per-worker by nature.
"""

import time

import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60


class LoginThrottle:
    def __init__(self) -> None:
        self.redis: redis.Redis | None = None
        self._memory: dict[str, tuple[int, float]] = {}

    async def connect(self) -> None:
        if not settings.REDIS_URL:
            return
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def disconnect(self) -> None:
        if self.redis:
            try:
                await self.redis.close()
            except Exception:
                pass
            self.redis = None

    @staticmethod
    def _key(identifier: str) -> str:
        return f"login:fail:{identifier}"

    async def is_blocked(self, identifier: str) -> bool:
        return await self._count(identifier) >= MAX_FAILURES

    async def register_failure(self, identifier: str) -> int:
        """Count one failed attempt and return the running total for the window."""
        if self.redis:
            try:
                key = self._key(identifier)
                count = await self.redis.incr(key)
                if count == 1:
                    await self.redis.expire(key, WINDOW_SECONDS)
                return int(count)
            except Exception:
                # A Redis hiccup must never block logins; fall through to memory.
                pass

        now = time.monotonic()
        count, expires = self._memory.get(identifier, (0, now + WINDOW_SECONDS))
        if now > expires:
            count, expires = 0, now + WINDOW_SECONDS
        count += 1
        self._memory[identifier] = (count, expires)
        return count

    async def clear(self, identifier: str) -> None:
        self._memory.pop(identifier, None)
        if self.redis:
            try:
                await self.redis.delete(self._key(identifier))
            except Exception:
                pass

    async def _count(self, identifier: str) -> int:
        if self.redis:
            try:
                value = await self.redis.get(self._key(identifier))
                return int(value) if value else 0
            except Exception:
                pass

        count, expires = self._memory.get(identifier, (0, 0.0))
        if time.monotonic() > expires:
            self._memory.pop(identifier, None)
            return 0
        return count

    def reset_all(self) -> None:
        """Test helper: drop every in-process counter."""
        self._memory.clear()


login_throttle = LoginThrottle()
