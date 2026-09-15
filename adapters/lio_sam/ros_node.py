#!/usr/bin/env python
"""Republishes /hesai/pandar in LIO-SAM's expected velodyne point layout.

Runs inside the lio_sam container (needs rospy); the conversion itself is the pure,
unit-tested `to_lio_sam_points` in pointcloud_adapter.py.
"""
import numpy as np
import rospy
from pointcloud_adapter import OUT_DTYPE, to_lio_sam_points
from sensor_msgs.msg import PointCloud2, PointField

PC2_FIELD_TYPES = {"f4": PointField.FLOAT32, "u2": PointField.UINT16}
IN_FIELDS = ("x", "y", "z", "intensity", "timestamp", "ring")


def _in_dtype(msg: PointCloud2) -> np.dtype:
    by_name = {f.name: f for f in msg.fields}
    missing = [n for n in IN_FIELDS if n not in by_name]
    if missing:
        raise ValueError(f"{msg.header.frame_id}: missing point fields {missing}")
    formats = {"x": "<f4", "y": "<f4", "z": "<f4", "intensity": "<f4",
               "timestamp": "<f8", "ring": "<u2"}
    return np.dtype({"names": IN_FIELDS, "formats": [formats[n] for n in IN_FIELDS],
                     "offsets": [by_name[n].offset for n in IN_FIELDS], "itemsize": msg.point_step})


def _out_fields() -> list:
    fields, offset = [], 0
    for name in OUT_DTYPE.names:
        size = OUT_DTYPE[name].itemsize
        fields.append(PointField(name=name, offset=offset,
                                 datatype=PC2_FIELD_TYPES["u2" if name == "ring" else "f4"], count=1))
        offset += size
    return fields


def make_callback(pub: rospy.Publisher):
    out_fields = _out_fields()

    def callback(msg: PointCloud2) -> None:
        pts = np.frombuffer(bytes(msg.data), dtype=_in_dtype(msg))
        header_stamp = msg.header.stamp.to_sec()
        out = to_lio_sam_points(pts, header_stamp)
        out_msg = PointCloud2(header=msg.header, height=1, width=len(out), fields=out_fields,
                              is_bigendian=False, point_step=OUT_DTYPE.itemsize,
                              row_step=OUT_DTYPE.itemsize * len(out), is_dense=msg.is_dense,
                              data=out.tobytes())
        pub.publish(out_msg)

    return callback


def main():
    rospy.init_node("lio_sam_pointcloud_adapter")
    in_topic = rospy.get_param("~in_topic", "/hesai/pandar")
    out_topic = rospy.get_param("~out_topic", "/hesai/pandar/lio_sam")
    pub = rospy.Publisher(out_topic, PointCloud2, queue_size=10)
    rospy.Subscriber(in_topic, PointCloud2, make_callback(pub), queue_size=10)
    rospy.spin()


if __name__ == "__main__":
    main()
