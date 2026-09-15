"""Sensor frames and the conversion of estimator output into the ground-truth frame.

Hilti-Oxford ground truth is T_W_I: the IMU frame I in a world frame W. Estimators report the
pose of some body frame S (often the LiDAR L, sometimes the IMU) in their own world frame W'.
Before evaluation every estimate is converted to the IMU pose in W':

    T_W'_I = T_W'_S * T_S_I = T_W'_S * (T_I_S)^-1

W' and W differ by a rigid transform, which the SE(3) alignment in evaluation.py removes. The
calibration file gives T_I_L as the "PandarXT-32" extrinsics with `parent: imu`.

`check_lidar_extrinsics` is adapted from ranger-lio's scripts/gt_to_tum.py.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml
from scipy.spatial.transform import Rotation

from .paths import repo_root
from .se3 import SE3
from .trajectory import Trajectory

DATASET_CONFIG = Path("configs/dataset/hilti22.yaml")


def dataset_config(path: Path | None = None) -> dict:
    return yaml.safe_load((Path(path) if path else repo_root() / DATASET_CONFIG).read_text())


def extrinsic(cfg: dict, name: str) -> SE3:
    """An extrinsic from the dataset config, e.g. name='T_I_L'."""
    e = cfg["extrinsics"][name]
    return SE3.from_xyzw(e["quaternion_xyzw"], e["translation_m"])


def lidar_extrinsic_from_calibration(calibration_yaml: Path) -> SE3:
    """T_I_L read verbatim from the dataset's lidar_calibration.yaml."""
    cal = yaml.safe_load(Path(calibration_yaml).read_text())
    lidar = cal["sensors"]["PandarXT-32"]
    if lidar["parent"] != "imu":
        raise ValueError(f"expected PandarXT-32 parent 'imu', got {lidar['parent']!r}")
    ext = lidar["extrinsics"]
    return SE3.from_xyzw(ext["quaternion"], ext["translation"])


def check_lidar_extrinsics(T_I_L: SE3) -> None:
    """Known-answer checks for the calibration quaternion convention.

    (0.7071068, -0.7071068, 0, 0) read as (x, y, z, w) is a 180 degree rotation about
    (1, -1, 0)/sqrt(2): it maps z_L -> -z_I and x_L -> -y_I. Read as (w, x, y, z) it would be a
    90 degree rotation about -x, mapping z_L -> +y_I, so a wrong quaternion order fails here.
    """
    np.testing.assert_allclose(T_I_L.R @ [0, 0, 1.0], [0, 0, -1], atol=1e-6,
                               err_msg="T_I_L quaternion order/convention wrong")
    np.testing.assert_allclose(T_I_L.R @ [1.0, 0, 0], [0, -1, 0], atol=1e-6)
    np.testing.assert_allclose((T_I_L * T_I_L.inverse()).matrix(), np.eye(4), atol=1e-9)


def transform_body(traj: Trajectory, T_S_B: SE3) -> Trajectory:
    """Re-express a trajectory of body frame S as one of body frame B: T_W_B = T_W_S * T_S_B."""
    R_W_S = traj.rotations
    p = traj.p + R_W_S.apply(T_S_B.t)
    q = (R_W_S * Rotation.from_matrix(T_S_B.R)).as_quat()
    return Trajectory(traj.t.copy(), p, q)


def to_imu_frame(traj: Trajectory, T_I_S: SE3) -> Trajectory:
    """Estimator poses of sensor S -> IMU poses, using the extrinsic T_I_S."""
    return transform_body(traj, T_I_S.inverse())
