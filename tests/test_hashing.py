import hashlib
import shutil
import subprocess

import pytest

from lio_benchmark.hashing import file_digest, git_blob_sha1_file, sha256_file


def test_sha256_known_value(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"abc")
    assert sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_git_blob_sha1_known_values(tmp_path):
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    assert git_blob_sha1_file(empty) == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"   # git's empty blob
    f = tmp_path / "hello"
    f.write_bytes(b"hello\n")
    assert git_blob_sha1_file(f) == "ce013625030ba8dba906f756967f9e9ca394464a"


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_blob_sha1_matches_git_hash_object(tmp_path):
    f = tmp_path / "multi-chunk.bin"
    f.write_bytes(bytes(range(256)) * 50_000)   # crosses the read chunk boundary
    expected = subprocess.run(["git", "hash-object", str(f)], capture_output=True, text=True,
                              check=True).stdout.strip()
    assert git_blob_sha1_file(f) == expected
    assert file_digest(f, "sha256") == hashlib.sha256(f.read_bytes()).hexdigest()


def test_unknown_algorithm(tmp_path):
    f = tmp_path / "x"
    f.write_bytes(b"x")
    with pytest.raises(ValueError):
        file_digest(f, "md5")
