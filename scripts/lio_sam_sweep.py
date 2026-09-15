#!/usr/bin/env python
"""Phase 2 Bayesian sweep over LIO-SAM params on exp14 -- with phase 1 explicitly SKIPPED
(confirmed decision, docs/journal.md/docs/methods.md). docs/protocol.md #6.2 calls sweeping
without a phase-1-justified region "guessing with extra steps, not a real phase 2"; this run
is exactly that deviation, done deliberately and documented, not silently presented as
equivalent rigor to fast_lio2_sweep.py's phase-1-bounded search. Ranges below are therefore
centered on LIO-SAM's own upstream defaults (config/params.yaml) with 1-2 orders of magnitude
of spread on each side, not a measured region.

LIO-SAM has no configurable optimization-iteration-count param (mapOptmization.cpp hardcodes
30 LM iterations, src/mapOptmization.cpp:1292) -- unlike FAST-LIO2's max_iteration, so there
is no equivalent sweep dimension here; verified against source, not guessed.

Usage: uv run python scripts/lio_sam_sweep.py --parent-run-id <baseline run id from step 7> [--count 10]
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
from lio_sam_candidate import BASE_CONFIG, apply_overrides

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGE = "lio-benchmark/lio_sam:dev"
RUN_PARENT_ID = None  # set from --parent-run-id in main() before wandb.agent runs any trial

SWEEP_CONFIG = {
    "method": "bayes",
    "metric": {"name": "objective", "goal": "minimize"},
    "parameters": {
        # IMU noise (upstream defaults: accNoise 3.99e-3, gyrNoise 1.56e-3, accBiasN 6.44e-5,
        # gyrBiasN 3.56e-5) -- wide log-uniform spread since no phase-1 measurement bounds it.
        "imu_acc_noise": {"distribution": "log_uniform_values", "min": 1e-5, "max": 1e-1},
        "imu_gyr_noise": {"distribution": "log_uniform_values", "min": 1e-6, "max": 1e-2},
        "imu_acc_bias_n": {"distribution": "log_uniform_values", "min": 1e-7, "max": 1e-3},
        "imu_gyr_bias_n": {"distribution": "log_uniform_values", "min": 1e-7, "max": 1e-3},
        # Feature/registration leaf sizes (upstream defaults: odometrySurf 0.4, mappingCorner
        # 0.2, mappingSurf 0.4) -- wider than FAST-LIO2's phase-1-bounded voxel sweep.
        "odometry_surf_leaf_size": {"distribution": "uniform", "min": 0.1, "max": 1.0},
        "mapping_corner_leaf_size": {"distribution": "uniform", "min": 0.05, "max": 0.5},
        "mapping_surf_leaf_size": {"distribution": "uniform", "min": 0.1, "max": 1.0},
        # Keyframe thresholds (upstream defaults: dist 1.0m, angle 0.2rad) -- trade off drift
        # vs. compute; no prior finding to bound them.
        "keyframe_dist_threshold": {"distribution": "uniform", "min": 0.1, "max": 2.0},
        "keyframe_angle_threshold": {"distribution": "uniform", "min": 0.05, "max": 0.5},
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

    run = wandb.init(tags=["sweep", "lio_sam", "exp14"], group="lio_sam/exp14/sweep")
    cfg = run.config
    overrides = [
        f"lio_sam.imuAccNoise={cfg.imu_acc_noise}", f"lio_sam.imuGyrNoise={cfg.imu_gyr_noise}",
        f"lio_sam.imuAccBiasN={cfg.imu_acc_bias_n}", f"lio_sam.imuGyrBiasN={cfg.imu_gyr_bias_n}",
        f"lio_sam.odometrySurfLeafSize={cfg.odometry_surf_leaf_size}",
        f"lio_sam.mappingCornerLeafSize={cfg.mapping_corner_leaf_size}",
        f"lio_sam.mappingSurfLeafSize={cfg.mapping_surf_leaf_size}",
        f"lio_sam.surroundingkeyframeAddingDistThreshold={cfg.keyframe_dist_threshold}",
        f"lio_sam.surroundingkeyframeAddingAngleThreshold={cfg.keyframe_angle_threshold}",
    ]
    candidate = apply_overrides(yaml.safe_load(BASE_CONFIG.read_text()), overrides)

    manifest = load_manifest(None)
    data_root = paths.data_root()
    seq = manifest.sequence("exp14")
    split = next((name for name, keys in manifest.split.items() if seq.key in keys), "unassigned")
    store = VerifiedStore(data_root)
    hashes = {p: store.records.get(p, {}).get("digest") for p in (seq.bag, seq.ground_truth_dense)}

    run_dir = init_run(
        paths.runs_root(), "lio_sam", seq.key, split, candidate,
        hypothesis=(f"Bayesian sweep {run.sweep_id} trial {run.id}: DEVIATION from "
                   "docs/protocol.md #6 -- phase-1 manual tuning explicitly skipped for this "
                   "method (confirmed decision), so this search region is wide and centered "
                   "on upstream defaults (config/params.yaml), not phase-1-measured. See "
                   "docs/methods.md 'LIO-SAM integration'."),
        change=", ".join(overrides), parent=RUN_PARENT_ID, label="sweep",
        playback_rate=1.0, dataset_hashes=hashes)

    with tempfile.TemporaryDirectory() as tmp:
        candidate_path = Path(tmp) / "candidate.yaml"
        candidate_path.write_text(yaml.safe_dump(candidate, sort_keys=False))
        raw_tum = run_dir / "raw_lio_sam.tum"
        proc = subprocess.run([  # noqa: PLW1510 -- returncode checked explicitly below
            "docker", "run", "--rm",
            "-v", f"{data_root}:/data/hilti22:ro",
            "-v", f"{run_dir}:/run_out",
            "-v", f"{candidate_path}:/configs/lio_sam/override.yaml:ro",
            "-e", "LIO_SAM_CONFIG=/configs/lio_sam/override.yaml",
            IMAGE, "/run_lio_sam.sh", f"/data/hilti22/{seq.bag}",
            "/run_out/raw_lio_sam.tum", "1200", "1.0",
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
    metrics = {"sequence": seq.key, "split": split, "estimate_frame": "lidar", **result.metrics}
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
    ap.add_argument("--parent-run-id", required=True,
                    help="run id of the kept exp14 baseline from step 7 (docs/journal.md)")
    ap.add_argument("--count", type=int, default=10)
    args = ap.parse_args()

    global RUN_PARENT_ID
    RUN_PARENT_ID = args.parent_run_id

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
