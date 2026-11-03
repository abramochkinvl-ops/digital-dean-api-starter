import pytest
from fastapi.testclient import TestClient

from app.api.students import get_repository
from app.main import app
from app.repositories.student_repository import InMemoryStudentRepository


@pytest.fixture(autouse=True)
def repository():
    """Кожний тест отримує незалежне порожнє сховище."""
    instance = InMemoryStudentRepository()
    instance.clear()
    app.dependency_overrides[get_repository] = lambda: instance
    yield instance
    app.dependency_overrides.clear()
    instance.clear()


@pytest.fixture
def client(repository):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def student_data():
    from app.config import settings

    return {
        "full_name": "Олена Коваль",
        "email": "olena.koval@example.com",
        "group_code": "КН-31",
        "enrollment_year": settings.enrollment_year_min,
    }
