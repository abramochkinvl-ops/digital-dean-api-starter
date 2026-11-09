"""Запис і читання захищених службових приміток."""

from typing import Annotated, get_args
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.students import Repository
from app.repositories.secure_note_repository import EncryptedNote, SecureNoteRepository
from app.repositories.student_repository import StudentNotFoundError
from app.schemas.secure_note import NoteCategory, NoteCreate, NoteMetadata, NoteRead
from app.security.adapters import CiphertextError, open_bytes, seal_bytes
from app.security.context import ENVELOPE_VERSION, note_aad
from app.security.keys import ProcessKey
from app.security.profiles import NONCE_BYTES, TAG_BYTES


router = APIRouter(prefix="/api/v1/students", tags=["secure-notes"])
ALGORITHM = "AES-256-GCM"
BACKEND = "cryptography"
UNAVAILABLE = "Protected note unavailable"


def get_process_key(request: Request) -> ProcessKey:
    return request.app.state.process_key


def get_note_repository(request: Request) -> SecureNoteRepository:
    return request.app.state.secure_notes


Key = Annotated[ProcessKey, Depends(get_process_key)]
Notes = Annotated[SecureNoteRepository, Depends(get_note_repository)]


def _require_student(student_id: UUID, students: Repository) -> None:
    try:
        students.get(student_id)
    except StudentNotFoundError:
        raise HTTPException(404, "Студента не знайдено.") from None


def decrypt_note(note: EncryptedNote, student_id: UUID, note_id: UUID, key: ProcessKey) -> str:
    if (
        type(note.version) is not int
        or note.version != ENVELOPE_VERSION
        or note.student_id != student_id
        or note.note_id != note_id
        or note.algorithm != ALGORITHM
        or note.backend != BACKEND
        or note.category not in get_args(NoteCategory)
        or note.key_id != key.key_id
        or not isinstance(note.nonce, bytes)
        or len(note.nonce) != NONCE_BYTES
        or not isinstance(note.tag, bytes)
        or len(note.tag) != TAG_BYTES
        or not isinstance(note.ciphertext, bytes)
        or not 1 <= len(note.ciphertext) <= 4096
    ):
        raise CiphertextError("Invalid note envelope")

    context = note_aad(student_id, note_id, note.algorithm, key.key_id, note.category)
    return open_bytes(
        note.backend, note.algorithm, key.key, note.nonce, note.ciphertext, note.tag, context
    ).decode("utf-8")


@router.post(
    "/{student_id}/secure-notes", status_code=201, response_model=NoteMetadata,
    responses={
        404: {"description": "Студента не знайдено"},
        503: {"description": UNAVAILABLE},
    },
)
def create_note(
    student_id: UUID, payload: NoteCreate, students: Repository, notes: Notes, key: Key
) -> NoteMetadata:
    """Зберегти зашифровану примітку й повернути її метадані."""
    _require_student(student_id, students)
    note_id = uuid4()
    try:
        nonce = key.nonces.next()
    except RuntimeError:
        raise HTTPException(503, UNAVAILABLE) from None

    context = note_aad(student_id, note_id, ALGORITHM, key.key_id, payload.category)
    ciphertext, tag = seal_bytes(
        BACKEND, ALGORITHM, key.key, nonce, payload.text.encode("utf-8"), context
    )
    notes.add(EncryptedNote(
        version=ENVELOPE_VERSION, student_id=student_id, note_id=note_id,
        algorithm=ALGORITHM, backend=BACKEND, key_id=key.key_id,
        nonce=nonce, ciphertext=ciphertext, tag=tag, category=payload.category,
    ))
    return NoteMetadata(id=note_id, student_id=student_id, algorithm=ALGORITHM, category=payload.category)


@router.get(
    "/{student_id}/secure-notes/{note_id}", response_model=NoteRead,
    responses={
        404: {"description": "Студента або примітку не знайдено"},
        500: {"description": UNAVAILABLE},
    },
)
def read_note(student_id: UUID, note_id: UUID, students: Repository, notes: Notes, key: Key) -> NoteRead:
    """Видати текст після перевірки конверта та асоційованих даних."""
    _require_student(student_id, students)
    try:
        note = notes.get(student_id, note_id)
    except KeyError:
        raise HTTPException(404, "Примітку не знайдено.") from None

    try:
        text = decrypt_note(note, student_id, note_id, key)
    except (CiphertextError, UnicodeError):
        raise HTTPException(500, UNAVAILABLE) from None
    return NoteRead(id=note_id, student_id=student_id, algorithm=ALGORITHM, category=note.category, text=text)
