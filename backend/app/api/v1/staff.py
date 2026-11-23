from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentOwner, SessionDep
from app.models.staff_user import StaffUser
from app.schemas.staff import StaffCreate, StaffOut, StaffUpdate
from app.services import staff as staff_service

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("", response_model=list[StaffOut])
async def list_staff(session: SessionDep, _: CurrentOwner) -> list[StaffUser]:
    result = await session.scalars(select(StaffUser).order_by(StaffUser.id))
    return list(result.all())


@router.post("", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def create_staff(session: SessionDep, _: CurrentOwner, body: StaffCreate) -> StaffUser:
    try:
        return await staff_service.create_staff(session, body)
    except staff_service.StaffError as e:
        raise HTTPException(e.status_code, detail=e.message) from None


@router.patch("/{user_id}", response_model=StaffOut)
async def update_staff(
    session: SessionDep, owner: CurrentOwner, user_id: int, body: StaffUpdate
) -> StaffUser:
    try:
        return await staff_service.update_staff(session, owner, user_id, body)
    except staff_service.StaffError as e:
        raise HTTPException(e.status_code, detail=e.message) from None
