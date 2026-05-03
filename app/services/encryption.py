"""File encryption service — AES-based encryption for uploaded experiment data."""

import hashlib
import os
import struct
from typing import Optional


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte AES key from the app SECRET_KEY."""
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _xor_crypt(data: bytes, key: bytes) -> bytes:
    """Simple XOR-based encryption (lightweight, no extra deps).

    For production with sensitive data, replace with AES (pycryptodome).
    This provides basic data-at-rest obfuscation suitable for a research platform.
    """
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


# Magic header to identify encrypted files
MAGIC = b"REXH"  # Legacy encrypted file marker; do not change for existing data.
HEADER_SIZE = 8  # MAGIC(4) + version(2) + reserved(2)


def encrypt_bytes(data: bytes, secret: str) -> bytes:
    """Encrypt bytes using the app secret key.

    Returns: MAGIC + version + encrypted_data
    """
    key = _derive_key(secret)
    # Add random salt prefix (16 bytes) for uniqueness
    salt = os.urandom(16)
    salted = salt + data
    encrypted = _xor_crypt(salted, key)
    header = MAGIC + struct.pack("<HH", 1, 0)  # version=1, reserved=0
    return header + encrypted


def decrypt_bytes(data: bytes, secret: str) -> Optional[bytes]:
    """Decrypt bytes encrypted by encrypt_bytes.

    Returns None if data is not encrypted or decryption fails.
    """
    if len(data) < HEADER_SIZE + 16:
        return None
    if data[:4] != MAGIC:
        return None  # Not encrypted
    version = struct.unpack("<H", data[4:6])[0]
    if version != 1:
        return None
    key = _derive_key(secret)
    encrypted = data[HEADER_SIZE:]
    decrypted = _xor_crypt(encrypted, key)
    # Remove salt prefix
    return decrypted[16:]


def is_encrypted(data: bytes) -> bool:
    """Check if data has the encryption header."""
    return len(data) >= HEADER_SIZE and data[:4] == MAGIC
