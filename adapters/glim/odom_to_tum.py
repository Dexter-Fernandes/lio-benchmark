#!/usr/bin/env python3
"""Subscribes GLIM's online IMU-frame odometry and appends TUM-format lines
(t x y z qx qy qz qw).

GLIM itself never reads sensor_msgs/Imu.orientation and never publishes a topic from
glim_ros core -- odometry is only published by the `librviz_viewer.so` extension module
(glim_ros2/src/glim_ros/rviz_viewer.cpp), as nav_msgs/Odometry on <node>/odom (T_world_imu,
IMU frame) and <node>/lidar_odom (LiDAR frame). Use --frame imu with --topic .../odom. The
*_corrected topics are the retrospectively-optimized global-mapping poses (secondary
comparison, docs/protocol.md #1) and must never be substituted here.

Timestamps are the message header stamp, so they line up with the other absolute-epoch
trajectories this benchmark evaluates.
"""
import argparse

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node


class OdomToTum(Node):
    def __init__(self, topic: str, out_path: str):
        super().__init__("glim_odom_to_tum")
        self.f = open(out_path, "w")  # noqa: SIM115 -- kept open for the node's lifetime
        self.create_subscription(Odometry, topic, self.callback, 100)

    def callback(self, msg: Odometry) -> None:
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        self.f.write(f"{t:.9f} {p.x:.6f} {p.y:.6f} {p.z:.6f} {q.x:.9f} {q.y:.9f} {q.z:.9f} {q.w:.9f}\n")
        self.f.flush()

    def destroy_node(self):
        self.f.close()
        super().destroy_node()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--out", required=True)
    args, _ = ap.parse_known_args()

    rclpy.init()
    node = OdomToTum(args.topic, args.out)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
