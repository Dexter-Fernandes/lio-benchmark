"""Madgwick AHRS filter: synthesizes an orientation quaternion from accel+gyro only.

Hilti's /alphasense/imu ships an all-zero orientation quaternion with
orientation_covariance[0] = 0 (docs/dataset.md) -- not flagged as ROS's "-1 unknown", so
LIO-SAM would silently consume a degenerate quaternion. Worse, LIO-SAM's own imuConverter()
(TixiaoShan/LIO-SAM include/utility.h) checks the rotated quaternion's norm and calls
ros::shutdown() with "Invalid quaternion, please use a 9-axis IMU!" if it's near zero -- a
raw all-zero passthrough would crash the node outright, not just degrade accuracy.

This is a standard 6-axis Madgwick filter (Madgwick 2010, "An efficient orientation filter
for inertial and inertial/magnetic sensor arrays", gradient-descent variant without the
magnetometer term). It is a documented, sensor-only dataset adapter: it reads only this
IMU's own angular_velocity/linear_acceleration and never reads or is given ground truth.

Without a magnetometer, yaw is unobservable and free-drifts from the initial value -- this
filter only ever supplies a *local* gravity-referenced roll/pitch (with a consistent, if
arbitrary, initial yaw), which is what LIO-SAM's extrinsicRPY rotation and imuRPYWeight
(0.01, i.e. a low-confidence prior on mapOptimization's RPY, not a hard constraint) actually
need it for -- not a global heading reference. This is recorded, not hidden.

beta = 0.1 is Madgwick's own paper-recommended value for a MEMS-class IMU; docs/dataset.md
measures 399.2 Hz for /alphasense/imu, well within the filter's assumptions.
"""
from __future__ import annotations

import numpy as np

DEFAULT_BETA = 0.1


def initial_quaternion(accel: np.ndarray) -> np.ndarray:
    """Seed quaternion [w,x,y,z] whose body-frame accel direction maps to the filter's earth
    reference [0,0,1] (see madgwick_update's docstring for the convention).

    Starting the filter from a fixed identity quaternion is a known singularity for gradient
    descent whenever the true attitude happens to be near-antipodal to that reference (exactly
    the case here: this IMU mounts with its "up" reaction force along -z, docs/dataset.md's
    "up -z" at-rest reading) -- the gradient vanishes and the filter drifts unpredictably
    instead of converging. Seeding from the first accelerometer reading avoids it.
    """
    a_norm = np.linalg.norm(accel)
    if a_norm == 0:
        return np.array([1.0, 0.0, 0.0, 0.0])
    a = accel / a_norm
    ref = np.array([0.0, 0.0, 1.0])
    c = np.dot(a, ref)
    if c < -1 + 1e-8:
        # antipodal: any axis perpendicular to `a` gives a valid 180-degree rotation
        axis = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, [0.0, 1.0, 0.0])
        axis /= np.linalg.norm(axis)
        return np.array([0.0, *axis])
    v = np.cross(a, ref)
    q = np.array([1 + c, *v])
    return q / np.linalg.norm(q)


def madgwick_update(q: np.ndarray, gyro: np.ndarray, accel: np.ndarray, dt: float,
                     beta: float = DEFAULT_BETA) -> np.ndarray:
    """One filter step. `q` is [w, x, y, z]; `gyro` rad/s; `accel` m/s^2 (or any consistent unit,
    only its direction is used). Returns the updated, unit-normalized quaternion."""
    q0, q1, q2, q3 = q
    gx, gy, gz = gyro

    qdot = 0.5 * np.array([
        -q1 * gx - q2 * gy - q3 * gz,
        q0 * gx + q2 * gz - q3 * gy,
        q0 * gy - q1 * gz + q3 * gx,
        q0 * gz + q1 * gy - q2 * gx,
    ])

    a_norm = np.linalg.norm(accel)
    if a_norm > 0:
        ax, ay, az = accel / a_norm

        f = np.array([
            2 * (q1 * q3 - q0 * q2) - ax,
            2 * (q0 * q1 + q2 * q3) - ay,
            2 * (0.5 - q1 * q1 - q2 * q2) - az,
        ])
        j = np.array([
            [-2 * q2, 2 * q3, -2 * q0, 2 * q1],
            [2 * q1, 2 * q0, 2 * q3, 2 * q2],
            [0, -4 * q1, -4 * q2, 0],
        ])
        step = j.T @ f
        step_norm = np.linalg.norm(step)
        if step_norm > 0:
            step /= step_norm
        qdot -= beta * step

    q_new = q + qdot * dt
    norm = np.linalg.norm(q_new)
    return q_new / norm if norm > 0 else np.array([1.0, 0.0, 0.0, 0.0])
