from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.config import settings
from app.repositories.student_repository import (
    DuplicateEmailError,
    InMemoryStudentRepository,
    StudentNotFoundError,
    student_repository,
)
from app.schemas.student import StudentCreate, StudentRead, StudentUpdate


router = APIRouter(prefix="/api/v1/students", tags=["students"])

def get_repository() -> InMemoryStudentRepository:
    return student_repository


Repository = Annotated[InMemoryStudentRepository, Depends(get_repository)]


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED,
             responses={409: {"description": "Електронна адреса вже існує"}})
def create_student(payload: StudentCreate, repository: Repository) -> StudentRead:
    """Створити студента із серверним UUID. Клієнт не задає id."""
    try:
        return repository.create(payload)
    except DuplicateEmailError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.get("", response_model=list[StudentRead])
def list_students(
    repository: Repository,
    enrollment_year: Annotated[
        int | None,
        Query(ge=settings.enrollment_year_min, le=settings.enrollment_year_max,
              description="Необов’язковий точний фільтр за роком вступу"),
    ] = None,
) -> list[StudentRead]:
    """Отримати список студентів, за потреби відфільтрований за роком."""
    return repository.list(enrollment_year=enrollment_year)


@router.get("/{student_id}", response_model=StudentRead,
            responses={404: {"description": "Студента не знайдено"}})
def get_student(student_id: UUID, repository: Repository) -> StudentRead:
    """Отримати одного студента за UUID."""
    try:
        return repository.get(student_id)
    except StudentNotFoundError:
        raise HTTPException(status_code=404, detail="Студента не знайдено.") from None


@router.patch("/{student_id}", response_model=StudentRead,
              responses={404: {"description": "Студента не знайдено"},
                         409: {"description": "Електронна адреса вже існує"}})
def update_student(student_id: UUID, payload: StudentUpdate,
                   repository: Repository) -> StudentRead:
    """Змінити лише передані поля; порожнє тіло, null, id та зайві поля — 422."""
    try:
        return repository.update(student_id, payload)
    except StudentNotFoundError:
        raise HTTPException(status_code=404, detail="Студента не знайдено.") from None
    except DuplicateEmailError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
