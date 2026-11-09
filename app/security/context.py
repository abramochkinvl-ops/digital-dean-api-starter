"""Асоційовані дані пов’язують повідомлення з очікуваним ресурсом."""

import json
from uuid import UUID


ENVELOPE_VERSION = 1


def note_aad(
    student_id: UUID, note_id: UUID, algorithm: str, key_id: UUID, category: str
) -> bytes:
    """Серіалізувати контекст однаково під час запису й читання."""
    context = {
        "version": ENVELOPE_VERSION,
        "student_id": str(student_id),
        "note_id": str(note_id),
        "algorithm": algorithm,
        "key_id": str(key_id),
        "category": category,
    }
    return json.dumps(context, sort_keys=True, separators=(",", ":")).encode("utf-8")
