"""Synthetic trajectories for tests."""
import numpy as np
from scipy.spatial.transform import Rotation

from lio_benchmark.trajectory import Trajectory

T0 = 1_649_764_528.0   # epoch seconds, like the Hilti sequences
PERIOD = 60.0


def pose_at(t) -> Trajectory:
    """A fixed smooth 3D path with changing heading and some roll/pitch, as a function of
    absolute time (non-degenerate for alignment; about 1 m/s)."""
    t = np.asarray(t, dtype=float)
    s = (t - T0) / PERIOD * 2 * np.pi
    p = np.column_stack([10 * np.cos(s), 6 * np.sin(s), 1.5 * np.sin(2 * s)])
    euler = np.column_stack([0.1 * np.sin(3 * s), 0.05 * np.cos(2 * s), s + np.pi / 2])
    return Trajectory(t, p, Rotation.from_euler("xyz", euler).as_quat())


def loop(duration=PERIOD, rate=10.0, offset=0.0) -> Trajectory:
    """`pose_at` sampled at `rate` Hz from T0 + offset for `duration` seconds."""
    return pose_at(T0 + offset + np.arange(0, duration - 1e-9, 1.0 / rate))


def rigidly_moved(traj: Trajectory, R: Rotation, t) -> Trajectory:
    """Pre-multiply every pose by the world transform (R, t): the same motion in another frame."""
    return Trajectory(traj.t.copy(), R.apply(traj.p) + t, (R * traj.rotations).as_quat())
