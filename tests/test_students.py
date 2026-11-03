import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest

from app.config import settings
from app.repositories.student_repository import DuplicateEmailError
from app.schemas.student import StudentCreate


URL = "/api/v1/students"


def create(client, data):
    response = client.post(URL, json=data)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_server_uuid_and_normalized_strings(client, student_data):
    response = create(client, student_data | {"full_name": "  Олена Коваль  "})
    assert UUID(response["id"]).version == 4
    assert {key: value for key, value in response.items() if key != "id"} == student_data


def test_empty_list_starts_clean(client):
    assert client.get(URL).json() == []


def test_list_has_exactly_created_students(client, student_data):
    first = create(client, student_data)
    second = create(client, student_data | {"email": "second@example.com"})
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json() == [first, second]


def test_get_existing(client, student_data):
    student = create(client, student_data)
    response = client.get(f"{URL}/{student['id']}")
    assert response.status_code == 200
    assert response.json() == student


@pytest.mark.parametrize("method", ["get", "patch"])
def test_missing_uuid_returns_controlled_404(client, method):
    path = f"{URL}/{uuid4()}"
    response = getattr(client, method)(path, **({"json": {"group_code": "КН-32"}} if method == "patch" else {}))
    assert response.status_code == 404
    assert response.json() == {"detail": "Студента не знайдено."}
    assert "Traceback" not in response.text


@pytest.mark.parametrize("method", ["get", "patch"])
def test_invalid_path_uuid_returns_422(client, method):
    response = getattr(client, method)(f"{URL}/not-a-uuid", **({"json": {"group_code": "КН-32"}} if method == "patch" else {}))
    assert response.status_code == 422


@pytest.mark.parametrize("field,value", [
    ("email", "not-an-email"), ("full_name", "  Іра  "),
    ("full_name", "a" * 121), ("group_code", "кн-31"),
    ("group_code", "КН-3"), ("group_code", "КН-311"),
    ("group_code", "KN_31"), ("group_code", "Ы-31"),
])
def test_invalid_create_does_not_change_state(client, student_data, field, value):
    response = client.post(URL, json=student_data | {field: value})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert client.get(URL).json() == []


@pytest.mark.parametrize("name", ["a" * 5, "a" * 120])
def test_name_boundaries_accepted(client, student_data, name):
    assert create(client, student_data | {"full_name": name})["full_name"] == name


def test_duplicate_email_is_case_insensitive(client, student_data):
    first = create(client, student_data)
    response = client.post(URL, json=student_data | {"email": student_data["email"].upper()})
    assert response.status_code == 409
    assert response.json() == {"detail": "Електронна адреса вже використовується."}
    assert client.get(URL).json() == [first]


def test_patch_only_changes_supplied_field(client, student_data):
    before = create(client, student_data)
    response = client.patch(f"{URL}/{before['id']}", json={"group_code": "КН-32"})
    assert response.status_code == 200
    assert response.json() == before | {"group_code": "КН-32"}
    assert client.get(f"{URL}/{before['id']}").json() == response.json()


@pytest.mark.parametrize("payload", [{}, {"is_admin": True}, {"id": str(uuid4())},
    {"full_name": None}, {"email": None}, {"group_code": None}, {"enrollment_year": None},
    {"group_code": "КН-32", "is_admin": True}])
def test_invalid_patch_is_atomic(client, student_data, payload):
    before = create(client, student_data)
    response = client.patch(f"{URL}/{before['id']}", json=payload)
    assert response.status_code == 422
    assert client.get(f"{URL}/{before['id']}").json() == before


@pytest.mark.parametrize("extra", [{"id": str(uuid4())}, {"is_admin": True}])
def test_create_rejects_server_or_unknown_fields(client, student_data, extra):
    assert client.post(URL, json=student_data | extra).status_code == 422
    assert client.get(URL).json() == []


def test_patch_duplicate_email_preserves_every_field(client, student_data):
    create(client, student_data)
    second = create(client, student_data | {"email": "second@example.com"})
    response = client.patch(f"{URL}/{second['id']}", json={"email": student_data["email"].upper(), "group_code": "КН-32"})
    assert response.status_code == 409
    assert client.get(f"{URL}/{second['id']}").json() == second


def test_patch_same_email_ignores_current_record(client, student_data):
    student = create(client, student_data)
    response = client.patch(f"{URL}/{student['id']}", json={"email": student_data["email"]})
    assert response.status_code == 200
    assert response.json() == student


