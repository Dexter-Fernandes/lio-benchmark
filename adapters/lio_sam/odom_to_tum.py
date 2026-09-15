#!/usr/bin/env python
"""Subscribes LIO-SAM's /lio_sam/mapping/odometry and appends TUM-format lines.

Unlike FAST-LIO2 (whose ESKF state is IMU-centric), LIO-SAM's mapOptimization node keeps
`transformTobeMapped` as the LiDAR pose directly (src/mapOptmization.cpp, `lidarFrame ==
baselinkFrame == "base_link"`, published on `lio_sam/mapping/odometry`) -- this is a
lidar-frame pose, so `lio-bench eval` for this method must use `--frame lidar`, not `imu`.
Timestamps are the message header stamp (the LiDAR scan time), matching the other absolute-
epoch trajectories this benchmark evaluates.
"""
import rospy
from nav_msgs.msg import Odometry


def main():
    rospy.init_node("lio_sam_odom_to_tum")
    out_path = rospy.get_param("~out_path")
    topic = rospy.get_param("~topic", "/lio_sam/mapping/odometry")
    f = open(out_path, "w")  # noqa: SIM115 -- kept open for the node's lifetime, closed on shutdown
    rospy.on_shutdown(f.close)

    def callback(msg: Odometry) -> None:
        t = msg.header.stamp.to_sec()
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        f.write(f"{t:.9f} {p.x:.6f} {p.y:.6f} {p.z:.6f} {q.x:.9f} {q.y:.9f} {q.z:.9f} {q.w:.9f}\n")
        f.flush()

    rospy.Subscriber(topic, Odometry, callback, queue_size=100)
    rospy.spin()


if __name__ == "__main__":
    main()
