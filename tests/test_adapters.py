"""FAST-LIO2 input adapter: Hilti's absolute per-point timestamp -> FAST-LIO2's relative time.

Synthetic points mirror the measured PandarXT-32 layout (docs/dataset.md): x, y, z, intensity
as f4, absolute `timestamp` as f8 (first point ~header stamp +1us, scan spread ~0.1s), `ring`
as u2.
"""
import numpy as np

from adapters.fast_lio2.pointcloud_adapter import to_fast_lio2_points
from adapters.lio_sam.orientation_filter import initial_quaternion, madgwick_update
from adapters.lio_sam.pointcloud_adapter import to_lio_sam_points

HEADER_STAMP = 1_649_764_528.000000


def hilti_points(n=5, header_stamp=HEADER_STAMP, spread=0.1):
    pts = np.zeros(n, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("intensity", "<f4"),
                             ("timestamp", "<f8"), ("ring", "<u2")])
    pts["x"] = np.arange(n, dtype="f4")
    pts["y"] = np.arange(n, dtype="f4") * 2
    pts["z"] = 1.0
    pts["intensity"] = np.arange(n, dtype="f4") * 10
    pts["timestamp"] = header_stamp + 1e-6 + np.linspace(0, spread, n)
    pts["ring"] = np.arange(n) % 32
    return pts


def test_time_field_is_relative_to_header_stamp():
    pts = hilti_points()
    out = to_fast_lio2_points(pts, HEADER_STAMP)
    expected = (pts["timestamp"] - HEADER_STAMP).astype(np.float32)
    np.testing.assert_allclose(out["time"], expected, atol=1e-7)


def test_xyz_intensity_ring_pass_through_unchanged():
    pts = hilti_points()
    out = to_fast_lio2_points(pts, HEADER_STAMP)
    np.testing.assert_array_equal(out["x"], pts["x"])
    np.testing.assert_array_equal(out["y"], pts["y"])
    np.testing.assert_array_equal(out["z"], pts["z"])
    np.testing.assert_array_equal(out["intensity"], pts["intensity"])
    np.testing.assert_array_equal(out["ring"], pts["ring"])


def test_output_dtype_matches_fast_lio2_velodyne_layout():
    out = to_fast_lio2_points(hilti_points(), HEADER_STAMP)
    assert out.dtype.names == ("x", "y", "z", "intensity", "ring", "time")
    assert out.dtype["time"] == np.dtype("<f4")
    assert out.dtype["ring"] == np.dtype("<u2")


# --- LIO-SAM: pointcloud adapter -------------------------------------------------------------
# LIO-SAM's VelodynePointXYZIRT (src/imageProjection.cpp) is byte-identical to FAST-LIO2's
# velodyne layout, so these mirror the tests above exactly, just against to_lio_sam_points.

def test_lio_sam_time_field_is_relative_to_header_stamp():
    pts = hilti_points()
    out = to_lio_sam_points(pts, HEADER_STAMP)
    expected = (pts["timestamp"] - HEADER_STAMP).astype(np.float32)
    np.testing.assert_allclose(out["time"], expected, atol=1e-7)


def test_lio_sam_xyz_intensity_ring_pass_through_unchanged():
    pts = hilti_points()
    out = to_lio_sam_points(pts, HEADER_STAMP)
    np.testing.assert_array_equal(out["x"], pts["x"])
    np.testing.assert_array_equal(out["y"], pts["y"])
    np.testing.assert_array_equal(out["z"], pts["z"])
    np.testing.assert_array_equal(out["intensity"], pts["intensity"])
    np.testing.assert_array_equal(out["ring"], pts["ring"])


def test_lio_sam_output_dtype_matches_velodyne_layout():
    out = to_lio_sam_points(hilti_points(), HEADER_STAMP)
    assert out.dtype.names == ("x", "y", "z", "intensity", "ring", "time")
    assert out.dtype["time"] == np.dtype("<f4")
    assert out.dtype["ring"] == np.dtype("<u2")


# --- LIO-SAM: Madgwick orientation adapter ----------------------------------------------------
# docs/dataset.md exp14 at-rest window: specific force [0.173, 0.164, -9.660] m/s^2 ("up -z"),
# gyro mean ~[1.06e-03, -2.66e-04, -2.34e-05] rad/s (near-zero, at rest).
EXP14_AT_REST_ACCEL = np.array([0.173, 0.164, -9.660])
EXP14_AT_REST_GYRO = np.array([1.06e-03, -2.66e-04, -2.34e-05])


def test_madgwick_converges_to_measured_gravity_direction_at_rest():
    # Seeded from the first accel reading, as the real node does (imu_orientation_node.py) --
    # starting from a fixed identity quaternion is a gradient-descent singularity whenever the
    # true attitude is near-antipodal to the reference, which it is here (see
    # orientation_filter.initial_quaternion's docstring).
    q = initial_quaternion(EXP14_AT_REST_ACCEL)
    dt = 1.0 / 399.2  # docs/dataset.md measured /alphasense/imu rate
    for _ in range(2000):  # several seconds, enough for beta=0.1 to converge
        q = madgwick_update(q, EXP14_AT_REST_GYRO, EXP14_AT_REST_ACCEL, dt)
    w, x, y, z = q
    # The filter's objective function (Madgwick 2010) drives q so that the earth-frame
    # reference [0,0,1] expressed in the body frame -- the third row of R(q) -- matches the
    # normalized accelerometer reading. At convergence these should coincide.
    ref_in_body = np.array([
        2 * (x * z - w * y),
        2 * (y * z + w * x),
        1 - 2 * (x * x + y * y),
    ])
    expected_dir = EXP14_AT_REST_ACCEL / np.linalg.norm(EXP14_AT_REST_ACCEL)
    cos_angle = np.dot(ref_in_body, expected_dir)
    assert cos_angle > 0.99  # within ~8 degrees


def test_madgwick_output_is_always_unit_norm():
    q = np.array([1.0, 0.0, 0.0, 0.0])
    rng = np.random.default_rng(0)
    for _ in range(500):
        gyro = rng.normal(scale=0.5, size=3)
        accel = np.array([0.0, 0.0, -9.81]) + rng.normal(scale=0.1, size=3)
        q = madgwick_update(q, gyro, accel, dt=1.0 / 399.2)
        np.testing.assert_allclose(np.linalg.norm(q), 1.0, atol=1e-6)
