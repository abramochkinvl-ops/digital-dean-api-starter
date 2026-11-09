"""Моделі та HTTP-контракт; усі записи вигадані."""

from dataclasses import asdict, replace
from itertools import product
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import crypto_lab
from app.api.secure_notes import decrypt_note
from app.main import app
from app.security.adapters import CiphertextError, seal_bytes
from app.security.context import note_aad
from app.security.keys import create_process_key
from app.security.profiles import BACKENDS, KEY_BYTES
from app.schemas.secure_note import NoteCreate


@pytest.mark.parametrize("text", ("x" * 4096, "я" * 2048, "  текст  "))
def test_accepted_text_is_preserved(text):
    assert NoteCreate(text=text).text == text


@pytest.mark.parametrize("payload", (
    {"text": ""}, {"text": " "}, {"text": "x" * 4097},
    {"text": "я" * 2049}, {"text": 42},
    {"text": "demo", "key": "do-not-accept"},
))
def test_invalid_note_input(payload):
    with pytest.raises(ValidationError):
        NoteCreate(**payload)


def test_unknown_student_is_not_found():
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/students/{uuid4()}/secure-notes/{uuid4()}"
        )
    assert response.status_code == 404


@pytest.fixture
def student_id(client, student_data):
    response = client.post("/api/v1/students", json=student_data)
    assert response.status_code == 201
    return UUID(response.json()["id"])


def notes_path(student_id):
    return f"/api/v1/students/{student_id}/secure-notes"


def create_note(client, student_id, payload):
    response = client.post(notes_path(student_id), json=payload)
    assert response.status_code == 201
    return UUID(response.json()["id"]), response.json()


def test_note_api_and_internal_storage(client, student_id):
    text = "  Навчальна примітка  "
    note_id, metadata = create_note(client, student_id, {"text": text, "category": "academic"})
    assert metadata == {
        "id": str(note_id), "student_id": str(student_id),
        "algorithm": "AES-256-GCM", "category": "academic",
    }
    response = client.get(f"{notes_path(student_id)}/{note_id}")
    assert response.status_code == 200
    assert response.json() == {**metadata, "text": text}

    note = app.state.secure_notes.get(student_id, note_id)
    assert not {"text", "key"} & asdict(note).keys()
    assert note.key_id == app.state.process_key.key_id
    assert len(note.nonce) == 12 and len(note.tag) == 16
    assert len(note.ciphertext) == len(text.encode("utf-8"))
    assert note.ciphertext != text.encode("utf-8")


@pytest.mark.parametrize("field", ("ciphertext", "tag", "nonce", "version", "key_id", "backend", "algorithm"))
def test_damaged_note_is_rejected_without_plaintext(client, student_id, field):
    note_id, _ = create_note(client, student_id, {"text": "Синтетичний текст"})
    repository = app.state.secure_notes
    original = repository.get(student_id, note_id)
    value = getattr(original, field)
    if isinstance(value, bytes):
        changed = bytes([value[0] ^ 1]) + value[1:]
    else:
        changed = {
            "version": 2, "key_id": uuid4(),
            "backend": "pycryptodome", "algorithm": "ChaCha20-Poly1305",
        }[field]
    repository._items[note_id] = replace(original, **{field: changed})

    response = client.get(f"{notes_path(student_id)}/{note_id}")
    assert response.status_code == 500
    assert response.json() == {"detail": "Protected note unavailable"}


def test_undecodable_authenticated_note_is_rejected(client, student_id):
    note_id, _ = create_note(client, student_id, {"text": "demo"})
    repository, key = app.state.secure_notes, app.state.process_key
    original = repository.get(student_id, note_id)
    nonce = key.nonces.next()
    aad = note_aad(student_id, note_id, original.algorithm, key.key_id, original.category)
    ct, tag = seal_bytes(original.backend, original.algorithm, key.key, nonce, b"\xff", aad)
    repository._items[note_id] = replace(original, nonce=nonce, ciphertext=ct, tag=tag)
    response = client.get(f"{notes_path(student_id)}/{note_id}")
    assert response.status_code == 500
    assert response.json() == {"detail": "Protected note unavailable"}


def test_nonce_limit_rejects_only_new_writes(client, student_id):
    app.state.process_key = create_process_key(limit=2)
    first_id, _ = create_note(client, student_id, {"text": "first"})
    second_id, _ = create_note(client, student_id, {"text": "second"})
    repository = app.state.secure_notes
    assert repository.get(student_id, first_id).nonce != repository.get(student_id, second_id).nonce

    response = client.post(notes_path(student_id), json={"text": "third"})
    assert response.status_code == 503
    assert response.json() == {"detail": "Protected note unavailable"}
    response = client.get(f"{notes_path(student_id)}/{first_id}")
    assert response.status_code == 200 and response.json()["text"] == "first"


