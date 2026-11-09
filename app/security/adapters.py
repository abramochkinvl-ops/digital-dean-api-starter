"""Однаковий формат автентифікованого шифрування для двох бібліотек."""

from Crypto.Cipher import AES, ChaCha20_Poly1305
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305

from app.security.profiles import BACKENDS, TAG_BYTES, validate_profile


class CiphertextError(Exception):
    """Повідомлення не пройшло перевірку автентичності."""


def _validate(backend: str, algorithm: str, key: bytes, nonce: bytes) -> None:
    if backend not in BACKENDS:
        raise ValueError("Unsupported backend")
    validate_profile(algorithm, key, nonce)


def _pycryptodome_cipher(algorithm: str, key: bytes, nonce: bytes):
    if algorithm == "ChaCha20-Poly1305":
        return ChaCha20_Poly1305.new(key=key, nonce=nonce)
    return AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_BYTES)


def seal_bytes(
    backend: str, algorithm: str, key: bytes, nonce: bytes, data: bytes, aad: bytes
) -> tuple[bytes, bytes]:
    _validate(backend, algorithm, key, nonce)
    if backend == "cryptography":
        cipher = ChaCha20Poly1305(key) if algorithm == "ChaCha20-Poly1305" else AESGCM(key)
        sealed = cipher.encrypt(nonce, data, aad)
        return sealed[:-TAG_BYTES], sealed[-TAG_BYTES:]

    cipher = _pycryptodome_cipher(algorithm, key, nonce)
    cipher.update(aad)
    return cipher.encrypt_and_digest(data)


def open_bytes(
    backend: str, algorithm: str, key: bytes, nonce: bytes, ct: bytes, tag: bytes, aad: bytes
) -> bytes:
    _validate(backend, algorithm, key, nonce)
    if len(tag) != TAG_BYTES:
        raise CiphertextError("Verification failed")

    try:
        if backend == "cryptography":
            cipher = ChaCha20Poly1305(key) if algorithm == "ChaCha20-Poly1305" else AESGCM(key)
            return cipher.decrypt(nonce, ct + tag, aad)

        cipher = _pycryptodome_cipher(algorithm, key, nonce)
        cipher.update(aad)
        return cipher.decrypt_and_verify(ct, tag)
    except (InvalidTag, ValueError) as error:
        raise CiphertextError("Verification failed") from error
