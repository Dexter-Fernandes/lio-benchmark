"""Minimal rigid transforms.

Convention (as in ranger-lio docs/00-notation.md, from which this is adapted): T_A_B maps
points expressed in frame B into frame A, p_A = R_A_B p_B + t_A_B, and composes as
T_A_C = T_A_B * T_B_C. Quaternions are (x, y, z, w) everywhere, as in ROS, TUM files and the
Hilti calibration YAML.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation


class SE3:
    __slots__ = ("R", "t")

    def __init__(self, R=None, t=None):
        self.R = np.eye(3) if R is None else np.asarray(R, dtype=float)
        self.t = np.zeros(3) if t is None else np.asarray(t, dtype=float)

    @classmethod
    def from_xyzw(cls, q_xyzw, t) -> "SE3":
        return cls(Rotation.from_quat(np.asarray(q_xyzw, dtype=float)).as_matrix(), t)

    @classmethod
    def from_matrix(cls, T) -> "SE3":
        T = np.asarray(T, dtype=float)
        return cls(T[:3, :3], T[:3, 3])

    def matrix(self) -> np.ndarray:
        T = np.eye(4)
        T[:3, :3], T[:3, 3] = self.R, self.t
        return T

    def xyzw(self) -> np.ndarray:
        return Rotation.from_matrix(self.R).as_quat()

    def __mul__(self, other: "SE3") -> "SE3":          # T_A_C = T_A_B * T_B_C
        return SE3(self.R @ other.R, self.R @ other.t + self.t)

    def inverse(self) -> "SE3":                        # T_B_A = (R^T, -R^T t)
        return SE3(self.R.T, -self.R.T @ self.t)

    def act(self, p) -> np.ndarray:                    # p_A = R p_B + t, p may be (3,) or (N, 3)
        p = np.asarray(p, dtype=float)
        return p @ self.R.T + self.t

    def __repr__(self) -> str:
        return f"SE3(t={np.round(self.t, 6).tolist()}, q_xyzw={np.round(self.xyzw(), 6).tolist()})"


def rotation_angle_deg(R) -> np.ndarray:
    """Rotation angle of one (3, 3) or many (N, 3, 3) rotation matrices, in degrees."""
    R = np.asarray(R, dtype=float)
    return np.degrees(Rotation.from_matrix(R).magnitude())
