"""Evaluation plots (matplotlib, headless) and point-cloud map renders (Open3D, headless EGL)."""
from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .evaluation import EvalResult  # noqa: E402
from .trajectory import Trajectory  # noqa: E402


def plot_evaluation(gt: Trajectory, result: EvalResult, out_dir: Path, title: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if result.aligned is None:
        return
    t0 = gt.t[0]

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot(gt.p[:, 0], gt.p[:, 1], color="0.35", lw=1.5, label="ground truth")
    ax.plot(result.aligned.p[:, 0], result.aligned.p[:, 1], lw=1.2, label="estimate (SE(3)-aligned)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_title(f"{title}: top view")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(out_dir / "trajectory_xy.png", dpi=120)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(8, 5), sharex=True)
    ts = result.assoc.est.t - t0
    axes[0].plot(ts, result.ate_trans, lw=1)
    axes[0].set_ylabel("ATE trans [m]")
    axes[1].plot(ts, result.ate_rot, lw=1)
    axes[1].set_ylabel("ATE rot [deg]")
    axes[1].set_xlabel("time since ground-truth start [s]")
    cov = result.metrics["coverage"]["coverage"]
    axes[0].set_title(f"{title}: coverage {cov:.1%}, status {result.metrics['status']}")
    for ax in axes:
        ax.set_xlim(0, gt.t[-1] - t0)
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "ate_over_time.png", dpi=120)
    plt.close(fig)


def plot_pcd_map(pcd_path: Path, out_png: Path, title: str, voxel_size: float = 0.05) -> None:
    """Top-down orthographic render of a method's saved map, colored by height."""
    import open3d as o3d

    pcd = o3d.io.read_point_cloud(str(pcd_path))
    if not pcd.has_points():
        return
    pcd = pcd.voxel_down_sample(voxel_size)
    points = np.asarray(pcd.points)

    z = points[:, 2]
    z_norm = (z - z.min()) / max(z.max() - z.min(), 1e-6)
    pcd.colors = o3d.utility.Vector3dVector(plt.get_cmap("viridis")(z_norm)[:, :3])

    margin = 1.0
    x_min, y_min, _ = points.min(axis=0) - margin
    x_max, y_max, _ = points.max(axis=0) + margin
    z_min, z_max = z.min() - margin, z.max() + margin
    width, height = 1000, max(1, int(1000 * (y_max - y_min) / max(x_max - x_min, 1e-6)))

    renderer = o3d.visualization.rendering.OffscreenRenderer(width, height)
    renderer.scene.set_background([0.05, 0.05, 0.05, 1.0])
    material = o3d.visualization.rendering.MaterialRecord()
    material.shader = "defaultUnlit"
    material.point_size = 2.0
    renderer.scene.add_geometry("map", pcd, material)
    center = [(x_min + x_max) / 2, (y_min + y_max) / 2, 0.0]
    renderer.scene.camera.look_at(center, [*center[:2], z_max + 10], [0, 1, 0])
    renderer.scene.camera.set_projection(
        o3d.visualization.rendering.Camera.Projection.Ortho,
        x_min - center[0], x_max - center[0], y_min - center[1], y_max - center[1],
        0.1, (z_max - z_min) + 20)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    o3d.io.write_image(str(out_png), renderer.render_to_image())
