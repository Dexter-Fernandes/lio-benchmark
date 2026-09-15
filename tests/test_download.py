import hashlib
import shutil

import pytest

from lio_benchmark import download as dl
from lio_benchmark.download import (DownloadError, InsufficientSpace, VerifiedStore, check_file,
                                    download_entry, part_path, preflight_space)
from lio_benchmark.manifest import FileEntry

pytestmark = pytest.mark.skipif(shutil.which("curl") is None, reason="curl not installed")

REV = "0" * 40
PAYLOAD = bytes(range(256)) * 4000   # 1 MB


def entry(path="rosbags/x.bag", data=PAYLOAD, digest=None, size=None):
    return FileEntry(path, size or len(data), "seq:x", "sha256",
                     digest or hashlib.sha256(data).hexdigest())


def served(http_root, name="x.bag", data=PAYLOAD):
    base, root, log = http_root
    (root / name).write_bytes(data)
    return f"{base}/{name}", log


def test_fresh_download_verifies_and_records(tmp_path, http_root):
    url, _ = served(http_root)
    data_root, e = tmp_path / "data", entry()
    store = VerifiedStore(data_root)
    status = download_entry(e, url, data_root, store, REV, log=lambda *_: None)
    assert status.ok
    assert (data_root / e.path).read_bytes() == PAYLOAD
    assert not part_path(data_root / e.path).exists()
    assert VerifiedStore(data_root).is_current(e, data_root / e.path)   # persisted


def test_resumes_from_partial_file(tmp_path, http_root):
    url, log = served(http_root)
    data_root, e = tmp_path / "data", entry()
    part = part_path(data_root / e.path)
    part.parent.mkdir(parents=True)
    part.write_bytes(PAYLOAD[:300_000])
    download_entry(e, url, data_root, VerifiedStore(data_root), REV, log=lambda *_: None)
    assert (data_root / e.path).read_bytes() == PAYLOAD
    assert log[-1][1] == "bytes=300000-"   # only the remainder was requested


def test_hash_mismatch_is_not_renamed(tmp_path, http_root):
    url, _ = served(http_root)
    data_root, e = tmp_path / "data", entry(digest="f" * 64)
    with pytest.raises(DownloadError, match="sha256"):
        download_entry(e, url, data_root, VerifiedStore(data_root), REV, log=lambda *_: None)
    assert not (data_root / e.path).exists()
    assert (data_root / "rosbags" / "x.bag.part.corrupt").exists()


def test_size_mismatch_fails(tmp_path, http_root):
    url, _ = served(http_root)
    data_root = tmp_path / "data"
    e = entry(size=len(PAYLOAD) + 10)
    with pytest.raises(DownloadError):
        download_entry(e, url, data_root, VerifiedStore(data_root), REV, log=lambda *_: None)
    assert not (data_root / e.path).exists()


def test_http_error_keeps_partial(tmp_path, http_root):
    base, _, _ = http_root
    data_root, e = tmp_path / "data", entry()
    with pytest.raises(DownloadError, match="curl exited"):
        dl.fetch(f"{base}/missing.bag", part_path(data_root / e.path), e.size, retries=0)


def test_existing_verified_file_is_skipped_without_request(tmp_path, http_root):
    url, log = served(http_root)
    data_root, e = tmp_path / "data", entry()
    store = VerifiedStore(data_root)
    download_entry(e, url, data_root, store, REV, log=lambda *_: None)
    n = len(log)
    status = download_entry(e, url, data_root, store, REV, log=lambda *_: None)
    assert status.state == "ok-cached" and len(log) == n


def test_existing_corrupt_file_is_refused(tmp_path, http_root):
    url, log = served(http_root)
    data_root, e = tmp_path / "data", entry()
    (data_root / "rosbags").mkdir(parents=True)
    (data_root / e.path).write_bytes(b"\0" * len(PAYLOAD))
    with pytest.raises(DownloadError, match="hash-mismatch"):
        download_entry(e, url, data_root, VerifiedStore(data_root), REV, log=lambda *_: None)
    assert log == []


def test_check_file_detects_change_after_verification(tmp_path):
    data_root, e = tmp_path / "data", entry()
    (data_root / "rosbags").mkdir(parents=True)
    f = data_root / e.path
    f.write_bytes(PAYLOAD)
    store = VerifiedStore(data_root)
    assert check_file(e, data_root, store, REV).state == "ok"
    assert check_file(e, data_root, store, REV).state == "ok-cached"
    f.write_bytes(PAYLOAD[:-1] + b"\x00")          # same size, new mtime and content
    assert check_file(e, data_root, store, REV).state == "hash-mismatch"


def test_preflight_refuses_when_space_is_short(tmp_path, monkeypatch):
    e = entry(size=10 * 1024**3)
    monkeypatch.setattr(dl.shutil, "disk_usage", lambda p: shutil._ntuple_diskusage(0, 0, 5 * 1024**3))
    with pytest.raises(InsufficientSpace):
        preflight_space([e], tmp_path)


def test_preflight_counts_only_remaining_bytes(tmp_path):
    e = entry()
    part = part_path(tmp_path / e.path)
    part.parent.mkdir(parents=True)
    part.write_bytes(PAYLOAD[:1000])
    assert preflight_space([e], tmp_path, margin=0) == len(PAYLOAD) - 1000
