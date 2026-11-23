from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.staff_user import StaffRole, StaffUser
from app.schemas.staff import StaffCreate, StaffUpdate


class StaffError(Exception):
    """Lỗi nghiệp vụ; tầng API chuyển thành HTTP 4xx."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def authenticate(session: AsyncSession, email: str, password: str) -> StaffUser | None:
    user = await session.scalar(select(StaffUser).where(StaffUser.email == email.strip().lower()))
    # verify_password luôn chạy (kể cả khi không có user) để thời gian phản hồi như nhau
    ok = verify_password(password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        return None
    return user


async def create_staff(session: AsyncSession, data: StaffCreate) -> StaffUser:
    user = StaffUser(
        email=data.email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise StaffError("Email already registered", status_code=409) from None
    await session.refresh(user)
    return user


async def _lock_active_owner_count(session: AsyncSession) -> int:
    # Khóa các dòng owner: hai owner cùng lúc hạ quyền nhau sẽ phải chạy lần lượt,
    # nên không thể cùng lọt qua kiểm tra "còn ít nhất 1 owner".
    owner_ids = await session.scalars(
        select(StaffUser.id)
        .where(StaffUser.role == StaffRole.OWNER, StaffUser.is_active.is_(True))
        .order_by(StaffUser.id)
        .with_for_update()
    )
    return len(owner_ids.all())


async def update_staff(
    session: AsyncSession, actor: StaffUser, user_id: int, data: StaffUpdate
) -> StaffUser:
    user = await session.get(StaffUser, user_id)
    if user is None:
        raise StaffError("Staff user not found", status_code=404)

    changes = data.model_dump(exclude_unset=True)

    def loses_owner() -> bool:
        return (
            user.role == StaffRole.OWNER
            and user.is_active
            and (
                changes.get("role", user.role) != StaffRole.OWNER
                or changes.get("is_active") is False
            )
        )

    if loses_owner():
        if user.id == actor.id:
            raise StaffError("You cannot demote or deactivate yourself")
        active_owners = await _lock_active_owner_count(session)
        await session.refresh(user)  # đọc lại sau khi đã giữ khóa
        if loses_owner() and active_owners <= 1:
            raise StaffError("Shop must keep at least one active owner")

    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    for field, value in changes.items():
        setattr(user, field, value)

    await session.commit()
    await session.refresh(user)
    return user


async def change_password(
    session: AsyncSession, user: StaffUser, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise StaffError("Current password is incorrect")
    user.password_hash = hash_password(new_password)
    await session.commit()
