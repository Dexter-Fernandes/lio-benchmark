"""ROS 1 bag -> rosbag2 (MCAP) conversion for ROS 2 methods, with an equivalence check.

Only the LiDAR and IMU topics are kept. Conversion runs `rosbags-convert` (adapted from
ranger-lio's scripts/convert_bag.sh) into a temporary directory, which is renamed into place
only after the check passes. The check reads both bags and compares, per topic: message
type, count, first/last log time, first/last header stamp and a SHA-256 over the message
content that methods consume (header stamps plus IMU vectors, or PointCloud2 layout and
point bytes). Results go to <data root>/_provenance/conversions/<sequence>.json.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from rosbags.highlevel import AnyReader

from .download import write_json_atomic
from .paths import provenance_dir

IMU = "sensor_msgs/msg/Imu"
POINTCLOUD2 = "sensor_msgs/msg/PointCloud2"


class ConversionError(RuntimeError):
    pass


def _stamp_ns(msg) -> int:
    return int(msg.header.stamp.sec) * 1_000_000_000 + int(msg.header.stamp.nanosec)


def _content_bytes(msg, msgtype: str) -> bytes:
    stamp = np.array([_stamp_ns(msg)], dtype=np.int64).tobytes()
    if msgtype == IMU:
        o, w, a = msg.orientation, msg.angular_velocity, msg.linear_acceleration
        values = [o.x, o.y, o.z, o.w, w.x, w.y, w.z, a.x, a.y, a.z]
        cov = np.concatenate([msg.orientation_covariance, msg.angular_velocity_covariance,
                              msg.linear_acceleration_covariance])
        return stamp + np.array(values, dtype=np.float64).tobytes() + np.asarray(cov, np.float64).tobytes()
    if msgtype == POINTCLOUD2:
        layout = ";".join(f"{f.name}:{f.offset}:{f.datatype}:{f.count}" for f in msg.fields)
        head = f"{msg.height}:{msg.width}:{msg.point_step}:{msg.row_step}:{int(msg.is_bigendian)}:{layout}"
        return stamp + head.encode() + np.asarray(msg.data, dtype=np.uint8).tobytes()
    raise ConversionError(f"no content digest defined for {msgtype}")


def summarize(bag: Path, topics: list[str]) -> dict:
    """Per-topic counts, time bounds and content digest for a ROS 1 bag or rosbag2 directory."""
    out: dict = {"path": str(bag), "topics": {}}
    with AnyReader([Path(bag)]) as reader:
        conns = [c for c in reader.connections if c.topic in topics]
        missing = set(topics) - {c.topic for c in conns}
        if missing:
            raise ConversionError(f"{bag}: topics not found: {sorted(missing)}")
        for topic in topics:
            tc = [c for c in conns if c.topic == topic]
            msgtype = tc[0].msgtype
            h = hashlib.sha256()
            count, first_log, last_log, first_stamp, last_stamp = 0, None, None, None, None
            for conn, log_ns, raw in reader.messages(connections=tc):
                msg = reader.deserialize(raw, conn.msgtype)
                h.update(_content_bytes(msg, msgtype))
                stamp = _stamp_ns(msg)
                first_log = log_ns if first_log is None else first_log
                first_stamp = stamp if first_stamp is None else first_stamp
                last_log, last_stamp = log_ns, stamp
                count += 1
            out["topics"][topic] = {
                "msgtype": msgtype, "count": count, "first_log_ns": first_log, "last_log_ns": last_log,
                "first_stamp_ns": first_stamp, "last_stamp_ns": last_stamp, "content_sha256": h.hexdigest(),
            }
    return out


def compare(src: dict, dst: dict) -> list[str]:
    """Differences between two summaries (empty list means equivalent)."""
    problems = []
    for topic, a in src["topics"].items():
        b = dst["topics"].get(topic)
        if b is None:
            problems.append(f"{topic}: missing from destination")
            continue
        for key in ("msgtype", "count", "first_log_ns", "last_log_ns", "first_stamp_ns",
                    "last_stamp_ns", "content_sha256"):
            if a[key] != b[key]:
                problems.append(f"{topic}: {key} {a[key]} != {b[key]}")
    return problems


def rosbag2_metadata(bag_dir: Path) -> dict:
    info = yaml.safe_load((Path(bag_dir) / "metadata.yaml").read_text())["rosbag2_bagfile_information"]
    return {"version": info.get("version"), "storage_identifier": info.get("storage_identifier"),
            "ros_distro": info.get("ros_distro"), "message_count": info.get("message_count")}


def run_rosbags_convert(src: Path, dst: Path, topics: list[str], dst_version: int | None) -> list[str]:
    cmd = [sys.executable, "-m", "rosbags.convert", "--src", str(src), "--dst", str(dst),
           "--dst-storage", "mcap", "--include-topic", *topics]
    if dst_version is not None:
        cmd += ["--dst-version", str(dst_version)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ConversionError(f"rosbags-convert failed ({result.returncode}):\n{result.stderr}")
    return cmd


def convert_sequence(data_root: Path, seq_name: str, bag_rel: str, rosbag2_rel: str,
                     topics: list[str], check_only: bool = False, dst_version: int | None = None,
                     log=print) -> dict:
    src, dst = data_root / bag_rel, data_root / rosbag2_rel
    if not src.is_file():
        raise ConversionError(f"missing source bag {src}")
    record = {
        "sequence": seq_name, "source": bag_rel, "destination": rosbag2_rel, "topics": topics,
        "rosbags_version": importlib.metadata.version("rosbags"),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    prov = provenance_dir(data_root) / "conversions" / f"{seq_name}.json"

    if dst.exists():
        log(f"destination exists, checking only: {dst}")
        record["produced_by"] = _previous_producer(prov)
    elif check_only:
        raise ConversionError(f"--check-only but {dst} does not exist")
    else:
        tmp = dst.with_name(dst.name + ".converting")
        if tmp.exists():
            shutil.rmtree(tmp)
        log(f"converting {src.name} -> {dst.name} (topics {' '.join(topics)})")
        record["command"] = run_rosbags_convert(src, tmp, topics, dst_version)[1:]
        record["produced_by"] = "lio-bench data convert"
        log("checking equivalence of the converted bag")
        dst_summary = summarize(tmp, topics)
        src_summary = summarize(src, topics)
        problems = compare(src_summary, dst_summary)
        if problems:
            raise ConversionError("converted bag differs from source:\n  " + "\n  ".join(problems)
                                  + f"\n(left in {tmp})")
        tmp.rename(dst)
        record.update(source_summary=src_summary, destination_summary={**dst_summary, "path": str(dst)},
                      problems=[], metadata=rosbag2_metadata(dst), equivalent=True)
        write_json_atomic(prov, record)
        return record

    log("summarising source and destination (reads both bags)")
    src_summary, dst_summary = summarize(src, topics), summarize(dst, topics)
    problems = compare(src_summary, dst_summary)
    record.update(source_summary=src_summary, destination_summary=dst_summary, problems=problems,
                  metadata=rosbag2_metadata(dst), equivalent=not problems)
    write_json_atomic(prov, record)
    return record


def _previous_producer(prov: Path) -> str:
    if prov.exists():
        return json.loads(prov.read_text()).get("produced_by", "unknown")
    return "pre-existing (not produced by lio-bench; e.g. ranger-lio scripts/convert_bag.sh)"
