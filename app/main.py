from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.crypto_lab import router as crypto_lab_router
from app.api.secure_notes import router as secure_notes_router
from app.repositories.secure_note_repository import SecureNoteRepository
from app.security.keys import create_process_key
from app.api.students import router as students_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.process_key = create_process_key()
    app.state.secure_notes = SecureNoteRepository()
    try:
        yield
    finally:
        del app.state.secure_notes
        del app.state.process_key


app = FastAPI(
    lifespan=lifespan,
    title="Digital Dean API",
    version="0.2.0",
    description="Навчальний API системи «Цифровий деканат»",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Повертає ознаку готовності навчального застосунку."""
    return {"status": "ok"}


app.include_router(students_router)
app.include_router(secure_notes_router)
app.include_router(crypto_lab_router)
