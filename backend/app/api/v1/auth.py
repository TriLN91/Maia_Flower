from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentStaff, SessionDep
from app.core.security import create_access_token
from app.schemas.staff import ChangePasswordIn, StaffOut, TokenOut
from app.services import staff as staff_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(
    session: SessionDep, form: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> TokenOut:
    """Đăng nhập cho thợ bó / chủ shop. `username` là email (chuẩn OAuth2 để nút Authorize
    của Swagger dùng được)."""
    user = await staff_service.authenticate(session, form.username, form.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token(subject=str(user.id), role=user.role.value)
    return TokenOut(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=StaffOut)
async def me(user: CurrentStaff) -> StaffOut:
    return StaffOut.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(session: SessionDep, user: CurrentStaff, body: ChangePasswordIn) -> None:
    try:
        await staff_service.change_password(session, user, body.current_password, body.new_password)
    except staff_service.StaffError as e:
        raise HTTPException(e.status_code, detail=e.message) from None
