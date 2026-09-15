"""Trajectory I/O and validation.

Dense trajectories use the TUM format, one pose per line: `t x y z qx qy qz qw`, with `t` in
seconds and the pose T_W_B of the body frame B in the world W. The Hilti dense ground truth
(`*_imu.txt`) is in this format with B = IMU.

The sparse Hilti control-point files (`*_imu_3dof.txt`) carry a header `# timestamp_s id x y z`
but their rows actually have eight columns, `t x y z 0 0 0 1` (an identity quaternion, which
also confirms the x, y, z, w order). `load_sparse` reads the rows as they are.

`load_tum` is adapted from ranger-lio's scripts/gt_to_tum.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

QUAT_NORM_TOL = 1e-3

# Epoch-time magnitude thresholds for detecting the unit of absolute timestamps. An epoch
# time in 2000-2100 is ~1e9 s, ~1e12 ms, ~1e15 us or ~1e18 ns.
_UNIT_THRESHOLDS = [(1e17, "ns", 1e-9), (1e14, "us", 1e-6), (1e11, "ms", 1e-3)]


class TrajectoryError(ValueError):
    pass


@dataclass
class Trajectory:
    t: np.ndarray          # (N,) seconds
    p: np.ndarray          # (N, 3) positions
    q: np.ndarray          # (N, 4) quaternions x, y, z, w

    def __post_init__(self):
        self.t = np.asarray(self.t, dtype=float).reshape(-1)
        self.p = np.asarray(self.p, dtype=float).reshape(-1, 3)
        self.q = np.asarray(self.q, dtype=float).reshape(-1, 4)
        if not (len(self.t) == len(self.p) == len(self.q)):
            raise TrajectoryError("t, p and q lengths differ")

    def __len__(self) -> int:
        return len(self.t)

    @property
    def rotations(self) -> Rotation:
        return Rotation.from_quat(self.q)

    @property
    def duration(self) -> float:
        return float(self.t[-1] - self.t[0]) if len(self) else 0.0

    def subset(self, mask) -> "Trajectory":
        return Trajectory(self.t[mask], self.p[mask], self.q[mask])

    def as_array(self) -> np.ndarray:
        return np.column_stack([self.t, self.p, self.q])


def detect_time_unit(t) -> tuple[str, float]:
    """(unit, factor to seconds) for absolute epoch timestamps."""
    t = np.asarray(t, dtype=float)
    if not len(t):
        return "s", 1.0
    m = float(np.median(np.abs(t)))
    for threshold, unit, factor in _UNIT_THRESHOLDS:
        if m > threshold:
            return unit, factor
    return "s", 1.0


def validate(traj: Trajectory, name: str = "trajectory") -> None:
    if len(traj) == 0:
        raise TrajectoryError(f"{name}: empty")
    arr = traj.as_array()
    if not np.all(np.isfinite(arr)):
        raise TrajectoryError(f"{name}: non-finite values")
    norms = np.linalg.norm(traj.q, axis=1)
    if not np.allclose(norms, 1.0, atol=QUAT_NORM_TOL):
        raise TrajectoryError(f"{name}: quaternions not unit norm (min {norms.min():.4f}, max {norms.max():.4f})")
    if np.any(np.diff(traj.t) <= 0):
        i = int(np.argmax(np.diff(traj.t) <= 0))
        raise TrajectoryError(f"{name}: timestamps not strictly increasing at row {i + 1}")


def load_tum(path, convert_units: bool = True, check: bool = True) -> Trajectory:
    """Load a TUM file. Timestamps in ns/us/ms are converted to seconds when detected."""
    a = np.loadtxt(path, comments="#", ndmin=2)
    if a.shape[1] != 8:
        raise TrajectoryError(f"{path}: expected 8 columns (t x y z qx qy qz qw), got {a.shape[1]}")
    t = a[:, 0]
    if convert_units:
        _, factor = detect_time_unit(t)
        t = t * factor
    traj = Trajectory(t, a[:, 1:4], a[:, 4:8])
    if check:
        validate(traj, str(path))
    return traj


def save_tum(path, traj: Trajectory) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(path, traj.as_array(), fmt="%.9f %.6f %.6f %.6f %.9f %.9f %.9f %.9f",
               header="t x y z qx qy qz qw")


@dataclass
class SparsePoints:
    t: np.ndarray          # (M,) seconds
    p: np.ndarray          # (M, 3) positions of the IMU origin in the world


def load_sparse(path) -> SparsePoints:
    """Load a Hilti `*_3dof.txt` control-point file (4, 5 or 8 columns; see module docstring)."""
    a = np.loadtxt(path, comments="#", ndmin=2)
    if a.shape[1] == 8:      # t x y z qx qy qz qw (what the files actually contain)
        t, p = a[:, 0], a[:, 1:4]
    elif a.shape[1] == 5:    # t id x y z (what the header describes)
        t, p = a[:, 0], a[:, 2:5]
    elif a.shape[1] == 4:    # t x y z
        t, p = a[:, 0], a[:, 1:4]
    else:
        raise TrajectoryError(f"{path}: unsupported sparse layout with {a.shape[1]} columns")
    if np.any(np.diff(t) <= 0):
        raise TrajectoryError(f"{path}: timestamps not strictly increasing")
    return SparsePoints(t, p)
