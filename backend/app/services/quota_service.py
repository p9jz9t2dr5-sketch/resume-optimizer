from datetime import date
import redis.asyncio as redis

from app.config import get_settings

settings = get_settings()


class QuotaService:
    def __init__(self):
        self.redis: redis.Redis | None = None

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
            return 0
        try:
            count = await self.redis.get(self._daily_key(user_id))
            return int(count) if count else 0
        except Exception:
            # Redis unavailable — degrade gracefully (treat as 0)
            return 0

    async def increment_daily(self, user_id: str) -> int:
        if not self.redis:
            return 0
        try:
            key = self._daily_key(user_id)
            count = await self.redis.incr(key)
            await self.redis.expire(key, 86400)  # 24h TTL
            return count
        except Exception:
            return 0

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


quota_service = QuotaService()
