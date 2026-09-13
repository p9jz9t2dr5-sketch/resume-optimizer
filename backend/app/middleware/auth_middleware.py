"""JWT 鉴权依赖。

从 Authorization: Bearer <token> 解析出用户；在需要登录的接口签名里写
`current_user: User = Depends(get_current_user)` 即可拿到当前用户。
token 缺失/过期/伪造统一返回 401。
"""

import logging
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db
from app.models.user import User

logger = logging.getLogger("uvicorn")
security = HTTPBearer()
settings = get_settings()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError as e:
        logger.error("auth: token decode failed, token_head=%s... => %s", token[:24], e)
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        logger.error("auth: user not found for sub=%s (token_head=%s...)", user_id, token[:24])
        raise credentials_exception
    return user
