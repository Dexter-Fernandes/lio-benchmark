import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from lio_benchmark.frames import (check_lidar_extrinsics, dataset_config, extrinsic,
                                  lidar_extrinsic_from_calibration, to_imu_frame, transform_body)
from lio_benchmark.se3 import SE3
from tests.helpers import loop

CALIBRATION = """\
sensors:
  PandarXT-32:
    extrinsics:
      quaternion: [ 0.7071068, -0.7071068, 0, 0 ]
      translation: [ -0.001, -0.00855, 0.055 ]
    parent: imu
"""


@pytest.fixture
def T_I_L():
    return extrinsic(dataset_config(), "T_I_L")


def test_config_extrinsic_passes_convention_check(T_I_L):
    check_lidar_extrinsics(T_I_L)
    np.testing.assert_allclose(T_I_L.act([0, 0, 1.0]) - T_I_L.t, [0, 0, -1], atol=1e-6)


def test_wrong_quaternion_order_is_caught():
    wxyz_misread = SE3.from_xyzw([-0.7071068, 0, 0, 0.7071068], [0, 0, 0])   # (w,x,y,z) read as xyzw
    with pytest.raises(AssertionError):
        check_lidar_extrinsics(wxyz_misread)


def test_config_matches_calibration_file(tmp_path, T_I_L):
    f = tmp_path / "lidar_calibration.yaml"
    f.write_text(CALIBRATION)
    from_file = lidar_extrinsic_from_calibration(f)
    np.testing.assert_allclose(from_file.matrix(), T_I_L.matrix(), atol=1e-9)


def test_se3_inverse_composition_and_known_answer():
    T_W_I = SE3.from_xyzw([0.1, 0.2, 0.3, 0.9273618], [10.0, -2.0, 0.5])
    T_I_L = SE3.from_xyzw([0.7071068, -0.7071068, 0, 0], [-0.001, -0.00855, 0.055])
    T_W_L = T_W_I * T_I_L
    p_W = np.array([1.2, -3.4, 5.6])
    np.testing.assert_allclose(T_W_L.act(T_W_L.inverse().act(p_W)), p_W, atol=1e-9)
    np.testing.assert_allclose((T_W_L.inverse() * T_W_L).matrix(), np.eye(4), atol=1e-9)
    # The LiDAR origin in W is R_W_I t_I_L + t_W_I.
    np.testing.assert_allclose(T_W_L.t, T_W_I.R @ T_I_L.t + T_W_I.t, atol=1e-12)


def test_lidar_trajectory_round_trip_to_imu(T_I_L):
    imu = loop()
    lidar = transform_body(imu, T_I_L)                  # T_W_L = T_W_I T_I_L
    back = to_imu_frame(lidar, T_I_L)                   # T_W_I = T_W_L T_I_L^-1
    np.testing.assert_allclose(back.p, imu.p, atol=1e-9)
    ang = (back.rotations.inv() * imu.rotations).magnitude()
    assert ang.max() < 1e-9
    # And the LiDAR trajectory really is displaced by the lever arm, rotated into W.
    np.testing.assert_allclose(lidar.p - imu.p, imu.rotations.apply(T_I_L.t), atol=1e-12)


def test_transform_body_matches_se3_per_pose(T_I_L):
    imu = loop(duration=2.0)
    lidar = transform_body(imu, T_I_L)
    for k in range(len(imu)):
        expected = SE3.from_xyzw(imu.q[k], imu.p[k]) * T_I_L
        np.testing.assert_allclose(lidar.p[k], expected.t, atol=1e-12)
        assert (Rotation.from_quat(lidar.q[k]).inv() * Rotation.from_matrix(expected.R)).magnitude() < 1e-9


# --- LIO-SAM: extrinsic convention -------------------------------------------------------------
# TixiaoShan/LIO-SAM's include/utility.h imuConverter() computes `acc = extrinsicRot * acc_imu`
# and treats the result as the acceleration in the lidar/base_link-aligned frame (LIO-SAM assumes
# lidarFrame == baselinkFrame). That means extrinsicRot rotates an IMU-frame vector INTO the
# lidar frame -- i.e. it is T_L_I.R (== T_I_L.inverse().R), not T_I_L.R directly, despite
# config/params.yaml's own comment calling it "T_lb (lidar -> imu)" (misleading naming, a known
# source of confusion in LIO-SAM forks/issues). extrinsicTrans is consumed separately, only as a
# translation-only lever-arm offset between the IMU-preintegration and lidar pose graph nodes
# (src/imuPreintegration.cpp's imu2Lidar/lidar2Imu, both built with an *identity* rotation) --
# so it must be T_L_I.t, the position of the lidar origin's counterpart already expressed in the
# lidar-aligned frame, consistent with the same T_L_I used for extrinsicRot.
def test_lio_sam_extrinsic_is_T_L_I_not_T_I_L(T_I_L):
    T_L_I = T_I_L.inverse()
    # A vector at the IMU's own +z axis should land at the lidar's -z after extrinsicRot,
    # matching check_lidar_extrinsics' T_I_L convention run in reverse.
    np.testing.assert_allclose(T_L_I.R @ [0, 0, 1.0], [0, 0, -1], atol=1e-6)
    np.testing.assert_allclose(T_L_I.R @ [1.0, 0, 0], [0, -1.0, 0], atol=1e-6)
    # extrinsicTrans is the lidar-aligned-frame lever arm, not the raw calibration translation.
    assert not np.allclose(T_L_I.t, T_I_L.t)


def test_glim_extrinsic_is_T_L_I_not_T_I_L(T_I_L):
    """GLIM's config_sensors.json `T_lidar_imu` is consumed in cloud_preprocessor.cpp as
    `T_imu_lidar = T_lidar_imu.inverse()`, then `p_imu = T_imu_lidar * p_lidar` -- so the
    config value itself is T_L_I (T_I_L inverted), the same convention LIO-SAM's
    extrinsicRot/extrinsicTrans need (test_lio_sam_extrinsic_is_T_L_I_not_T_I_L above).
    configs/glim/hilti22.yaml's `sensors.T_lidar_imu` translation must therefore match
    LIO-SAM's extrinsicTrans, not the raw calibration translation.
    """
    T_L_I = T_I_L.inverse()
    np.testing.assert_allclose(T_L_I.R @ [0, 0, 1.0], [0, 0, -1], atol=1e-6)
    np.testing.assert_allclose(T_L_I.t, [-0.00855, -0.001, 0.055], atol=1e-6)


def test_lio_sam_extrinsic_puts_gravity_up_per_rep105(T_I_L):
    """LIO-SAM's README requires IMU data to land in the lidar frame under ROS REP-105
    (x forward, y left, z up), i.e. a level, stationary sensor reads ~+9.8 on z after
    `extrinsicRot`. The raw Hilti IMU reads gravity along -z (docs/dataset.md's measured
    at-rest specific force, "up -z"), so this only holds if extrinsicRot is the right way
    round -- the check upstream asks the user to make by hand with the sensor in their hands.
    """
    at_rest_I = np.array([0.173, 0.164, -9.660])  # docs/dataset.md, exp14, first 1 s
    at_rest_L = T_I_L.inverse().R @ at_rest_I
    np.testing.assert_allclose(at_rest_L, [0.0, 0.0, 9.66], atol=0.2)
