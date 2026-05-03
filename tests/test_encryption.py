"""Tests for the file encryption service."""

from app.services.encryption import encrypt_bytes, decrypt_bytes, is_encrypted, MAGIC


class TestEncryption:
    def test_round_trip(self):
        data = b"Hello, this is secret experiment data!"
        secret = "my-secret-key"
        enc = encrypt_bytes(data, secret)
        assert is_encrypted(enc)
        dec = decrypt_bytes(enc, secret)
        assert dec == data

    def test_different_secrets(self):
        data = b"test data"
        enc = encrypt_bytes(data, "key1")
        dec = decrypt_bytes(enc, "key2")
        assert dec != data  # Wrong key produces garbage

    def test_not_encrypted(self):
        raw = b"plain text data"
        assert not is_encrypted(raw)
        assert decrypt_bytes(raw, "key") is None

    def test_header(self):
        enc = encrypt_bytes(b"data", "key")
        assert enc[:4] == MAGIC

    def test_empty_data(self):
        enc = encrypt_bytes(b"", "key")
        dec = decrypt_bytes(enc, "key")
        assert dec == b""

    def test_binary_data(self):
        data = bytes(range(256)) * 10
        enc = encrypt_bytes(data, "binary-key")
        dec = decrypt_bytes(enc, "binary-key")
        assert dec == data
