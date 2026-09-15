"""`lio-bench`: data management, inspection, evaluation and run records for lio-benchmark."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import paths


def _manifest(args):
    from .manifest import load_manifest
    return load_manifest(args.manifest)


def _data_root(args) -> Path:
    return Path(args.data_root) if args.data_root else paths.data_root()


def _split_of(manifest, key: str) -> str:
    return next((name for name, keys in manifest.split.items() if key in keys), "unassigned")


# ---- data ------------------------------------------------------------------------------------

def cmd_data_status(args) -> int:
    from .download import VerifiedStore, part_path
    m, root = _manifest(args), _data_root(args)
    store = VerifiedStore(root)
    print(f"data root: {root}\nrevision:  {m.revision}\n")
    for group in m.groups:
        default = " (default)" if group in m.default_groups else ""
        print(f"[{group}]{default}")
        for e in m.select([group]):
            file = root / e.path
            if store.is_current(e, file):
                state = "verified"
            elif file.exists():
                state = "present, unverified"
            elif part_path(file).exists():
                state = f"partial {part_path(file).stat().st_size / e.size:.1%}"
            else:
                state = "missing"
            print(f"  {state:22s} {e.size / 1e9:8.3f} GB  {e.path}")
    print("\n[derived rosbag2]")
    for s in m.sequences.values():
        prov = paths.provenance_dir(root) / "conversions" / f"{s.name}.json"
        if prov.exists():
            rec = json.loads(prov.read_text())
            state = "equivalent" if rec.get("equivalent") else "CHECK FAILED"
        else:
            state = "present, unchecked" if (root / s.rosbag2).exists() else "missing"
        print(f"  {state:22s} {'':11s} {s.rosbag2}")
    return 0


def cmd_data_download(args) -> int:
    from .download import DownloadError, download
    try:
        statuses = download(_manifest(args), _data_root(args), args.groups or None)
    except DownloadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0 if all(s.ok for s in statuses) else 1


def cmd_data_verify(args) -> int:
    from .download import verify
    statuses = verify(_manifest(args), _data_root(args), args.groups or None, rehash=args.rehash)
    for s in statuses:
        print(f"{s.state:14s} {s.entry.path}{'  ' + s.detail if s.detail else ''}")
    bad = [s for s in statuses if not s.ok]
    print(f"\n{len(statuses) - len(bad)}/{len(statuses)} ok")
    return 1 if bad else 0


def cmd_data_convert(args) -> int:
    from .convert import ConversionError, convert_sequence
    from .download import VerifiedStore
    from .frames import dataset_config
    m, root = _manifest(args), _data_root(args)
    seq = m.sequence(args.sequence)
    bag_entry = m.entry(seq.bag)
    if not args.check_only and not VerifiedStore(root).is_current(bag_entry, root / seq.bag):
        print(f"error: {seq.bag} is not verified; run `lio-bench data verify` first", file=sys.stderr)
        return 1
    topics = [dataset_config()["topics"]["lidar"], dataset_config()["topics"]["imu"]]
    try:
        rec = convert_sequence(root, seq.name, seq.bag, seq.rosbag2, topics, args.check_only, args.dst_version)
    except ConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for topic, s in rec["source_summary"]["topics"].items():
        d = rec["destination_summary"]["topics"][topic]
        print(f"  {topic:20s} src {s['count']:6d}  dst {d['count']:6d}  content "
              f"{'match' if s['content_sha256'] == d['content_sha256'] else 'DIFFERS'}")
    print(f"  rosbag2 metadata: {rec['metadata']}")
    print("equivalent" if rec["equivalent"] else "NOT EQUIVALENT:\n  " + "\n  ".join(rec["problems"]))
    return 0 if rec["equivalent"] else 1


# ---- inspect / ground truth ------------------------------------------------------------------

def cmd_inspect(args) -> int:
    from .inspection import inspect_sequence, summary_lines
    report = inspect_sequence(_manifest(args).sequence(args.sequence), _data_root(args),
                              rest_seconds=args.rest_seconds)
    print("\n".join(summary_lines(report)))
    print(f"\nwrote {report['_written_to']}")
    return 0


def cmd_imu_noise(args) -> int:
    from .download import write_json_atomic
    from .inspection import imu_noise
    from .paths import provenance_dir
    root = _data_root(args)
    report = imu_noise(root / args.bag)
    out = provenance_dir(root) / "imu_noise.json"
    write_json_atomic(out, report)
    print(f"gyr_cov {report['gyr_cov']:.3e} (rad/s)^2, acc_cov {report['acc_cov']:.3e} (m/s^2)^2, "
          f"from {report['samples']} samples")
    print(f"wrote {out}")
    return 0


def cmd_gt_check(args) -> int:
    import numpy as np
    from .trajectory import load_sparse, load_tum
    m, root = _manifest(args), _data_root(args)
    keys = [args.sequence] if args.sequence else list(m.sequences)
    for key in keys:
        s = m.sequence(key)
        gt = load_tum(root / s.ground_truth_dense)
        sp = load_sparse(root / s.ground_truth_sparse)
        dt = np.diff(gt.t)
        inside = ((sp.t >= gt.t[0]) & (sp.t <= gt.t[-1])).sum()
        print(f"{s.key} ({_split_of(m, s.key)}): {len(gt)} poses, {gt.duration:.1f} s, "
              f"{(len(gt) - 1) / gt.duration:.2f} Hz, max gap {dt.max():.3f} s, "
              f"path {np.linalg.norm(np.diff(gt.p, axis=0), axis=1).sum():.1f} m; "
              f"sparse {len(sp.t)} points, {inside} inside dense span")
    return 0


# ---- evaluation ------------------------------------------------------------------------------

def cmd_eval(args) -> int:
    from .evaluation import EvalConfig, evaluate
    from .frames import dataset_config, extrinsic, to_imu_frame
    from .plots import plot_evaluation
    from .trajectory import load_sparse, load_tum, save_tum
    m, root = _manifest(args), _data_root(args)
    seq = m.sequence(args.sequence)
    cfg = EvalConfig.from_yaml(args.config)
    gt = load_tum(root / seq.ground_truth_dense)
    sparse = load_sparse(root / seq.ground_truth_sparse)
    est = load_tum(args.estimate)
    if args.frame == "lidar":
        est = to_imu_frame(est, extrinsic(dataset_config(), "T_I_L"))

    result = evaluate(gt, est, cfg, sparse=sparse)
    metrics = {"sequence": seq.key, "split": _split_of(m, seq.key), "estimate": str(args.estimate),
               "estimate_frame": args.frame, "eval_config_file": str(args.config), **result.metrics}
    out = Path(args.out) if args.out else Path(args.estimate).parent
    out.mkdir(parents=True, exist_ok=True)
    if args.run_dir:
        from .tracking import update_run, write_metrics
        out = Path(args.run_dir)
        write_metrics(out, metrics)
        save_tum(out / "trajectory.tum", est)
        update_run(out, status=metrics["status"])
    else:
        (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    if not args.no_plots:
        plot_evaluation(gt, result, out, f"{seq.key} {Path(args.estimate).stem}")
        pcd = Path(args.estimate).parent / "map.pcd"
        if pcd.exists():
            from .plots import plot_pcd_map
            plot_pcd_map(pcd, out / "map.png", f"{seq.key} {Path(args.estimate).stem}")

    c = metrics["coverage"]
    print(f"status {metrics['status']}  coverage {c['coverage']:.1%} ({c['n_associated']}/{c['n_gt']})"
          + (f"  reasons: {'; '.join(metrics['reasons'])}" if metrics["reasons"] else ""))
    if metrics["ate"]:
        a = metrics["ate"]["trans_m"]
        print(f"ATE  rmse {a['rmse']:.4f} m  median {a['median']:.4f}  p95 {a['p95']:.4f}  "
              f"rot rmse {metrics['ate']['rot_deg']['rmse']:.3f} deg")
        for name, r in metrics["rpe"].items():
            if r["trans_m"]["n"]:
                print(f"RPE {name:>4s} trans rmse {r['trans_m']['rmse']:.4f} m  rot rmse "
                      f"{r['rot_deg']['rmse']:.3f} deg  ({r['trans_m']['n']} pairs)")
    print(f"wrote {out}")
    return 0 if metrics["status"] != "failed" else 2


# ---- runs ------------------------------------------------------------------------------------

def cmd_run_init(args) -> int:
    import yaml
    from .download import VerifiedStore
    from .tracking import init_run
    m, root = _manifest(args), _data_root(args)
    seq = m.sequence(args.sequence)
    config = yaml.safe_load(Path(args.config).read_text()) if args.config else {}
    store = VerifiedStore(root)
    hashes = {p: store.records.get(p, {}).get("digest") for p in (seq.bag, seq.ground_truth_dense)}
    run_dir = init_run(Path(args.runs_root) if args.runs_root else paths.runs_root(), args.method,
                       seq.key, _split_of(m, seq.key), config, hypothesis=args.hypothesis,
                       change=args.change, parent=args.parent, label=args.label,
                       playback_rate=args.playback_rate, dataset_hashes=hashes)
    print(run_dir)
    return 0


def cmd_run_close(args) -> int:
    from .tracking import update_run
    run = update_run(Path(args.run_dir), interpretation=args.interpretation, decision=args.decision)
    print(f"{run['run_id']}: {run['status']}, decision {run['decision']}")
    return 0


def cmd_view(args) -> int:
    import open3d as o3d
    pcd_path = Path(args.target)
    if pcd_path.suffix != ".pcd":
        pcd_path = paths.runs_root() / args.target / "map.pcd"  # bare run_id
    if not pcd_path.exists():
        print(f"error: not found: {pcd_path}", file=sys.stderr)
        return 1

    print(f"loading {pcd_path} ({pcd_path.stat().st_size / 1e6:.0f} MB)...")
    pcd = o3d.io.read_point_cloud(str(pcd_path))
    if args.voxel > 0:
        pcd = pcd.voxel_down_sample(args.voxel)
    print(f"{len(pcd.points):,} points")
    o3d.visualization.draw_geometries([pcd], window_name=str(pcd_path))
    return 0


def cmd_log(args) -> int:
    from .tracking import log_to_wandb
    try:
        print(log_to_wandb(Path(args.run_dir)))
    except ImportError:
        print("error: wandb is not installed; `uv sync`", file=sys.stderr)
        return 1
    return 0


def cmd_report(args) -> int:
    from .tracking import build_report
    try:
        print(build_report(args.project, args.entity))
    except ImportError:
        print("error: wandb is not installed; `uv sync`", file=sys.stderr)
        return 1
    return 0


# ---- parser ----------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="lio-bench", description=__doc__)
    ap.add_argument("--manifest", default=None, help="manifest YAML (default: manifests/hilti22.yaml)")
    ap.add_argument("--data-root", default=None, help="dataset root (default: $LIO_DATA_ROOT)")
    sub = ap.add_subparsers(dest="command", required=True)

    data = sub.add_parser("data", help="download, verify and convert dataset files").add_subparsers(
        dest="data_command", required=True)
    p = data.add_parser("status", help="show what is present, partial, verified or missing")
    p.set_defaults(func=cmd_data_status)
    p = data.add_parser("download", help="fetch selected groups (resumable, verified)")
    p.add_argument("--groups", nargs="+", help="manifest groups (default: manifest default_groups)")
    p.set_defaults(func=cmd_data_download)
    p = data.add_parser("verify", help="check sizes and hashes against the manifest")
    p.add_argument("--groups", nargs="+")
    p.add_argument("--rehash", action="store_true", help="re-hash even files recorded as verified")
    p.set_defaults(func=cmd_data_verify)
    p = data.add_parser("convert", help="ROS 1 bag -> rosbag2 MCAP (LiDAR + IMU) with equivalence check")
    p.add_argument("sequence", help="e.g. exp14")
    p.add_argument("--check-only", action="store_true", help="only compare an existing conversion")
    p.add_argument("--dst-version", type=int, default=None, help="rosbag2 metadata version (e.g. for Humble)")
    p.set_defaults(func=cmd_data_convert)

    p = sub.add_parser("inspect", help="measure topics, point layout, timing, IMU and GT coverage")
    p.add_argument("sequence")
    p.add_argument("--rest-seconds", type=float, default=1.0, help="initial window assumed stationary")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("imu-noise", help="measure per-axis IMU white-noise std/variance from a static bag")
    p.add_argument("--bag", default="calibration/imu_noise_calibration.bag", help="path relative to the data root")
    p.set_defaults(func=cmd_imu_noise)

    gt = sub.add_parser("gt", help="ground-truth checks").add_subparsers(dest="gt_command", required=True)
    p = gt.add_parser("check", help="validate dense and sparse ground truth (no bag needed)")
    p.add_argument("sequence", nargs="?")
    p.set_defaults(func=cmd_gt_check)

    p = sub.add_parser("eval", help="evaluate an estimated trajectory (TUM) against ground truth")
    p.add_argument("sequence")
    p.add_argument("estimate", help="TUM file: t x y z qx qy qz qw")
    p.add_argument("--frame", choices=["imu", "lidar"], required=True,
                   help="body frame of the estimate; lidar poses are converted with T_I_L")
    p.add_argument("--config", default=str(paths.repo_root() / "configs/eval/default.yaml"))
    p.add_argument("--out", help="output directory (default: next to the estimate)")
    p.add_argument("--run-dir", help="write metrics into this run record instead")
    p.add_argument("--no-plots", action="store_true")
    p.set_defaults(func=cmd_eval)

    run = sub.add_parser("run", help="create and close run records").add_subparsers(dest="run_command", required=True)
    p = run.add_parser("init", help="create a run directory with config, environment and intent")
    p.add_argument("--method", required=True)
    p.add_argument("--sequence", required=True)
    p.add_argument("--config", help="resolved method configuration (YAML)")
    p.add_argument("--hypothesis", required=True)
    p.add_argument("--change", required=True, help="exact change relative to the parent run")
    p.add_argument("--parent", help="parent run id")
    p.add_argument("--label", default="")
    p.add_argument("--playback-rate", type=float)
    p.add_argument("--runs-root")
    p.set_defaults(func=cmd_run_init)
    p = run.add_parser("close", help="record interpretation and keep/revert/investigate decision")
    p.add_argument("run_dir")
    p.add_argument("--interpretation", required=True)
    p.add_argument("--decision", required=True, choices=["keep", "revert", "investigate"])
    p.set_defaults(func=cmd_run_close)

    p = sub.add_parser("log", help="mirror a run record to W&B (online by default)")
    p.add_argument("run_dir")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("report", help="create/update a W&B report comparing every logged run")
    p.add_argument("--project", help="default: $WANDB_PROJECT or .env, else 'lio-benchmark'")
    p.add_argument("--entity", help="default: $WANDB_ENTITY or .env, else your default entity")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("view", help="open a run's map.pcd in Open3D's interactive viewer")
    p.add_argument("target", help="run_id (resolves to runs/<id>/map.pcd) or a direct .pcd path")
    p.add_argument("--voxel", type=float, default=0.0, help="downsample voxel size in m, e.g. 0.05")
    p.set_defaults(func=cmd_view)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
