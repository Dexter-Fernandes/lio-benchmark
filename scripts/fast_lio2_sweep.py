#!/usr/bin/env python
"""Phase 2 (docs/protocol.md #6.2): Bayesian sweep over FAST-LIO2 params on exp14, searching
the region phase 1 already established (measured noise covariance; a found voxel-size sweet
spot). Every trial gets the same run record as a manual run and is logged to W&B tagged
"sweep"; the winner, if kept, still needs one phase-1-style confirmation run.

Usage: uv run python scripts/fast_lio2_sweep.py [--count 15]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

import wandb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fast_lio2_candidate import BASE_CONFIG, apply_overrides

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGE = "lio-benchmark/fast_lio2:dev"
PARENT_RUN_ID = "20260915T152627Z_fast_lio2_exp14"  # current kept baseline (0.2m voxel)

SWEEP_CONFIG = {
    "method": "bayes",
    "metric": {"name": "objective", "goal": "minimize"},
    "parameters": {
        "acc_cov": {"distribution": "log_uniform_values", "min": 1e-5, "max": 1e-2},
        "gyr_cov": {"distribution": "log_uniform_values", "min": 1e-6, "max": 1e-3},
        "b_acc_cov": {"distribution": "log_uniform_values", "min": 1e-6, "max": 1e-2},
        "b_gyr_cov": {"distribution": "log_uniform_values", "min": 1e-6, "max": 1e-2},
        "voxel_size": {"distribution": "uniform", "min": 0.1, "max": 0.4},
        "point_filter_num": {"distribution": "int_uniform", "min": 1, "max": 6},
        "max_iteration": {"distribution": "int_uniform", "min": 2, "max": 6},
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

    run = wandb.init(tags=["sweep", "fast_lio2", "exp14"], group="fast_lio2/exp14/sweep")
    cfg = run.config
    overrides = [
        f"mapping.acc_cov={cfg.acc_cov}", f"mapping.gyr_cov={cfg.gyr_cov}",
        f"mapping.b_acc_cov={cfg.b_acc_cov}", f"mapping.b_gyr_cov={cfg.b_gyr_cov}",
        f"launch.filter_size_surf={cfg.voxel_size}", f"launch.filter_size_map={cfg.voxel_size}",
        f"launch.point_filter_num={int(cfg.point_filter_num)}",
        f"launch.max_iteration={int(cfg.max_iteration)}",
    ]
    candidate = apply_overrides(yaml.safe_load(BASE_CONFIG.read_text()), overrides)

    manifest = load_manifest(None)
    data_root = paths.data_root()
    seq = manifest.sequence("exp14")
    split = next((name for name, keys in manifest.split.items() if seq.key in keys), "unassigned")
    store = VerifiedStore(data_root)
    hashes = {p: store.records.get(p, {}).get("digest") for p in (seq.bag, seq.ground_truth_dense)}

    run_dir = init_run(
        paths.runs_root(), "fast_lio2", seq.key, split, candidate,
        hypothesis=(f"Bayesian sweep {run.sweep_id} trial {run.id}: search region set by "
                   "phase-1 findings (measured noise covariance, docs/journal.md "
                   "20260915T133833Z; voxel-size sweet spot bracketed 0.1-0.4m, "
                   "docs/journal.md 20260915T152627Z/20260915T152922Z)."),
        change=", ".join(overrides), parent=PARENT_RUN_ID, label="sweep",
        playback_rate=0.5, dataset_hashes=hashes)

    with tempfile.TemporaryDirectory() as tmp:
        candidate_path = Path(tmp) / "candidate.yaml"
        candidate_path.write_text(yaml.safe_dump(candidate, sort_keys=False))
        raw_tum = run_dir / "raw_fast_lio2.tum"
        proc = subprocess.run([  # noqa: PLW1510 -- returncode checked explicitly below
            "docker", "run", "--rm",
            "-v", f"{data_root}:/data/hilti22:ro",
            "-v", f"{run_dir}:/run_out",
            "-v", f"{candidate_path}:/configs/fast_lio2/override.yaml:ro",
            "-e", "FAST_LIO2_CONFIG=/configs/fast_lio2/override.yaml",
            IMAGE, "/run_fast_lio2.sh", f"/data/hilti22/{seq.bag}",
            "/run_out/raw_fast_lio2.tum", "600", "0.5",
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
    ap.add_argument("--count", type=int, default=15)
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
