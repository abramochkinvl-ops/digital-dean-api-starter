from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.config import settings


FullName = Annotated[str, Field(min_length=5, max_length=120)]
GroupCode = Annotated[
    str,
    Field(pattern=r"^[A-ZАБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ0-9]+-[0-9]{2}$"),
]
EnrollmentYear = Annotated[
    int,
    Field(
        strict=True,
        ge=settings.enrollment_year_min,
        le=settings.enrollment_year_max,
        description="Рік вступу; межі задає конфігурація закладу.",
    ),
]


class StrictModel(BaseModel):
    """Базова модель, яка не приймає невідомих полів."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StudentCreate(StrictModel):
    full_name: FullName
    email: EmailStr
    group_code: GroupCode
    enrollment_year: EnrollmentYear


class StudentRead(StudentCreate):
    id: UUID


class StudentUpdate(StrictModel):
    """Поля можна пропускати, але явно переданий null не приймається."""

    @staticmethod
    def _schema_without_null_defaults(schema: dict) -> None:
        for field in schema.get("properties", {}).values():
            field.pop("default", None)

    model_config = ConfigDict(json_schema_extra=_schema_without_null_defaults)

    full_name: FullName | SkipJsonSchema[None] = None
    email: EmailStr | SkipJsonSchema[None] = None
    group_code: GroupCode | SkipJsonSchema[None] = None
    enrollment_year: EnrollmentYear | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Потрібно передати хоча б одне дозволене поле.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Явне значення null не дозволене.")
        return self
