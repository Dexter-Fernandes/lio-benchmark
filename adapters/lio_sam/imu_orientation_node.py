#!/usr/bin/env python
"""Republishes /alphasense/imu with a Madgwick-synthesized `orientation` field.

Hilti's raw IMU has an all-zero orientation quaternion (docs/dataset.md); LIO-SAM's own
imuConverter() rejects a near-zero-norm quaternion outright (see orientation_filter.py's
docstring). This node runs the pure, unit-tested `madgwick_update` stepwise on each IMU
message and republishes a copy with `orientation` filled in and a small-but-finite
`orientation_covariance` (not the original cov[0]=0, which upstream code may treat as
"unknown" and ignore -- here the orientation is real, sensor-derived data). LIO-SAM's
`imuTopic` param must point at this node's output, not the raw topic.
"""
import numpy as np
import rospy
from orientation_filter import DEFAULT_BETA, initial_quaternion, madgwick_update
from sensor_msgs.msg import Imu

# Small, finite, roughly consistent with Madgwick's steady-state roll/pitch accuracy for a
# MEMS IMU; yaw is unobservable without a magnetometer so its variance is left large.
ORIENTATION_COVARIANCE = [
    0.01, 0, 0,
    0, 0.01, 0,
    0, 0, 1.0,
]


class _State:
    q = None
    last_stamp = None


def make_callback(pub: rospy.Publisher, beta: float):
    state = _State()

    def callback(msg: Imu) -> None:
        stamp = msg.header.stamp.to_sec()
        accel = np.array([msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z])
        if state.q is None:
            # Seed from the first accel reading -- see orientation_filter.initial_quaternion.
            state.q = initial_quaternion(accel)
        else:
            dt = stamp - state.last_stamp
            if dt > 0:
                gyro = np.array([msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z])
                state.q = madgwick_update(state.q, gyro, accel, dt, beta)
        state.last_stamp = stamp

        out = Imu()
        out.header = msg.header
        out.angular_velocity = msg.angular_velocity
        out.angular_velocity_covariance = msg.angular_velocity_covariance
        out.linear_acceleration = msg.linear_acceleration
        out.linear_acceleration_covariance = msg.linear_acceleration_covariance
        w, x, y, z = state.q
        out.orientation.w, out.orientation.x, out.orientation.y, out.orientation.z = w, x, y, z
        out.orientation_covariance = ORIENTATION_COVARIANCE
        pub.publish(out)

    return callback


def main():
    rospy.init_node("lio_sam_imu_orientation_adapter")
    in_topic = rospy.get_param("~in_topic", "/alphasense/imu")
    out_topic = rospy.get_param("~out_topic", "/alphasense/imu/oriented")
    beta = rospy.get_param("~beta", DEFAULT_BETA)
    pub = rospy.Publisher(out_topic, Imu, queue_size=200)
    rospy.Subscriber(in_topic, Imu, make_callback(pub, beta), queue_size=200)
    rospy.spin()


if __name__ == "__main__":
    main()
