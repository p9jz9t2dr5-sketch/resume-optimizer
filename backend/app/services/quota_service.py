"""Free-tier daily message quota.

The counter is what actually stops a free account from hammering the paid model,
so it must not silently disappear: when Redis is configured the count is shared
by every worker, otherwise it falls back to an in-process dict (fine for local
development and tests, per-worker by nature).

The reservation is taken *before* the model call and released again when the
stream fails, which keeps two guarantees: concurrent requests cannot slip past
the limit together, and a request that never produced an answer does not burn
one of the free messages.
"""

from datetime import date

import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()


class QuotaService:
    def __init__(self):
        self.redis: redis.Redis | None = None
        # Fallback counters keyed by the same daily key, used when Redis is absent.
        self._memory: dict[str, int] = {}

    async def connect(self):
        if not settings.REDIS_URL:
            return
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def disconnect(self):
        if self.redis:
            try:
                await self.redis.close()
            except Exception:
                pass
            self.redis = None

    def _daily_key(self, user_id: str) -> str:
        today = date.today().isoformat()
        return f"quota:daily:{user_id}:{today}"

    async def get_daily_count(self, user_id: str) -> int:
        if not self.redis:
            return self._memory.get(self._daily_key(user_id), 0)
        try:
            count = await self.redis.get(self._daily_key(user_id))
            return int(count) if count else 0
        except Exception:
            # Redis unavailable mid-flight — fall back to the in-process counter
            # rather than pretending the user has sent nothing.
            return self._memory.get(self._daily_key(user_id), 0)

    async def increment_daily(self, user_id: str) -> int:
        if not self.redis:
            return self._increment_memory(user_id)
        try:
            key = self._daily_key(user_id)
            count = await self.redis.incr(key)
            await self.redis.expire(key, 86400)  # 24h TTL
            return count
        except Exception:
            return self._increment_memory(user_id)

    async def release_message(self, user_id: str) -> None:
        """Give back a reserved message (used when the model call failed)."""
        key = self._daily_key(user_id)
        if self._memory.get(key):
            self._memory[key] = max(0, self._memory[key] - 1)
        if self.redis:
            try:
                count = await self.redis.decr(key)
                if count < 0:  # never leave a negative counter behind
                    await self.redis.set(key, 0)
            except Exception:
                pass

    async def clear_daily(self, user_id: str) -> None:
        """Drop the day's counter for a user (used when an account is deleted)."""
        self._memory.pop(self._daily_key(user_id), None)
        if self.redis:
            try:
                await self.redis.delete(self._daily_key(user_id))
            except Exception:
                pass

    async def consume_message(self, user_id: str, is_premium: bool) -> bool:
        """Reserve one message. Returns False when the free quota is exhausted."""
        count = await self.increment_daily(user_id)
        if is_premium:
            return True
        return count <= settings.FREE_DAILY_MESSAGE_LIMIT

    def _increment_memory(self, user_id: str) -> int:
        key = self._daily_key(user_id)
        self._memory[key] = self._memory.get(key, 0) + 1
        return self._memory[key]

    async def can_send_message(self, user_id: str, is_premium: bool) -> bool:
        if is_premium:
            return True
        count = await self.get_daily_count(user_id)
        return count < settings.FREE_DAILY_MESSAGE_LIMIT

    async def remaining_messages(self, user_id: str, is_premium: bool) -> int:
        if is_premium:
            return 999999  # effectively unlimited
        count = await self.get_daily_count(user_id)
        return max(0, settings.FREE_DAILY_MESSAGE_LIMIT - count)

    def reset_all(self) -> None:
        """Test helper: drop every in-process counter."""
        self._memory.clear()


quota_service = QuotaService()
