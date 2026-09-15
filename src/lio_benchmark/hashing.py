"""Streaming file hashes matching what Hugging Face publishes.

LFS objects are identified by the SHA-256 of their content. Small files stored as plain git
blobs are identified only by their git blob SHA-1, i.e. SHA-1 over b"blob <size>\\0" + content,
which is what `git hash-object <file>` prints.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK = 8 * 1024 * 1024
ALGORITHMS = {"sha256": 64, "git_blob_sha1": 40}   # algorithm -> hex digest length


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha1_file(path: Path) -> str:
    size = Path(path).stat().st_size
    h = hashlib.sha1(f"blob {size}\0".encode())
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def file_digest(path: Path, algorithm: str) -> str:
    if algorithm == "sha256":
        return sha256_file(path)
    if algorithm == "git_blob_sha1":
        return git_blob_sha1_file(path)
    raise ValueError(f"unknown hash algorithm: {algorithm}")
