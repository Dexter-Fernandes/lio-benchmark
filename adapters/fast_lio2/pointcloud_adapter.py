"""Hilti PandarXT-32 points -> FAST-LIO2's velodyne point layout.

FAST-LIO2's Velodyne handler (hku-mars/FAST_LIO preprocess.cpp) reads a `time` field as
float32 seconds relative to the scan's header stamp. Hilti's `timestamp` field is absolute
epoch seconds (docs/dataset.md); this only re-derives `time`, everything else passes through.
"""
from __future__ import annotations

import numpy as np

OUT_DTYPE = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("intensity", "<f4"),
                      ("ring", "<u2"), ("time", "<f4")])


def to_fast_lio2_points(pts: np.ndarray, header_stamp: float) -> np.ndarray:
    out = np.empty(len(pts), dtype=OUT_DTYPE)
    for name in ("x", "y", "z", "intensity", "ring"):
        out[name] = pts[name]
    out["time"] = (pts["timestamp"].astype(np.float64) - header_stamp).astype(np.float32)
    return out
