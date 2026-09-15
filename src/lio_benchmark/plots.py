"""Evaluation plots (matplotlib, headless)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

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
