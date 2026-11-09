"""Сховище конвертів без відкритого тексту й секретних ключів."""

from dataclasses import dataclass
from threading import Lock
from uuid import UUID

from app.schemas.secure_note import NoteCategory


@dataclass(frozen=True)
class EncryptedNote:
    version: int
    student_id: UUID
    note_id: UUID
    algorithm: str
    backend: str
    key_id: UUID
    nonce: bytes
    ciphertext: bytes
    tag: bytes
    category: NoteCategory


class SecureNoteRepository:
    def __init__(self):
        self._items: dict[UUID, EncryptedNote] = {}
        self._lock = Lock()

    def add(self, note: EncryptedNote) -> None:
        with self._lock:
            if note.note_id in self._items:
                raise ValueError("Duplicate note ID")
            self._items[note.note_id] = note

    def get(self, student_id: UUID, note_id: UUID) -> EncryptedNote:
        with self._lock:
            note = self._items[note_id]
            if note.student_id != student_id:
                raise KeyError(note_id)
            return note

    def clear(self) -> None:
        """Очищення записів не скидає послідовність одноразових значень."""
        with self._lock:
            self._items.clear()
