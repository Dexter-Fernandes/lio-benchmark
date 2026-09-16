#!/usr/bin/env python
"""Phase 2 (docs/protocol.md #6.2): Bayesian sweep over GLIM params on exp14.

Ranges here are deliberately WIDER than a strict phase-1-bounded sweep would use -- a
documented deviation, same spirit as lio_sam_sweep.py's (docs/protocol.md #6.2: sweeping
without a phase-1-justified region is "guessing with extra steps, not a real phase 2", so
this is labelled as such, not presented as equivalent rigor to fast_lio2_sweep.py). Only
odometry_cpu.ivox_resolution has an actual phase-1 finding behind it (0.2m kept over 1.0m
default and 0.1m sibling, docs/journal.md "GLIM integration and phase-1 tuning summary"); its
range below still spans well past that finding rather than bracketing it tightly. Every other
dimension here (ivox_min_dist, max_iterations, smoother_lag, registration_type/
vgicp_resolution, and all three IMU noise params) has no phase-1 measurement behind it at all
-- IMU noise ranges in particular are wide because GLIM's preintegration noise-unit
convention hasn't been verified against source (docs/methods.md "GLIM integration", "Still
open"), so the range covers both a "same units as configured" and a "much smaller, like
FAST-LIO2's measured std" interpretation rather than guessing one.

Usage: uv run python scripts/glim_sweep.py [--count 20]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import wandb
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glim_candidate import BASE_CONFIG, apply_overrides

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGE = "lio-benchmark/glim:dev"
PARENT_RUN_ID = "20260916T054701Z_glim_exp14_glim_ivox0.2_r1"  # current kept baseline

SWEEP_CONFIG = {
    "method": "bayes",
    "metric": {"name": "objective", "goal": "minimize"},
    "parameters": {
        # Phase-1 found 0.2m best among {1.0, 0.2, 0.1}; this range spans well past that
        # finding rather than bracketing it (wider than typical, per the deviation above).
        "ivox_resolution": {"distribution": "uniform", "min": 0.02, "max": 1.0},
        "ivox_min_dist": {"distribution": "uniform", "min": 0.01, "max": 0.3},
        "max_iterations": {"distribution": "int_uniform", "min": 2, "max": 30},
        "smoother_lag": {"distribution": "uniform", "min": 0.5, "max": 20.0},
        # Phase-1 showed VGICP worse than GICP at one matched resolution (0.2m); untested at
        # other resolutions, so both stay in the search rather than dropping VGICP outright.
        "registration_type": {"values": ["GICP", "VGICP"]},
        "vgicp_resolution": {"distribution": "uniform", "min": 0.02, "max": 1.0},
        # IMU noise (upstream defaults: imu_acc_noise 0.05, imu_gyro_noise 0.02,
        # imu_bias_noise 1e-5) -- wide log-uniform spread, unit convention unverified.
        "imu_acc_noise": {"distribution": "log_uniform_values", "min": 1e-4, "max": 1.0},
        "imu_gyro_noise": {"distribution": "log_uniform_values", "min": 1e-4, "max": 0.5},
        "imu_bias_noise": {"distribution": "log_uniform_values", "min": 1e-7, "max": 1e-2},
    },
}


def run_trial():
    from lio_benchmark import paths
    from lio_benchmark.download import VerifiedStore
    from lio_benchmark.evaluation import EvalConfig, evaluate
    from lio_benchmark.manifest import load_manifest
    from lio_benchmark.plots import plot_evaluation
    from lio_benchmark.tracking import flatten, init_run, update_run, write_metrics
    from lio_benchmark.trajectory import load_sparse, load_tum, save_tum

    run = wandb.init(tags=["sweep", "glim", "exp14"], group="glim/exp14/sweep")
    cfg = run.config
    overrides = [
        f"odometry_cpu.ivox_resolution={cfg.ivox_resolution}",
        f"odometry_cpu.ivox_min_dist={cfg.ivox_min_dist}",
        f"odometry_cpu.max_iterations={int(cfg.max_iterations)}",
        f"odometry_cpu.smoother_lag={cfg.smoother_lag}",
        f"odometry_cpu.registration_type={cfg.registration_type}",
        f"odometry_cpu.vgicp_resolution={cfg.vgicp_resolution}",
        f"sensors.imu_acc_noise={cfg.imu_acc_noise}",
        f"sensors.imu_gyro_noise={cfg.imu_gyro_noise}",
        f"sensors.imu_bias_noise={cfg.imu_bias_noise}",
    ]
    candidate = apply_overrides(yaml.safe_load(BASE_CONFIG.read_text()), overrides)

    manifest = load_manifest(None)
    data_root = paths.data_root()
    seq = manifest.sequence("exp14")
    split = next((name for name, keys in manifest.split.items() if seq.key in keys), "unassigned")
    store = VerifiedStore(data_root)
    hashes = {p: store.records.get(p, {}).get("digest") for p in (seq.bag, seq.ground_truth_dense)}

    run_dir = init_run(
        paths.runs_root(), "glim", seq.key, split, candidate,
        hypothesis=(f"Bayesian sweep {run.sweep_id} trial {run.id}: DEVIATION from "
                   "docs/protocol.md #6 -- ranges are wider than a strict phase-1-bounded "
                   "sweep (only ivox_resolution has a phase-1 finding behind it, and this "
                   "range spans well past it; IMU noise units are unverified against source). "
                   "See scripts/glim_sweep.py's module docstring and docs/methods.md "
                   "'GLIM integration'."),
        change=", ".join(overrides), parent=PARENT_RUN_ID, label="sweep",
        playback_rate=1.0, dataset_hashes=hashes)

    with tempfile.TemporaryDirectory() as tmp:
        candidate_path = Path(tmp) / "candidate.yaml"
        candidate_path.write_text(yaml.safe_dump(candidate, sort_keys=False))
        raw_tum = run_dir / "raw_glim.tum"
        proc = subprocess.run([  # noqa: PLW1510 -- returncode checked explicitly below
            "docker", "run", "--rm",
            "-v", f"{data_root}:/data/hilti22:ro",
            "-v", f"{run_dir}:/run_out",
            "-v", f"{candidate_path}:/configs/glim/override.yaml:ro",
            "-e", "GLIM_CONFIG=/configs/glim/override.yaml",
            IMAGE, "/run_glim.sh", f"/data/hilti22/{seq.rosbag2}",
            "/run_out/raw_glim.tum", "300", "1.0",
        ], capture_output=True, text=True)

    if proc.returncode != 0 or not raw_tum.exists() or raw_tum.stat().st_size == 0:
        update_run(run_dir, status="failed")
        wandb.log({"objective": float("inf"), "failed": True})
        print(proc.stdout[-2000:], proc.stderr[-2000:], file=sys.stderr)
        wandb.finish()
        return

    gt = load_tum(data_root / seq.ground_truth_dense)
    sparse = load_sparse(data_root / seq.ground_truth_sparse)
    est = load_tum(raw_tum)
    eval_cfg = EvalConfig.from_yaml(REPO_ROOT / "configs/eval/default.yaml")
    result = evaluate(gt, est, eval_cfg, sparse=sparse)
    metrics = {"sequence": seq.key, "split": split, "estimate_frame": "imu", **result.metrics}
    write_metrics(run_dir, metrics)
    save_tum(run_dir / "trajectory.tum", est)
    update_run(run_dir, status=metrics["status"])
    plot_evaluation(gt, result, run_dir, f"{seq.key} sweep {run.id}")

    objective = metrics["ate"]["trans_m"]["rmse"] if metrics.get("ate") else float("inf")
    scalars = {k: v for k, v in flatten(metrics).items() if isinstance(v, (int, float))}
    wandb.log({**scalars, "objective": objective})
    for png in sorted(run_dir.glob("*.png")):
        wandb.log({png.stem: wandb.Image(str(png))})
    wandb.finish()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=20)
    args = ap.parse_args()

    api = wandb.Api()
    entity = api.default_entity
    project = "lio-benchmark"
    sweep_id = wandb.sweep(SWEEP_CONFIG, project=project, entity=entity)
    print(f"sweep: https://wandb.ai/{entity}/{project}/sweeps/{sweep_id}")

    wandb.agent(sweep_id, function=run_trial, project=project, entity=entity, count=args.count)

    # A fresh process, not this one: wandb.agent tears down the shared async service
    # connection on exit, and reusing an Api() object (even a new one) after that raises
    # AlreadyJoinedError from inside the same process.
    subprocess.run([sys.executable, "-c", f"""
import wandb
best = wandb.Api().sweep("{entity}/{project}/{sweep_id}").best_run()
print(f"best trial: {{best.id}}  objective={{best.summary.get('objective')}}")
print(f"  config: {{dict(best.config)}}")
"""], check=False)


if __name__ == "__main__":
    main()
