#!/usr/bin/env python
"""Per-scan diagnostics from a bag recorded by scripts/run_lio_sam.sh with LIO_SAM_RECORD set.

Shows, for every scan mapOptmization processed: the LM degeneracy flag (published as
odometry_incremental covariance[0], src/mapOptmization.cpp), corner/surf feature counts
(sizes of the feature clouds), and how much the LM output moved in tilt/z versus how much the
IMU-preintegration guess (/odometry/imu_incremental) moved over the same interval -- if the two
track each other, LM is not correcting that axis. Also reports the IMU stream LIO-SAM actually
received (count, max gap) and warning counts from the captured console log.

Usage: lio_sam_diag.py runs/<id>/diag.bag [--log runs/<id>/lio_sam.log] [--until 12] [--every 1]
"""
import argparse
import re
from pathlib import Path

import numpy as np
from rosbags.rosbag1 import Reader
from rosbags.typesys import Stores, get_typestore
from scipy.spatial.transform import Rotation as R

TOPICS = {"odom": "/lio_sam/mapping/odometry_incremental", "guess": "/odometry/imu_incremental",
          "corner": "/lio_sam/feature/cloud_corner", "surf": "/lio_sam/feature/cloud_surface",
          "imu": "/alphasense/imu/oriented"}


def _stamp(msg) -> float:
    return msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9


def _pose(msg):
    p, q = msg.pose.pose.position, msg.pose.pose.orientation
    return _stamp(msg), np.array([p.x, p.y, p.z]), R.from_quat([q.x, q.y, q.z, q.w])


def read(bag: Path) -> dict:
    ts = get_typestore(Stores.ROS1_NOETIC)
    out = {k: [] for k in TOPICS}
    with Reader(bag) as r:
        by_topic = {c.topic: k for c in r.connections for k, t in TOPICS.items() if c.topic == t}
        for conn, _, raw in r.messages():
            k = by_topic.get(conn.topic)
            if k is None:
                continue
            msg = ts.deserialize_ros1(raw, conn.msgtype)
            if k in ("odom", "guess"):
                out[k].append((*_pose(msg), int(round(msg.pose.covariance[0]))))
            elif k == "imu":
                out[k].append(_stamp(msg))
            else:
                out[k].append((_stamp(msg), msg.width * msg.height))
    return out


def tilt_deg(rot: R) -> float:
    """Angle between the body z axis and world z: 0 when level."""
    z = rot.apply([0, 0, 1.0])
    return float(np.degrees(np.arccos(np.clip(z[2], -1, 1))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bag", type=Path)
    ap.add_argument("--log", type=Path, help="captured container stdout/stderr")
    ap.add_argument("--until", type=float, default=float("inf"), help="only rows within this many s of the first scan")
    ap.add_argument("--every", type=int, default=1, help="print every Nth row")
    args = ap.parse_args()
    d = read(args.bag)

    imu = np.array(d["imu"])
    gaps = np.diff(imu) if len(imu) > 1 else np.array([0.0])
    print(f"IMU received: {len(imu)} msgs, span {imu[-1] - imu[0]:.1f}s, max gap {gaps.max() * 1e3:.1f} ms, "
          f"gaps >50ms: {(gaps > 0.05).sum()}")
    if args.log and args.log.exists():
        text = args.log.read_text(errors="replace")
        for pat in ("Not enough features", "Large velocity", "Large bias"):
            print(f"log: '{pat}' x{len(re.findall(pat, text))}")

    odom = d["odom"]
    counts = {k: dict(d[k]) for k in ("corner", "surf")}
    guess_t = np.array([g[0] for g in d["guess"]])
    deg = np.array([o[3] for o in odom])
    print(f"scans processed: {len(odom)}, degenerate on {deg.sum()} ({deg.mean():.0%}); "
          f"features corner median {np.median(list(counts['corner'].values())):.0f} "
          f"surf median {np.median(list(counts['surf'].values())):.0f}")
    print(f"{'t':>6} {'deg':>3} {'corner':>6} {'surf':>6} | {'tilt':>6} {'dTilt':>6} {'dTiltG':>6} | {'z':>6} {'dz':>6} {'dzG':>6}")
    t0 = odom[0][0]
    for i in range(1, len(odom)):
        t, p, rot, flag = odom[i]
        if t - t0 > args.until:
            break
        if i % args.every:
            continue
        tp, pp, rp, _ = odom[i - 1]
        # preintegration guess at the two scan stamps (nearest imu_incremental message at or before)
        ga, gb = np.searchsorted(guess_t, tp, side="right") - 1, np.searchsorted(guess_t, t, side="right") - 1
        if ga >= 0 and gb >= 0:
            _, pga, rga, _ = d["guess"][ga]
            _, pgb, rgb, _ = d["guess"][gb]
            d_tilt_g, dz_g = tilt_deg(rgb) - tilt_deg(rga), pgb[2] - pga[2]
        else:
            d_tilt_g = dz_g = float("nan")
        key = round(t, 3)
        c = next((v for k, v in counts["corner"].items() if abs(k - t) < 1e-3), -1)
        s = next((v for k, v in counts["surf"].items() if abs(k - t) < 1e-3), -1)
        print(f"{t - t0:6.2f} {flag:>3} {c:6d} {s:6d} | {tilt_deg(rot):6.2f} {tilt_deg(rot) - tilt_deg(rp):+6.2f} {d_tilt_g:+6.2f} "
              f"| {p[2]:6.3f} {p[2] - pp[2]:+6.3f} {dz_g:+6.3f}")


if __name__ == "__main__":
    main()
