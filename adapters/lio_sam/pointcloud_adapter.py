"""Hilti PandarXT-32 points -> LIO-SAM's velodyne point layout.

LIO-SAM's VelodynePointXYZIRT (src/imageProjection.cpp, TixiaoShan/LIO-SAM) is byte-identical
in fields to FAST-LIO2's velodyne handler: x,y,z,intensity float32, ring uint16, time float32
seconds relative to the scan's header stamp (`field.name == "time"` is the accepted name;
imageProjection.cpp adds it to `timeScanCur` to deskew each point). Hilti's `timestamp` field
is absolute epoch seconds (docs/dataset.md); this only re-derives `time`, everything else
passes through.
"""
from __future__ import annotations

import numpy as np

OUT_DTYPE = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("intensity", "<f4"),
                      ("ring", "<u2"), ("time", "<f4")])


def to_lio_sam_points(pts: np.ndarray, header_stamp: float) -> np.ndarray:
    out = np.empty(len(pts), dtype=OUT_DTYPE)
    for name in ("x", "y", "z", "intensity", "ring"):
        out[name] = pts[name]
    out["time"] = (pts["timestamp"].astype(np.float64) - header_stamp).astype(np.float32)
    return out
