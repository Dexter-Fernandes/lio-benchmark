#!/usr/bin/env python
"""Subscribes FAST-LIO2's /Odometry and appends TUM-format lines (t x y z qx qy qz qw).

Timestamps are the message header stamp (the LiDAR scan time FAST-LIO2 copies through), so
they line up with the other absolute-epoch trajectories this benchmark evaluates.
"""
import rospy
from nav_msgs.msg import Odometry


def main():
    rospy.init_node("fast_lio2_odom_to_tum")
    out_path = rospy.get_param("~out_path")
    topic = rospy.get_param("~topic", "/Odometry")
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
