"""Run records for manually guided experiments.

Every run lives in <runs root>/<run_id>/ and is complete without W&B:

    run.json               method, sequence, split, hypothesis, parent run, change, playback
                           rate, status, interpretation and keep/revert/investigate decision
    config.resolved.yaml   the full configuration the method ran with, and its hash in run.json
    env.json               git commit/dirty state, container image, CPU and thread limits,
                           package versions, dataset file hashes from the manifest
    metrics.json / .csv    evaluation output (nested JSON and flattened scalars)
    trajectory.tum, plots, logs

`log_to_wandb` mirrors a finished record to Weights & Biases. W&B is imported only there, and
WANDB_MODE defaults to offline, so no credentials are needed to develop or run experiments.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .download import write_json_atomic
from .paths import repo_root, setting


def canonical_hash(obj) -> str:
    """SHA-256 of a JSON rendering that ignores key order."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def flatten(d: dict, prefix: str = "") -> dict:
    """Nested metrics -> {'ate.trans_m.rmse': value} for scalar leaves (lists are skipped)."""
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif isinstance(v, (int, float, str, bool)) or v is None:
            out[key] = v
    return out


def git_state() -> dict:
    def git(*args):
        r = subprocess.run(["git", "-C", str(repo_root()), *args], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    status = git("status", "--porcelain")
    return {"commit": git("rev-parse", "HEAD"), "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(status) if status is not None else None}


def environment() -> dict:
    try:
        affinity = len(os.sched_getaffinity(0))
    except AttributeError:
        affinity = None
    packages = {}
    for name in ("lio-benchmark", "numpy", "scipy", "rosbags"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "platform": platform.platform(), "machine": platform.machine(),
        "python": platform.python_version(), "cpu_count": os.cpu_count(), "cpu_affinity": affinity,
        "thread_env": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
        "container_image": os.environ.get("LIO_CONTAINER_IMAGE"),
        "packages": packages,
    }


def new_run_id(method: str, sequence: str, label: str = "") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", "_".join([stamp, method, sequence] + ([label] if label else [])))


def init_run(runs_root: Path, method: str, sequence: str, split: str, config: dict, *,
             hypothesis: str, change: str, parent: str | None = None, label: str = "",
             playback_rate: float | None = None, dataset_hashes: dict | None = None) -> Path:
    run_id = new_run_id(method, sequence, label)
    run_dir = Path(runs_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config.resolved.yaml").write_text(yaml.safe_dump(config, sort_keys=True))
    write_json_atomic(run_dir / "env.json", {"git": git_state(), **environment(),
                                              "dataset_hashes": dataset_hashes or {}})
    write_json_atomic(run_dir / "run.json", {
        "run_id": run_id, "method": method, "sequence": sequence, "split": split,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_hash": canonical_hash(config), "hypothesis": hypothesis, "change": change,
        "parent": parent, "playback_rate": playback_rate, "status": "created",
        "interpretation": None, "decision": None,
    })
    return run_dir


def read_run(run_dir: Path) -> dict:
    return json.loads((Path(run_dir) / "run.json").read_text())


def update_run(run_dir: Path, **fields) -> dict:
    run = {**read_run(run_dir), **fields}
    write_json_atomic(Path(run_dir) / "run.json", run)
    return run


def write_metrics(run_dir: Path, metrics: dict) -> None:
    run_dir = Path(run_dir)
    write_json_atomic(run_dir / "metrics.json", metrics)
    flat = flatten(metrics)
    with open(run_dir / "metrics.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k in sorted(flat):
            w.writerow([k, flat[k]])


def log_to_wandb(run_dir: Path) -> str:
    """Mirror a run record to W&B (offline unless WANDB_MODE=online). Returns the W&B run path."""
    import wandb   # optional dependency: `uv sync --extra wandb`

    run_dir = Path(run_dir)
    run = read_run(run_dir)
    config = yaml.safe_load((run_dir / "config.resolved.yaml").read_text())
    env = json.loads((run_dir / "env.json").read_text())
    metrics = json.loads((run_dir / "metrics.json").read_text()) if (run_dir / "metrics.json").exists() else {}
    wb = wandb.init(
        project=setting("WANDB_PROJECT", "lio-benchmark"), entity=setting("WANDB_ENTITY"),
        mode=setting("WANDB_MODE", "offline"), dir=str(run_dir), name=run["run_id"], id=run["run_id"],
        group=f"{run['method']}/{run['sequence']}", job_type=run["split"],
        tags=[run["method"], run["sequence"], run["split"]],
        config={"method_config": config, "run": run, "env": env}, resume="allow",
    )
    wb.summary.update({k: v for k, v in flatten(metrics).items() if v is not None})
    for png in sorted(run_dir.glob("*.png")):
        wb.log({png.stem: wandb.Image(str(png))})
    for name in ("trajectory.tum", "metrics.json", "config.resolved.yaml"):
        if (run_dir / name).exists():
            wb.save(str(run_dir / name), base_path=str(run_dir), policy="now")
    path = wb.path if hasattr(wb, "path") else run["run_id"]
    wb.finish()
    return path
