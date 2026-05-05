import base64
import hashlib

from app.core.config import settings


def _key() -> bytes:
    return hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()


def encrypt_text(text: str) -> str:
    if not text:
        return ""
    data = text.encode("utf-8")
    key = _key()
    out = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
    return base64.urlsafe_b64encode(out).decode("ascii")


def decrypt_text(token: str) -> str:
    if not token:
        return ""
    try:
        data = base64.urlsafe_b64decode(token.encode("ascii"))
        key = _key()
        out = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
        return out.decode("utf-8")
    except (UnicodeDecodeError, base64.binascii.Error, ValueError):
        return ""
