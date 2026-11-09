"""Моделі API відокремлені від внутрішнього криптографічного конверта."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Algorithm = Literal["AES-128-GCM", "AES-256-GCM", "ChaCha20-Poly1305"]
NoteCategory = Literal["general", "academic", "administrative"]


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=4096)
    category: NoteCategory = "general"

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Empty note")
        if len(value.encode("utf-8")) > 4096:
            raise ValueError("Note exceeds 4096 bytes")
        return value


class NoteMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    student_id: UUID
    algorithm: Algorithm
    category: NoteCategory


class NoteRead(NoteMetadata):
    text: str
