"""Locations of the repository, the dataset root and run outputs.

Resolution order for every setting: process environment, then `<repo>/.env`, then a default.
The tools image sets LIO_DATA_ROOT=/data/hilti22; on the host it defaults to ~/data/hilti22.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve().parents[2]   # src/lio_benchmark/paths.py -> repo (editable install)
    return here if (here / "manifests").is_dir() else Path.cwd()


@lru_cache(maxsize=1)
def _dotenv() -> dict[str, str]:
    path = repo_root() / ".env"
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def setting(name: str, default: str | None = None) -> str | None:
    """Environment variable, else a non-empty value from .env, else `default`."""
    value = os.environ.get(name) or _dotenv().get(name)
    return value if value else default


def data_root() -> Path:
    return Path(setting("LIO_DATA_ROOT") or Path.home() / "data" / "hilti22")


def runs_root() -> Path:
    return Path(setting("LIO_RUNS_ROOT") or repo_root() / "runs")


def provenance_dir(root: Path | None = None) -> Path:
    """Per-data-root provenance records (verification, conversions, inspections)."""
    return (root or data_root()) / "_provenance"


def manifest_path() -> Path:
    return repo_root() / "manifests" / "hilti22.yaml"