def test_malformed_json_rejected_without_creating_student(client):
    response = client.post(URL, content='{"full_name":', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "json_invalid"
    assert client.get(URL).json() == []


@pytest.mark.parametrize("year", [settings.enrollment_year_min, settings.enrollment_year_max])
def test_enrollment_year_boundaries_accepted(client, student_data, year):
    assert create(client, student_data | {"enrollment_year": year})["enrollment_year"] == year


@pytest.mark.parametrize("year", [settings.enrollment_year_min - 1, settings.enrollment_year_max + 1, True, 2026.5, "2026"])
def test_invalid_enrollment_year_rejected_in_create_and_patch(client, student_data, year):
    assert client.post(URL, json=student_data | {"enrollment_year": year}).status_code == 422
    before = create(client, student_data)
    assert client.patch(f"{URL}/{before['id']}", json={"enrollment_year": year}).status_code == 422
    assert client.get(f"{URL}/{before['id']}").json() == before


def test_year_filter_uses_actual_value(client, student_data):
    first = create(client, student_data)
    if settings.enrollment_year_min != settings.enrollment_year_max:
        create(client, student_data | {"email": "other@example.com", "enrollment_year": settings.enrollment_year_max})
    response = client.get(URL, params={"enrollment_year": settings.enrollment_year_min})
    assert response.status_code == 200
    assert response.json() == [first]


def test_filter_tracks_updated_year(client, student_data):
    first = create(client, student_data)
    new_year = settings.enrollment_year_max
    patched = client.patch(f"{URL}/{first['id']}", json={"enrollment_year": new_year})
    assert patched.status_code == 200
    assert client.get(URL, params={"enrollment_year": new_year}).json() == [patched.json()]


@pytest.mark.parametrize("year", [settings.enrollment_year_min - 1, settings.enrollment_year_max + 1, "abc"])
def test_invalid_year_filter_returns_422(client, year):
    assert client.get(URL, params={"enrollment_year": year}).status_code == 422


def test_configurable_bounds_and_openapi_in_fresh_process():
    code = '''
from fastapi.testclient import TestClient
from app.main import app
c=TestClient(app)
p={"full_name":"Олена Коваль","email":"configured@example.com","group_code":"КН-31","enrollment_year":2010}
assert c.post('/api/v1/students',json=p).status_code==201
assert c.post('/api/v1/students',json=p|{"email":"outside@example.com","enrollment_year":2009}).status_code==422
assert c.get('/api/v1/students',params={"enrollment_year":2013}).status_code==422
s=app.openapi()['components']['schemas']['StudentCreate']['properties']['enrollment_year']
assert s['minimum']==2010 and s['maximum']==2012
'''
    result = subprocess.run([sys.executable, "-c", code], env=os.environ | {"ENROLLMENT_YEAR_MIN": "2010", "ENROLLMENT_YEAR_MAX": "2012"}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_invalid_configuration_fails_at_startup():
    result = subprocess.run([sys.executable, "-c", "import app.config"], env=os.environ | {"ENROLLMENT_YEAR_MIN": "2030", "ENROLLMENT_YEAR_MAX": "2000"}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Мінімальний рік вступу" in result.stderr


def test_repository_does_not_leak_mutable_models(repository, student_data):
    first = repository.create(StudentCreate(**student_data))
    first.full_name = "Changed externally"
    listed = repository.list()
    listed[0].full_name = "Another outside change"
    assert repository.get(first.id).full_name == student_data["full_name"]


def test_concurrent_duplicate_creates_are_atomic(repository, student_data):
    payload = StudentCreate(**student_data)
    def attempt(_):
        try:
            repository.create(payload)
            return "created"
        except DuplicateEmailError:
            return "duplicate"
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(attempt, range(8)))
    assert results.count("created") == 1
    assert results.count("duplicate") == 7


def test_openapi_contains_variant_and_contract(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    for model in ["StudentCreate", "StudentRead", "StudentUpdate"]:
        assert "enrollment_year" in schema["components"]["schemas"][model]["properties"]
    assert "id" not in schema["components"]["schemas"]["StudentCreate"]["properties"]
    assert schema["components"]["schemas"]["StudentCreate"]["additionalProperties"] is False
    assert schema["paths"][URL]["get"]["parameters"][0]["name"] == "enrollment_year"
    patch_props = schema["components"]["schemas"]["StudentUpdate"]["properties"]
    assert patch_props["email"]["type"] == "string"
    assert "default" not in patch_props["email"]
    assert "409" in schema["paths"][URL]["post"]["responses"]
    assert client.get("/docs").status_code == 200