def test_clearing_notes_does_not_reset_nonce(client, student_id):
    first_id, _ = create_note(client, student_id, {"text": "first"})
    repository = app.state.secure_notes
    nonce = repository.get(student_id, first_id).nonce
    repository.clear()
    second_id, _ = create_note(client, student_id, {"text": "second"})
    assert repository.get(student_id, second_id).nonce != nonce


@pytest.mark.parametrize("text", ("x" * 4096, "я" * 2048))
def test_note_byte_limit_accepted_by_api(client, student_id, text):
    note_id, _ = create_note(client, student_id, {"text": text})
    assert client.get(f"{notes_path(student_id)}/{note_id}").json()["text"] == text


@pytest.mark.parametrize("payload", (
    {"text": "x" * 4097}, {"text": "я" * 2049}, {"text": " "},
    {"text": "demo", "key": "rejected"}, {"text": "demo", "category": "unknown"},
))
def test_invalid_note_api_has_no_writes(client, student_id, payload):
    assert client.post(notes_path(student_id), json=payload).status_code == 422
    assert not app.state.secure_notes._items


def test_invalid_uuid_is_rejected(client, student_id):
    assert client.get(f"{notes_path(student_id)}/invalid").status_code == 422
    assert client.post(notes_path("invalid"), json={"text": "demo"}).status_code == 422


def test_unknown_student_cannot_receive_note(client):
    assert client.post(notes_path(uuid4()), json={"text": "demo"}).status_code == 404


def test_category_tampering_is_detected(client, student_id):
    note_id, _ = create_note(client, student_id, {"text": "demo", "category": "academic"})
    repository = app.state.secure_notes
    original = repository.get(student_id, note_id)
    repository._items[note_id] = replace(original, category="administrative")
    response = client.get(f"{notes_path(student_id)}/{note_id}")
    assert response.status_code == 500
    assert response.json() == {"detail": "Protected note unavailable"}


def test_wrong_student_and_forged_binding(client, student_id, student_data):
    other = client.post("/api/v1/students", json={**student_data, "email": "other@example.com"})
    assert other.status_code == 201
    other_id = UUID(other.json()["id"])
    note_id, _ = create_note(client, student_id, {"text": "demo"})
    url = f"{notes_path(other_id)}/{note_id}"
    assert client.get(url).status_code == 404

    repository = app.state.secure_notes
    original = repository.get(student_id, note_id)
    forged = replace(original, student_id=other_id)
    with pytest.raises(CiphertextError):
        decrypt_note(forged, other_id, note_id, app.state.process_key)
    repository._items[note_id] = forged
    response = client.get(url)
    assert response.status_code == 500
    assert response.json() == {"detail": "Protected note unavailable"}


@pytest.fixture
def sample_report():
    rows = [
        {"backend": backend, "algorithm": algorithm, "size_bytes": size, "operation": op,
         "series_mean_ns": [100.0] * 5, "median_ns": 100.0, "iqr_ns": 0.0,
         "throughput_mib_s": size * 1e9 / (2**20 * 100)}
        for backend, algorithm, size, op in product(
            BACKENDS, KEY_BYTES, (1024, 65536, 1048576), ("encrypt", "decrypt")
        )
    ]
    return {
        "schema_version": 1, "run_id": "test",
        "measured_at_utc": "2026-01-01T00:00:00+00:00", "code_commit": "a" * 40,
        "environment": {
            "cpu": "test", "os": "test", "architecture": "test", "python": "test",
            "cryptography": "test", "pycryptodome": "test", "openssl": "test",
            "aes_cpu_flag": None, "timer_resolution_ns": 1.0,
        },
        "parameters": {
            "sizes_bytes": [1024, 65536, 1048576], "warmup": 10, "series": 5,
            "operations_per_series": 100, "aad_bytes": 64,
            "includes_cipher_setup": True, "shuffle_seed": 2026,
        },
        "results": rows,
    }


def test_benchmark_report_reader(client, monkeypatch, tmp_path, sample_report):
    report = tmp_path / "report.json"
    monkeypatch.setattr(crypto_lab, "REPORT_PATH", report)
    url = "/api/v1/lab/crypto/benchmark-results"
    assert client.get(url).status_code == 404

    report.write_text(json.dumps(sample_report), encoding="utf-8")
    response = client.get(url, params={"path": "ignored.json"})
    assert response.status_code == 200 and response.json() == sample_report

    for bad in ("{", json.dumps({**sample_report, "results": [sample_report["results"][0]] * 36})):
        report.write_text(bad, encoding="utf-8")
        response = client.get(url)
        assert response.status_code == 500
        assert response.json() == {"detail": "Benchmark results unavailable"}
