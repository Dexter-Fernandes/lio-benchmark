"""IMU noise measurement on a tiny synthetic static ROS 1 bag with known injected noise."""
import numpy as np
import pytest
from rosbags.rosbag1 import Writer
from rosbags.typesys import Stores, get_typestore

from lio_benchmark.inspection import imu_noise

IMU = "/alphasense/imu"
T0 = 1_649_764_528
GYR_STD, ACC_STD = 0.02, 0.05


@pytest.fixture(scope="module")
def static_imu_bag(tmp_path_factory):
    ts = get_typestore(Stores.ROS1_NOETIC)
    T = ts.types
    Header, Time = T["std_msgs/msg/Header"], T["builtin_interfaces/msg/Time"]
    Vec, Quat = T["geometry_msgs/msg/Vector3"], T["geometry_msgs/msg/Quaternion"]
    rng = np.random.default_rng(0)
    n = 20_000
    gyro = rng.normal(0, GYR_STD, size=(n, 3))
    acc = rng.normal([0, 0, 9.81], ACC_STD, size=(n, 3))
    path = tmp_path_factory.mktemp("bags") / "imu_noise_calibration.bag"
    with Writer(path) as w:
        c_imu = w.add_connection(IMU, "sensor_msgs/msg/Imu", typestore=ts)
        for k in range(n):
            total_ns = k * 2_500_000                  # 400 Hz
            sec, nanosec = T0 + total_ns // 1_000_000_000, total_ns % 1_000_000_000
            msg = T["sensor_msgs/msg/Imu"](
                Header(k, Time(sec, nanosec), "imu"), Quat(0, 0, 0, 1), np.full(9, -1.0),
                Vec(*gyro[k]), np.zeros(9), Vec(*acc[k]), np.zeros(9))
            w.write(c_imu, T0 * 10**9 + total_ns, ts.serialize_ros1(msg, "sensor_msgs/msg/Imu"))
    return path


def test_imu_noise_recovers_known_injected_std(static_imu_bag):
    report = imu_noise(static_imu_bag, log=lambda *_: None)
    assert report["samples"] == 20_000
    np.testing.assert_allclose(report["gyr_std_rad_s"], [GYR_STD] * 3, rtol=0.05)
    np.testing.assert_allclose(report["acc_std_m_s2"], [ACC_STD] * 3, rtol=0.05)
    assert report["gyr_cov"] == pytest.approx(GYR_STD ** 2, rel=0.1)
    assert report["acc_cov"] == pytest.approx(ACC_STD ** 2, rel=0.1)
