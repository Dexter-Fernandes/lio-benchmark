"""Measure a sequence before integrating any method: topics, rates, PointCloud2 layout and
per-point time units, ring range, IMU orientation validity, time alignment between sensors,
ground-truth coverage, calibration consistency and the ground-truth quaternion order.

Adapted and extended from ranger-lio's scripts/inspect_bag.py. Reads the ROS 1 bag with
`rosbags` (no ROS needed). The report is written to
<data root>/_provenance/inspect/<sequence>.json and summarised on stdout; the numbers in
configs/dataset/hilti22.yaml and docs/dataset.md come from these reports.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from rosbags.highlevel import AnyReader
from scipy.spatial.transform import Rotation

from .download import write_json_atomic
from .frames import check_lidar_extrinsics, dataset_config, extrinsic, lidar_extrinsic_from_calibration
from .manifest import Sequence
from .paths import provenance_dir
from .trajectory import load_sparse, load_tum

PC2_DTYPES = {1: "i1", 2: "u1", 3: "i2", 4: "u2", 5: "i4", 6: "u4", 7: "f4", 8: "f8"}
TIME_FIELD_CANDIDATES = ("timestamp", "time", "t", "time_offset", "offset_time", "stamp")


def structured_dtype(msg) -> np.dtype:
    """numpy dtype from PointCloud2.fields, so any point layout is readable."""
    names, formats, offsets = [], [], []
    for f in msg.fields:
        names.append(f.name)
        base = PC2_DTYPES[f.datatype]
        formats.append(base if f.count == 1 else f"{f.count}{base}")
        offsets.append(f.offset)
    endian = ">" if msg.is_bigendian else "<"
    return np.dtype({"names": names, "formats": [endian + f for f in formats], "offsets": offsets,
                     "itemsize": msg.point_step})


def _stamp(msg) -> float:
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def _dist(x) -> dict:
    x = np.asarray(x, dtype=float)
    if not len(x):
        return {}
    return {"min": float(x.min()), "max": float(x.max()), "mean": float(x.mean()),
            "std": float(x.std()), "median": float(np.median(x))}


def infer_point_time_unit(sample_value: float) -> str:
    """Classify a per-point time field from its magnitude (absolute epoch times only)."""
    if abs(sample_value) > 1e17:
        return "nanoseconds_absolute"
    if abs(sample_value) > 1e8:
        return "seconds_absolute"
    return "unknown"


def _lidar_section(reader, conn) -> dict:
    stamps, bag_times, n_points, spreads, min_minus_header, max_minus_header = [], [], [], [], [], []
    ring_min, ring_max, nonfinite, ranges = np.inf, -np.inf, 0, []
    layout, time_field, sample_time, total = None, None, None, 0
    for k, (c, log_ns, raw) in enumerate(reader.messages(connections=[conn])):
        msg = reader.deserialize(raw, c.msgtype)
        stamp = _stamp(msg)
        stamps.append(stamp)
        bag_times.append(log_ns * 1e-9)
        if layout is None:
            layout = {
                "fields": [{"name": f.name, "offset": f.offset, "datatype": PC2_DTYPES[f.datatype],
                            "count": f.count} for f in msg.fields],
                "point_step": msg.point_step, "height": msg.height, "is_dense": bool(msg.is_dense),
                "is_bigendian": bool(msg.is_bigendian), "frame_id": msg.header.frame_id,
            }
            names = [f.name for f in msg.fields]
            time_field = next((n for n in TIME_FIELD_CANDIDATES if n in names), None)
        pts = np.frombuffer(np.asarray(msg.data, dtype=np.uint8).tobytes(), dtype=structured_dtype(msg))
        n_points.append(len(pts))
        total += len(pts)
        xyz = np.column_stack([pts["x"], pts["y"], pts["z"]]).astype(float)
        finite = np.all(np.isfinite(xyz), axis=1)
        nonfinite += int((~finite).sum())
        if k % 10 == 0:
            r = np.linalg.norm(xyz[finite], axis=1)
            ranges.append(r[r > 0])
        if time_field is not None and len(pts):
            tf = pts[time_field].astype(np.float64)
            if sample_time is None:
                sample_time = float(tf[0])
            spreads.append(tf.max() - tf.min())
            min_minus_header.append(tf.min() - stamp)
            max_minus_header.append(tf.max() - stamp)
        if "ring" in pts.dtype.names and len(pts):
            ring_min, ring_max = min(ring_min, int(pts["ring"].min())), max(ring_max, int(pts["ring"].max()))

    stamps, bag_times = np.array(stamps), np.array(bag_times)
    period = np.diff(stamps)
    r = np.concatenate(ranges) if ranges else np.empty(0)
    section = {
        "topic": conn.topic, "count": len(stamps), "layout": layout,
        "first_stamp": float(stamps[0]), "last_stamp": float(stamps[-1]),
        "period_s": _dist(period), "rate_hz": float(1 / period.mean()) if len(period) else None,
        "non_monotonic_stamps": int((period <= 0).sum()),
        "points_per_scan": _dist(n_points), "nonfinite_points": nonfinite,
        "nonfinite_fraction": nonfinite / total if total else None,
        "range_m_sampled": {**_dist(r), "p01": float(np.percentile(r, 1)), "p99": float(np.percentile(r, 99))} if len(r) else {},
        "bag_minus_header_s": _dist(bag_times - stamps),
        "ring": {"min": int(ring_min), "max": int(ring_max)} if np.isfinite(ring_min) else None,
        "point_time": None,
    }
    if time_field is not None:
        spreads, mmh = np.array(spreads), np.array(min_minus_header)
        section["point_time"] = {
            "field": time_field,
            "unit": infer_point_time_unit(sample_time),
            "per_scan_spread": _dist(spreads),
            "per_scan_min_minus_header": _dist(mmh),
            "per_scan_max_minus_header": _dist(max_minus_header),
        }
    return section


def _imu_section(reader, conn, rest_seconds: float) -> dict:
    stamps, bag_times, gyro, acc, quat, ocov0 = [], [], [], [], [], []
    for c, log_ns, raw in reader.messages(connections=[conn]):
        msg = reader.deserialize(raw, c.msgtype)
        stamps.append(_stamp(msg))
        bag_times.append(log_ns * 1e-9)
        gyro.append([msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z])
        acc.append([msg.linear_acceleration.x, msg.linear_acceleration.y, msg.linear_acceleration.z])
        quat.append([msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w])
        ocov0.append(msg.orientation_covariance[0])
    stamps, bag_times = np.array(stamps), np.array(bag_times)
    gyro, acc, quat, ocov0 = map(np.array, (gyro, acc, quat, ocov0))
    period = np.diff(stamps)
    qn = np.linalg.norm(quat, axis=1)
    rest = stamps - stamps[0] <= rest_seconds
    a_rest = acc[rest].mean(0)
    up = int(np.argmax(np.abs(a_rest)))

    # Orientation is usable only if it is a unit quaternion that changes over the sequence and
    # the covariance does not flag it as absent (ROS convention: orientation_covariance[0] = -1).
    unit = bool(np.allclose(qn, 1.0, atol=1e-3))
    varies = bool(unit and (Rotation.from_quat(quat[0]).inv() * Rotation.from_quat(quat)).magnitude().max() > 1e-3)
    return {
        "topic": conn.topic, "count": len(stamps),
        "first_stamp": float(stamps[0]), "last_stamp": float(stamps[-1]),
        "period_s": _dist(period), "rate_hz": float(1 / period.mean()),
        "non_monotonic_stamps": int((period <= 0).sum()),
        "max_gap_s": float(period.max()),
        "bag_minus_header_s": _dist(bag_times - stamps),
        "orientation": {
            "quaternion_norm": _dist(qn),
            "all_zero": bool(np.all(qn < 1e-9)),
            "covariance0_values": sorted({float(v) for v in np.unique(ocov0)})[:5],
            "flagged_absent": bool(np.all(ocov0 == -1)),
            "unit_norm": unit, "varies": varies,
            "usable": unit and varies and not bool(np.all(ocov0 == -1)),
        },
        "rest_window": {
            "seconds": rest_seconds, "samples": int(rest.sum()),
            "gyro_mean_rad_s": gyro[rest].mean(0).tolist(), "gyro_std_rad_s": gyro[rest].std(0).tolist(),
            "acc_mean_m_s2": a_rest.tolist(), "acc_std_m_s2": acc[rest].std(0).tolist(),
            "acc_norm_mean": float(np.linalg.norm(acc[rest], axis=1).mean()),
            "up_axis": f"{'+' if a_rest[up] > 0 else '-'}{'xyz'[up]}",
            "t_mid": float(stamps[rest].mean()),
        },
        "acc_norm_whole_sequence": _dist(np.linalg.norm(acc, axis=1)),
        "gyro_norm_whole_sequence": _dist(np.linalg.norm(gyro, axis=1)),
    }


def gravity_check(gt, t: float, acc_rest_I: np.ndarray) -> dict:
    """Angle between the at-rest specific force, rotated into W by the ground truth, and +z_W.

    At rest the accelerometer measures the specific force, which points up. If the ground-truth
    world is z-up and its quaternions are (x, y, z, w), R_W_I a_I is close to +z_W. Reading the
    same numbers as (w, x, y, z) should give a clearly larger angle, so this settles the order.
    """
    k = int(np.argmin(np.abs(gt.t - t)))
    a = acc_rest_I / np.linalg.norm(acc_rest_I)
    q = gt.q[k]
    as_xyzw = Rotation.from_quat(q).apply(a)
    as_wxyz = Rotation.from_quat([q[1], q[2], q[3], q[0]]).apply(a)
    ang = lambda v: float(np.degrees(np.arccos(np.clip(v[2], -1, 1))))
    return {"gt_time": float(gt.t[k]), "dt_to_rest_window_s": float(gt.t[k] - t),
            "angle_to_up_deg_if_xyzw": ang(as_xyzw), "angle_to_up_deg_if_wxyz": ang(as_wxyz)}


def inspect_sequence(seq: Sequence, data_root: Path, rest_seconds: float = 1.0,
                     log=print) -> dict:
    cfg = dataset_config()
    bag = data_root / seq.bag
    report: dict = {"sequence": seq.name, "bag": seq.bag,
                    "inspected_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    log(f"reading {bag}")
    with AnyReader([bag]) as reader:
        report["bag_info"] = {
            "start": reader.start_time * 1e-9, "end": reader.end_time * 1e-9,
            "duration_s": reader.duration * 1e-9, "message_count": reader.message_count,
            "topics": [{"topic": c.topic, "msgtype": c.msgtype, "count": c.msgcount,
                        "rate_hz": c.msgcount / (reader.duration * 1e-9)} for c in reader.connections],
        }
        by_topic = {c.topic: c for c in reader.connections}
        for key in ("lidar", "imu"):
            if cfg["topics"][key] not in by_topic:
                raise RuntimeError(f"{seq.name}: configured {key} topic {cfg['topics'][key]} not in bag")
        log("  lidar ...")
        report["lidar"] = _lidar_section(reader, by_topic[cfg["topics"]["lidar"]])
        log("  imu ...")
        report["imu"] = _imu_section(reader, by_topic[cfg["topics"]["imu"]], rest_seconds)

    lidar, imu = report["lidar"], report["imu"]
    report["sensor_overlap_s"] = [max(lidar["first_stamp"], imu["first_stamp"]),
                                  min(lidar["last_stamp"], imu["last_stamp"])]

    gt = load_tum(data_root / seq.ground_truth_dense)
    sparse = load_sparse(data_root / seq.ground_truth_sparse)
    span = report["sensor_overlap_s"]
    report["ground_truth"] = {
        "dense_poses": len(gt), "dense_span_s": [float(gt.t[0]), float(gt.t[-1])],
        "dense_rate_hz": float((len(gt) - 1) / gt.duration),
        "dense_max_gap_s": float(np.diff(gt.t).max()),
        "dense_starts_after_sensors_s": float(gt.t[0] - span[0]),
        "dense_ends_before_sensors_s": float(span[1] - gt.t[-1]),
        "dense_extent_m": (gt.p.max(0) - gt.p.min(0)).tolist(),
        "dense_path_length_m": float(np.linalg.norm(np.diff(gt.p, axis=0), axis=1).sum()),
        "sparse_points": len(sparse.t),
        "sparse_times": sparse.t.tolist(),
        "sparse_outside_dense_span": int(((sparse.t < gt.t[0]) | (sparse.t > gt.t[-1])).sum()),
        "sparse_outside_sensor_span": int(((sparse.t < span[0]) | (sparse.t > span[1])).sum()),
    }
    report["gravity_check"] = gravity_check(gt, imu["rest_window"]["t_mid"],
                                            np.array(imu["rest_window"]["acc_mean_m_s2"]))

    T_cfg = extrinsic(cfg, "T_I_L")
    check_lidar_extrinsics(T_cfg)
    T_file = lidar_extrinsic_from_calibration(data_root / "calibration/calibration_files/lidar_calibration.yaml")
    report["calibration"] = {
        "config_matches_file": bool(np.allclose(T_cfg.matrix(), T_file.matrix(), atol=1e-9)),
        "convention_check": "passed",
    }

    out = provenance_dir(data_root) / "inspect" / f"{seq.key}.json"
    write_json_atomic(out, report)
    report["_written_to"] = str(out)
    return report


def summary_lines(r: dict) -> list[str]:
    li, im, gt, g = r["lidar"], r["imu"], r["ground_truth"], r["gravity_check"]
    pt = li["point_time"] or {}
    o = im["orientation"]
    return [
        f"{r['sequence']}: bag {r['bag_info']['duration_s']:.1f} s, {r['bag_info']['message_count']} msgs",
        f"  lidar {li['topic']}: {li['count']} scans @ {li['rate_hz']:.2f} Hz, "
        f"{li['points_per_scan'].get('median', 0):.0f} pts/scan, point_step {li['layout']['point_step']}, "
        f"frame '{li['layout']['frame_id']}'",
        "    fields: " + ", ".join(f"{f['name']}:{f['datatype']}@{f['offset']}" for f in li["layout"]["fields"]),
        f"    point time '{pt.get('field')}' unit={pt.get('unit')} spread median="
        f"{pt.get('per_scan_spread', {}).get('median', float('nan')):.4f} "
        f"min-header median={pt.get('per_scan_min_minus_header', {}).get('median', float('nan')):+.6f}",
        f"    ring {li['ring']}, non-finite points {li['nonfinite_fraction']:.2%}",
        f"  imu {im['topic']}: {im['count']} @ {im['rate_hz']:.1f} Hz, max gap {im['max_gap_s'] * 1e3:.1f} ms, "
        f"non-monotonic {im['non_monotonic_stamps']}",
        f"    orientation usable={o['usable']} (unit={o['unit_norm']} varies={o['varies']} "
        f"cov0={o['covariance0_values']})",
        f"    rest: acc {np.round(im['rest_window']['acc_mean_m_s2'], 3).tolist()} "
        f"|a|={im['rest_window']['acc_norm_mean']:.3f} up={im['rest_window']['up_axis']}",
        f"  ground truth: {gt['dense_poses']} poses @ {gt['dense_rate_hz']:.2f} Hz, "
        f"starts {gt['dense_starts_after_sensors_s']:+.2f} s after sensors, ends "
        f"{gt['dense_ends_before_sensors_s']:+.2f} s before; path {gt['dense_path_length_m']:.1f} m; "
        f"sparse {gt['sparse_points']} ({gt['sparse_outside_dense_span']} outside dense span)",
        f"  gravity check: {g['angle_to_up_deg_if_xyzw']:.2f} deg (xyzw) vs "
        f"{g['angle_to_up_deg_if_wxyz']:.2f} deg (wxyz)",
        f"  calibration matches config: {r['calibration']['config_matches_file']}",
    ]
