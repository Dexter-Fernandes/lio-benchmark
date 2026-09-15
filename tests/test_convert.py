"""Conversion equivalence on a tiny synthetic ROS 1 bag with Hilti-like topics."""
import copy

import numpy as np
import pytest
from rosbags.rosbag1 import Writer
from rosbags.typesys import Stores, get_typestore

from lio_benchmark.convert import compare, convert_sequence, summarize

LIDAR, IMU, CAM = "/hesai/pandar", "/alphasense/imu", "/alphasense/cam0/image_raw"
T0 = 1_649_764_528


@pytest.fixture(scope="module")
def ros1_bag(tmp_path_factory):
    ts = get_typestore(Stores.ROS1_NOETIC)
    T = ts.types
    Header, Time = T["std_msgs/msg/Header"], T["builtin_interfaces/msg/Time"]
    Vec, Quat, Field = T["geometry_msgs/msg/Vector3"], T["geometry_msgs/msg/Quaternion"], T["sensor_msgs/msg/PointField"]
    path = tmp_path_factory.mktemp("bags") / "rosbags" / "tiny.bag"
    path.parent.mkdir()
    fields = [Field("x", 0, 7, 1), Field("y", 4, 7, 1), Field("z", 8, 7, 1),
              Field("timestamp", 16, 8, 1), Field("ring", 24, 4, 1)]
    with Writer(path) as w:
        c_imu = w.add_connection(IMU, "sensor_msgs/msg/Imu", typestore=ts)
        c_pc = w.add_connection(LIDAR, "sensor_msgs/msg/PointCloud2", typestore=ts)
        c_cam = w.add_connection(CAM, "std_msgs/msg/String", typestore=ts)
        for k in range(40):                                  # 400 Hz IMU for 0.1 s
            ns = k * 2_500_000
            msg = T["sensor_msgs/msg/Imu"](
                Header(k, Time(T0, ns), "imu"), Quat(0, 0, 0, 1), np.full(9, -1.0),
                Vec(0.001 * k, 0, 0), np.zeros(9), Vec(0, 0, -9.81), np.zeros(9))
            w.write(c_imu, T0 * 10**9 + ns, ts.serialize_ros1(msg, "sensor_msgs/msg/Imu"))
        for k in range(2):                                   # two tiny scans
            pts = np.zeros(5, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("pad", "<f4"),
                                     ("timestamp", "<f8"), ("ring", "<u2"), ("pad2", "<u2", 3)])
            pts["x"], pts["timestamp"], pts["ring"] = np.arange(5) + k, T0 + 0.05 * k + 0.01 * np.arange(5), np.arange(5)
            msg = T["sensor_msgs/msg/PointCloud2"](
                Header(k, Time(T0, 50_000_000 * k), "pandar"), 1, 5, fields, False, 32, 160,
                np.frombuffer(pts.tobytes(), dtype=np.uint8), True)
            w.write(c_pc, T0 * 10**9 + 50_000_000 * k, ts.serialize_ros1(msg, "sensor_msgs/msg/PointCloud2"))
        w.write(c_cam, T0 * 10**9, ts.serialize_ros1(T["std_msgs/msg/String"]("dropped"), "std_msgs/msg/String"))
    return path


def test_convert_keeps_only_selected_topics_and_is_equivalent(ros1_bag):
    root = ros1_bag.parent.parent
    rec = convert_sequence(root, "tiny", "rosbags/tiny.bag", "rosbag2/tiny", [LIDAR, IMU], log=lambda *_: None)
    assert rec["equivalent"] and rec["problems"] == []
    dst = rec["destination_summary"]["topics"]
    assert dst[IMU]["count"] == 40 and dst[LIDAR]["count"] == 2
    assert (root / "rosbag2/tiny/metadata.yaml").exists()
    assert not (root / "rosbag2/tiny.converting").exists()
    assert (root / "_provenance/conversions/tiny.json").exists()
    with pytest.raises(Exception, match="not found"):
        summarize(root / "rosbag2/tiny", [CAM])            # camera topic was dropped

    again = convert_sequence(root, "tiny", "rosbags/tiny.bag", "rosbag2/tiny", [LIDAR, IMU],
                             check_only=True, log=lambda *_: None)
    assert again["equivalent"] and again["produced_by"] == "lio-bench data convert"


def test_compare_detects_content_and_count_changes(ros1_bag):
    src = summarize(ros1_bag, [LIDAR, IMU])
    dst = copy.deepcopy(src)
    assert compare(src, dst) == []
    dst["topics"][LIDAR]["content_sha256"] = "0" * 64
    dst["topics"][IMU]["count"] -= 1
    problems = compare(src, dst)
    assert any("content_sha256" in p for p in problems) and any("count" in p for p in problems)
