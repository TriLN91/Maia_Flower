from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_access_token
from app.models.staff_user import StaffRole, StaffUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_staff(
    session: SessionDep, token: Annotated[str, Depends(oauth2_scheme)]
) -> StaffUser:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _CREDENTIALS_ERROR from None

    # Luôn đọc lại từ DB: tài khoản bị khóa hoặc đổi quyền sẽ có hiệu lực ngay,
    # không phải đợi token cũ hết hạn.
    user = await session.get(StaffUser, user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR
    return user


CurrentStaff = Annotated[StaffUser, Depends(get_current_staff)]


async def require_owner(user: CurrentStaff) -> StaffUser:
    if user.role != StaffRole.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Owner permission required")
    return user


CurrentOwner = Annotated[StaffUser, Depends(require_owner)]
