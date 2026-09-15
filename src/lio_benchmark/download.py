"""Selective, resumable, integrity-checked downloads into the data root.

Each file is fetched with curl (resume with `-C -`, retries) into `<file>.part`. The part is
checked against the manifest size and hash and only then renamed into place, so a file at
its final path has always been verified at least once. Verified files are recorded in
`_provenance/verified.json` with their size and mtime, so later runs skip re-hashing
multi-gigabyte bags unless `rehash` is requested or the file has changed.

The curl resume pattern is adapted from ranger-lio's scripts/download_hilti.sh.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .hashing import file_digest
from .manifest import FileEntry, Manifest
from .paths import provenance_dir

SPACE_MARGIN = 2 * 1024**3   # keep 2 GiB free beyond what the downloads need


class DownloadError(RuntimeError):
    pass


class InsufficientSpace(DownloadError):
    pass


def _log(msg: str) -> None:
    print(msg, flush=True)   # flushed so background logs show progress


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


class VerifiedStore:
    """Record of files whose content has been hashed and matched the manifest."""

    def __init__(self, data_root: Path):
        self.path = provenance_dir(data_root) / "verified.json"
        self.records: dict[str, dict] = json.loads(self.path.read_text()) if self.path.exists() else {}

    def is_current(self, entry: FileEntry, file: Path) -> bool:
        rec = self.records.get(entry.path)
        if not rec or not file.exists():
            return False
        st = file.stat()
        return (rec["size"] == st.st_size == entry.size and rec["mtime_ns"] == st.st_mtime_ns
                and rec["algorithm"] == entry.algorithm and rec["digest"] == entry.digest)

    def record(self, entry: FileEntry, file: Path, revision: str, how: str) -> None:
        st = file.stat()
        self.records[entry.path] = {
            "size": st.st_size, "mtime_ns": st.st_mtime_ns, "algorithm": entry.algorithm,
            "digest": entry.digest, "verified_at": _now(), "source_revision": revision, "how": how,
        }
        write_json_atomic(self.path, self.records)

    def forget(self, entry: FileEntry) -> None:
        if self.records.pop(entry.path, None) is not None:
            write_json_atomic(self.path, self.records)


@dataclass
class FileStatus:
    entry: FileEntry
    state: str          # ok | ok-cached | missing | partial | size-mismatch | hash-mismatch
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.state in ("ok", "ok-cached")


def part_path(file: Path) -> Path:
    return file.with_name(file.name + ".part")


def check_file(entry: FileEntry, data_root: Path, store: VerifiedStore, revision: str,
               rehash: bool = False) -> FileStatus:
    """Verify one file; hash it only if it is not already recorded as verified (or rehash)."""
    file = data_root / entry.path
    if not file.exists():
        part = part_path(file)
        if part.exists():
            return FileStatus(entry, "partial", f"{part.stat().st_size}/{entry.size} bytes")
        return FileStatus(entry, "missing")
    size = file.stat().st_size
    if size != entry.size:
        store.forget(entry)
        return FileStatus(entry, "size-mismatch", f"{size} != {entry.size}")
    if not rehash and store.is_current(entry, file):
        return FileStatus(entry, "ok-cached")
    actual = file_digest(file, entry.algorithm)
    if actual != entry.digest:
        store.forget(entry)
        return FileStatus(entry, "hash-mismatch", f"{entry.algorithm} {actual} != {entry.digest}")
    store.record(entry, file, revision, how="verified-existing")
    return FileStatus(entry, "ok")


def bytes_needed(entries: list[FileEntry], data_root: Path) -> int:
    total = 0
    for e in entries:
        file = data_root / e.path
        if file.exists():
            continue
        part = part_path(file)
        total += e.size - (part.stat().st_size if part.exists() else 0)
    return total


def preflight_space(entries: list[FileEntry], data_root: Path, margin: int = SPACE_MARGIN) -> int:
    needed = bytes_needed(entries, data_root)
    probe = data_root
    while not probe.exists():
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if needed + margin > free:
        raise InsufficientSpace(
            f"need {needed / 1e9:.2f} GB + {margin / 1e9:.1f} GB margin, "
            f"only {free / 1e9:.2f} GB free on {probe}")
    return needed


def fetch(url: str, part: Path, expected_size: int, retries: int = 8, retry_delay: int = 10) -> None:
    """Resume `part` from `url` until it has `expected_size` bytes."""
    part.parent.mkdir(parents=True, exist_ok=True)
    if part.exists() and part.stat().st_size > expected_size:
        part.unlink()   # cannot be a prefix of the right file
    if part.exists() and part.stat().st_size == expected_size:
        return          # complete; asking for a range past the end would return 416
    progress = ["--progress-bar"] if sys.stderr.isatty() else ["--silent", "--show-error"]
    cmd = ["curl", "--location", "--fail", "--retry", str(retries), "--retry-delay", str(retry_delay),
           "--retry-all-errors", "--continue-at", "-", *progress, "--output", str(part), url]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise DownloadError(f"curl exited {result.returncode} for {url} (partial file kept for resume)")


def download_entry(entry: FileEntry, url: str, data_root: Path, store: VerifiedStore,
                   revision: str, log=_log) -> FileStatus:
    file = data_root / entry.path
    if file.exists():
        status = check_file(entry, data_root, store, revision)
        if not status.ok:
            raise DownloadError(
                f"{entry.path} exists but fails verification ({status.state}: {status.detail}); "
                "move it aside and re-run to download a fresh copy")
        log(f"skip  {entry.path} ({status.state})")
        return status

    part = part_path(file)
    log(f"fetch {entry.path} ({entry.size / 1e9:.3f} GB)")
    fetch(url, part, entry.size)
    size = part.stat().st_size
    if size != entry.size:
        raise DownloadError(f"{entry.path}: downloaded {size} bytes, expected {entry.size}")
    log(f"hash  {entry.path} ({entry.algorithm})")
    actual = file_digest(part, entry.algorithm)
    if actual != entry.digest:
        bad = part.with_name(part.name + ".corrupt")
        os.replace(part, bad)
        raise DownloadError(
            f"{entry.path}: {entry.algorithm} {actual} != manifest {entry.digest}; kept as {bad.name}")
    os.replace(part, file)
    store.record(entry, file, revision, how="downloaded")
    log(f"ok    {entry.path}")
    return FileStatus(entry, "ok")


def download(manifest: Manifest, data_root: Path, groups: list[str] | None = None,
             log=_log) -> list[FileStatus]:
    entries = manifest.select(groups)
    store = VerifiedStore(data_root)
    needed = preflight_space(entries, data_root)
    log(f"{len(entries)} files selected, {needed / 1e9:.2f} GB to fetch into {data_root} "
        f"(revision {manifest.revision[:12]})")
    return [download_entry(e, manifest.url(e), data_root, store, manifest.revision, log)
            for e in entries]


def verify(manifest: Manifest, data_root: Path, groups: list[str] | None = None,
           rehash: bool = False) -> list[FileStatus]:
    store = VerifiedStore(data_root)
    return [check_file(e, data_root, store, manifest.revision, rehash) for e in manifest.select(groups)]
