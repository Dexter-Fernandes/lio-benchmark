"""Load and validate the dataset manifest (manifests/hilti22.yaml)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .hashing import ALGORITHMS
from .paths import manifest_path


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class FileEntry:
    path: str          # relative to the data root; also the path in the source repository
    size: int
    group: str
    algorithm: str     # key of hashing.ALGORITHMS
    digest: str


@dataclass(frozen=True)
class Sequence:
    key: str           # short id, e.g. "exp14"
    name: str          # full name, e.g. "exp14_basement_2"
    environment: str
    bag: str
    rosbag2: str
    ground_truth_dense: str
    ground_truth_sparse: str


@dataclass
class Manifest:
    dataset: str
    source: dict
    license: dict
    citation: str
    default_groups: list[str]
    files: list[FileEntry]
    sequences: dict[str, Sequence]
    split: dict[str, list[str]]
    path: Path | None = field(default=None, compare=False)

    @property
    def revision(self) -> str:
        return self.source["revision"]

    @property
    def groups(self) -> list[str]:
        return sorted({f.group for f in self.files})

    def url(self, entry: FileEntry) -> str:
        return self.source["url_template"].format(
            repo=self.source["repo"], revision=self.revision, path=entry.path)

    def entry(self, path: str) -> FileEntry:
        for f in self.files:
            if f.path == path:
                return f
        raise KeyError(path)

    def select(self, groups: list[str] | None = None) -> list[FileEntry]:
        groups = list(groups or self.default_groups)
        unknown = set(groups) - set(self.groups)
        if unknown:
            raise ManifestError(f"unknown groups {sorted(unknown)}; available: {self.groups}")
        return [f for f in self.files if f.group in groups]

    def sequence(self, key_or_name: str) -> Sequence:
        for s in self.sequences.values():
            if key_or_name in (s.key, s.name):
                return s
        raise KeyError(f"unknown sequence {key_or_name!r}; available: {sorted(self.sequences)}")


def _parse_hash(raw: dict, path: str) -> tuple[str, str]:
    if not isinstance(raw, dict) or len(raw) != 1:
        raise ManifestError(f"{path}: hash must be a single {{algorithm: digest}} mapping")
    (algorithm, digest), = raw.items()
    if algorithm not in ALGORITHMS:
        raise ManifestError(f"{path}: unknown hash algorithm {algorithm!r}")
    digest = str(digest).lower()
    if len(digest) != ALGORITHMS[algorithm] or any(c not in "0123456789abcdef" for c in digest):
        raise ManifestError(f"{path}: malformed {algorithm} digest")
    return algorithm, digest


def load_manifest(path: Path | None = None) -> Manifest:
    path = Path(path or manifest_path())
    raw = yaml.safe_load(path.read_text())

    files: list[FileEntry] = []
    seen: set[str] = set()
    for f in raw["files"]:
        p = f["path"]
        if p in seen:
            raise ManifestError(f"duplicate path {p}")
        if p.startswith("/") or ".." in Path(p).parts:
            raise ManifestError(f"{p}: paths must be relative and inside the data root")
        seen.add(p)
        if not isinstance(f.get("size"), int) or f["size"] <= 0:
            raise ManifestError(f"{p}: size must be a positive integer")
        algorithm, digest = _parse_hash(f.get("hash"), p)
        files.append(FileEntry(p, f["size"], f["group"], algorithm, digest))

    sequences = {k: Sequence(key=k, **v) for k, v in raw["sequences"].items()}
    for s in sequences.values():
        for p in (s.bag, s.ground_truth_dense, s.ground_truth_sparse):
            if p not in seen:
                raise ManifestError(f"sequence {s.key}: {p} is not listed under files")

    split = {k: list(v) for k, v in raw["split"].items()}
    all_split = [s for v in split.values() for s in v]
    if len(all_split) != len(set(all_split)):
        raise ManifestError("split sets overlap")
    if missing := set(all_split) - set(sequences):
        raise ManifestError(f"split names unknown sequences {sorted(missing)}")

    m = Manifest(raw["dataset"], raw["source"], raw["license"], raw["citation"].strip(),
                 list(raw["default_groups"]), files, sequences, split, path)
    if unknown := set(m.default_groups) - set(m.groups):
        raise ManifestError(f"default_groups names unknown groups {sorted(unknown)}")
    return m
