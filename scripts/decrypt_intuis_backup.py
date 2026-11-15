#!/usr/bin/env python3
"""Read an Android backup and extract only Intuis Compagnon's cached config.

Adapted from adrienvsj's PR #39. Requires Python 3.12+ and cryptography.
The password is prompted, never taken from the command line or printed.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import io
import sys
import tarfile
import zlib
from pathlib import Path

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

CONFIG_PATH = "apps/com.muller.app_toolbox/r/app_flutter/config.json"
MAX_CONFIG_SIZE = 16 * 1024 * 1024


def decrypt_cbc(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def key_checksum(key: bytes, salt: bytes, rounds: int) -> bytes:
    # Android casts signed Java bytes to chars before PBKDF2's UTF-8 encoding.
    # See AOSP PasswordUtils.makeKeyChecksum, not a raw-byte PBKDF2 password.
    password = "".join(chr(b if b < 128 else b + 0xFF00) for b in key)
    return hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), salt, rounds, 32)


def read_backup(raw: bytes, password_prompt=getpass.getpass) -> bytes:
    stream = io.BytesIO(raw)

    def line() -> bytes:
        value = stream.readline(4096)
        if not value.endswith(b"\n"):
            raise ValueError("Truncated or oversized backup header")
        return value[:-1]

    if line() != b"ANDROID BACKUP":
        raise ValueError("Not an Android backup file")
    if line() not in {b"2", b"3", b"4", b"5"}:
        raise ValueError("Supported Android backup versions: 2 through 5")
    compressed = line()
    if compressed not in {b"0", b"1"}:
        raise ValueError("Invalid compression flag")
    encryption = line()
    if encryption == b"none":
        payload = stream.read()
    elif encryption == b"AES-256":
        user_salt = bytes.fromhex(line().decode("ascii"))
        checksum_salt = bytes.fromhex(line().decode("ascii"))
        rounds = int(line())
        user_iv = bytes.fromhex(line().decode("ascii"))
        master_blob = bytes.fromhex(line().decode("ascii"))
        if not 1 <= rounds <= 1_000_000 or not user_salt or not checksum_salt:
            raise ValueError("Invalid backup key parameters")
        password = password_prompt("Backup password: ")
        user_key = hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), user_salt, rounds, 32)
        blob = io.BytesIO(decrypt_cbc(user_key, user_iv, master_blob))

        def field(length: int) -> bytes:
            size = blob.read(1)
            if size != bytes([length]):
                raise ValueError("Invalid master key blob")
            value = blob.read(length)
            if len(value) != length:
                raise ValueError("Truncated master key blob")
            return value

        master_iv, master_key, checksum = field(16), field(32), field(32)
        if blob.read() or not hmac.compare_digest(
            checksum, key_checksum(master_key, checksum_salt, rounds)
        ):
            raise ValueError("Invalid master key checksum")
        payload = decrypt_cbc(master_key, master_iv, stream.read())
    else:
        raise ValueError("Unsupported backup encryption")
    return zlib.decompress(payload) if compressed == b"1" else payload


def extract_config(archive: bytes, destination: Path) -> None:
    # Never extract archive paths, links or unrelated application data.
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tf:
        matches = [member for member in tf if member.name == CONFIG_PATH]
        if len(matches) != 1:
            raise ValueError("Expected exactly one cached Intuis config.json; backup may exclude app data")
        member = matches[0]
        if not member.isfile() or not 0 < member.size <= MAX_CONFIG_SIZE:
            raise ValueError("Cached config must be a regular file of at most 16 MiB")
        source = tf.extractfile(member)
        if source is None:
            raise ValueError("Cannot read cached config")
        with source:
            content = source.read()
    # Exclusive creation also refuses an existing symlink or accidental overwrite.
    with destination.open("xb") as output:
        output.write(content)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 decrypt_intuis_backup.py <backup.ab>", file=sys.stderr)
        return 2
    backup = Path(sys.argv[1])
    destination = backup.with_name(backup.stem + "_config.json")
    try:
        extract_config(read_backup(backup.read_bytes()), destination)
    except (OSError, ValueError, UnicodeError, zlib.error, tarfile.TarError):
        print("Cannot extract config: invalid backup/password, missing app data, or output already exists.", file=sys.stderr)
        return 1
    print(f"Extracted cached config to: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
