from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models.staff_user import StaffRole

NormalizedEmail = Annotated[EmailStr, AfterValidator(lambda v: v.strip().lower())]
Password = Annotated[str, Field(min_length=8, max_length=128)]
FullName = Annotated[str, Field(min_length=1, max_length=120)]


class StaffCreate(BaseModel):
    email: NormalizedEmail
    full_name: FullName
    password: Password
    role: StaffRole = StaffRole.STAFF


class StaffUpdate(BaseModel):
    full_name: FullName | None = None
    role: StaffRole | None = None
    is_active: bool | None = None
    password: Password | None = None


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: StaffRole
    is_active: bool
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - loại token OAuth2, không phải mật khẩu
    expires_in: int


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: Password
