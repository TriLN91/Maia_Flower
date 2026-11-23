from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, HttpUrl

# Tiền luôn là số nguyên đồng VNĐ (không dùng float để tránh sai số làm tròn)
Money = Annotated[int, Field(ge=0, le=1_000_000_000, description="Số tiền (VNĐ)")]
PositiveMoney = Annotated[int, Field(gt=0, le=1_000_000_000, description="Số tiền (VNĐ)")]

# Chuỗi tên: tự cắt khoảng trắng hai đầu và gộp khoảng trắng thừa ở giữa
Name = Annotated[
    str,
    AfterValidator(lambda v: " ".join(v.split())),
    Field(min_length=1, max_length=120),
]

ImageUrl = Annotated[HttpUrl, AfterValidator(str)]


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
