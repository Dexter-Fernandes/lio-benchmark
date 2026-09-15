#!/usr/bin/env python
"""Open a run's map.pcd in Open3D's interactive viewer (rotate/zoom/pan, Q to quit).

Usage: uv run python scripts/view_pcd.py <run_id | path/to/map.pcd> [--voxel 0.05]
"""
import argparse
import sys
from pathlib import Path

import open3d as o3d

from lio_benchmark import paths


def resolve(arg: str) -> Path:
    p = Path(arg)
    if p.suffix == ".pcd":
        return p
    return paths.runs_root() / arg / "map.pcd"  # bare run_id


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target", help="run_id (resolves to runs/<id>/map.pcd) or a direct .pcd path")
    ap.add_argument("--voxel", type=float, default=0.0, help="downsample voxel size in m, e.g. 0.05 for faster loading")
    args = ap.parse_args()

    pcd_path = resolve(args.target)
    if not pcd_path.exists():
        sys.exit(f"not found: {pcd_path}")

    print(f"loading {pcd_path} ({pcd_path.stat().st_size / 1e6:.0f} MB)...")
    pcd = o3d.io.read_point_cloud(str(pcd_path))
    if args.voxel > 0:
        pcd = pcd.voxel_down_sample(args.voxel)
    print(f"{len(pcd.points):,} points")
    o3d.visualization.draw_geometries([pcd], window_name=str(pcd_path))


if __name__ == "__main__":
    main()
