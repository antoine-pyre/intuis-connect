#!/usr/bin/env python3
"""Decrypt an Android `adb backup` (.ab) archive with the user's own password.

The password is read interactively (hidden), never passed on the command line,
so it stays out of the shell history and the terminal scrollback.

Usage: python3 decrypt_intuis_backup.py <backup.ab>
Output: backup.tar next to it, and the extracted config.json if present.

See docs/17-firmware-menu-avance.md for the full procedure.
"""

import getpass
import hashlib
import sys
import tarfile
import zlib
from pathlib import Path

from Crypto.Cipher import AES


def unpad(data: bytes) -> bytes:
    return data[: -data[-1]]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 decrypt_intuis_backup.py <backup.ab>", file=sys.stderr)
        return 2
    raw = Path(sys.argv[1]).read_bytes()
    # Header lines are newline-separated ASCII, then the binary payload.
    parts = raw.split(b"\n", 9)
    magic, version, compressed, encryption = parts[0], parts[1], parts[2], parts[3]
    if magic != b"ANDROID BACKUP":
        print("Not an Android backup file.", file=sys.stderr)
        return 1
    if encryption == b"none":
        payload = raw.split(b"\n", 4)[4]
        tar = zlib.decompress(payload) if compressed == b"1" else payload
    elif encryption == b"AES-256":
        user_salt = bytes.fromhex(parts[4].decode())
        checksum_salt = bytes.fromhex(parts[5].decode())
        rounds = int(parts[6])
        user_iv = bytes.fromhex(parts[7].decode())
        master_blob = bytes.fromhex(parts[8].decode())
        payload = parts[9]

        pw = getpass.getpass("Backup password: ")
        # Derive the key that wraps the master key, from the password.
        user_key = hashlib.pbkdf2_hmac("sha1", pw.encode(), user_salt, rounds, 32)
        try:
            blob = unpad(AES.new(user_key, AES.MODE_CBC, user_iv).decrypt(master_blob))
            # blob = [len][master IV][len][master key][len][checksum]
            i = 0
            n = blob[i]; i += 1
            master_iv = blob[i:i + n]; i += n
            n = blob[i]; i += 1
            master_key = blob[i:i + n]; i += n
            # The checksum (the rest) is skipped: Android's checksum has a
            # sign-extension quirk that makes it unreliable to recompute. The
            # real proof of a correct password is that the payload below
            # decrypts and decompresses cleanly.
            data = unpad(AES.new(master_key, AES.MODE_CBC, master_iv).decrypt(payload))
            tar = zlib.decompress(data) if compressed == b"1" else data
        except (ValueError, zlib.error):
            print("Wrong password (decryption failed).", file=sys.stderr)
            return 1
    else:
        print(f"Unsupported encryption: {encryption!r}", file=sys.stderr)
        return 1

    out = Path(sys.argv[1]).with_suffix(".tar")
    out.write_bytes(tar)
    print(f"OK: {out} ({len(tar)} bytes)")

    # List and extract any JSON file (the cached config lives there).
    with tarfile.open(out) as tf:
        names = tf.getnames()
        jsons = [n for n in names if n.lower().endswith(".json")]
        print(f"{len(names)} files in the archive, {len(jsons)} JSON:")
        for n in jsons:
            print("  ", n)
        dest = out.parent / "backup_extracted"
        try:
            tf.extractall(dest, filter="data")  # Python 3.12+
        except TypeError:
            tf.extractall(dest)  # older Python has no `filter` argument
        print(f"Extracted to: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
