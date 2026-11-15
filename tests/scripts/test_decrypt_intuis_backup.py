"""Synthetic Android backups: passwords, checksum validation and bounded extraction."""

import io
from pathlib import Path
import runpy
import tarfile
import zlib

import pytest
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import hashlib

script = runpy.run_path(str(Path(__file__).parents[2] / "scripts/decrypt_intuis_backup.py"))
CONFIG_PATH = script["CONFIG_PATH"]


def archive(kind=tarfile.REGTYPE, name=CONFIG_PATH):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tf:
        info = tarfile.TarInfo(name)
        info.type = kind
        info.linkname = "/tmp/should-not-be-read"
        content = b'{"accessCodes": []}'
        info.size = len(content) if kind == tarfile.REGTYPE else 0
        tf.addfile(info, io.BytesIO(content) if info.size else None)
        other = tarfile.TarInfo("../../unrelated.json")
        other.size = 4
        tf.addfile(other, io.BytesIO(b"nope"))
    return buffer.getvalue()


def encrypt(key, iv, data):
    padder = padding.PKCS7(128).padder()
    padded = padder.update(data) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def encrypted_backup(compressed=True, bad_checksum=False):
    key, iv = bytes(range(128, 160)), bytes(range(16))
    salt, checksum_salt, rounds = b"user-salt", b"checksum-salt", 10000
    # Independent conversion following AOSP's signed byte -> Java char cast.
    chars = bytes(key).decode("latin-1")
    signed_chars = "".join(chr(ord(c) | 0xFF00) for c in chars)
    checksum = hashlib.pbkdf2_hmac("sha1", signed_chars.encode(), checksum_salt, rounds, 32)
    if bad_checksum:
        checksum = bytes(32)
    blob = b"\x10" + iv + b"\x20" + key + b"\x20" + checksum
    user_key = hashlib.pbkdf2_hmac("sha1", "tést-password".encode(), salt, rounds, 32)
    wrapped = encrypt(user_key, iv, blob)
    data = zlib.compress(archive()) if compressed else archive()
    header = [b"ANDROID BACKUP", b"5", b"1" if compressed else b"0", b"AES-256",
              salt.hex().encode(), checksum_salt.hex().encode(), b"10000", iv.hex().encode(), wrapped.hex().encode()]
    return b"\n".join(header) + b"\n" + encrypt(key, iv, data)


@pytest.mark.parametrize("compressed", [True, False])
async def test_encrypted_and_plain_backup_extract_only_config(tmp_path, compressed):
    raw = encrypted_backup(compressed)
    decoded = script["read_backup"](raw, lambda _: "tést-password")
    assert decoded == archive()
    plain = b"ANDROID BACKUP\n5\n" + (b"1" if compressed else b"0") + b"\nnone\n"
    plain += zlib.compress(archive()) if compressed else archive()
    assert script["read_backup"](plain) == decoded
    destination = tmp_path / "config.json"
    script["extract_config"](decoded, destination)
    assert destination.read_bytes() == b'{"accessCodes": []}'
    assert list(tmp_path.iterdir()) == [destination]
    with pytest.raises(FileExistsError):
        script["extract_config"](decoded, destination)


@pytest.mark.parametrize("raw,password", [
    (encrypted_backup(), "wrong"),
    (encrypted_backup(bad_checksum=True), "tést-password"),
    (b"ANDROID BACKUP\n5\n1\nAES-256\n", ""),
    (b"garbage", ""),
    (b"ANDROID BACKUP\n5\n9\nnone\n", ""),
])
async def test_invalid_backups_are_rejected(raw, password):
    with pytest.raises(ValueError):
        script["read_backup"](raw, lambda _: password)


@pytest.mark.parametrize("kind,name", [
    (tarfile.SYMTYPE, CONFIG_PATH), (tarfile.LNKTYPE, CONFIG_PATH),
    (tarfile.REGTYPE, "../../config.json"),
])
async def test_links_and_missing_config_do_not_create_output(tmp_path, kind, name):
    with pytest.raises(ValueError):
        script["extract_config"](archive(kind, name), tmp_path / "config.json")
    assert not list(tmp_path.iterdir())
