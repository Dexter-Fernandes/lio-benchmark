"""FAST-LIO2 input adapter: Hilti's absolute per-point timestamp -> FAST-LIO2's relative time.

Synthetic points mirror the measured PandarXT-32 layout (docs/dataset.md): x, y, z, intensity
as f4, absolute `timestamp` as f8 (first point ~header stamp +1us, scan spread ~0.1s), `ring`
as u2.
"""
import numpy as np

from adapters.fast_lio2.pointcloud_adapter import to_fast_lio2_points

HEADER_STAMP = 1_649_764_528.000000


def hilti_points(n=5, header_stamp=HEADER_STAMP, spread=0.1):
    pts = np.zeros(n, dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("intensity", "<f4"),
                             ("timestamp", "<f8"), ("ring", "<u2")])
    pts["x"] = np.arange(n, dtype="f4")
    pts["y"] = np.arange(n, dtype="f4") * 2
    pts["z"] = 1.0
    pts["intensity"] = np.arange(n, dtype="f4") * 10
    pts["timestamp"] = header_stamp + 1e-6 + np.linspace(0, spread, n)
    pts["ring"] = np.arange(n) % 32
    return pts


def test_time_field_is_relative_to_header_stamp():
    pts = hilti_points()
    out = to_fast_lio2_points(pts, HEADER_STAMP)
    expected = (pts["timestamp"] - HEADER_STAMP).astype(np.float32)
    np.testing.assert_allclose(out["time"], expected, atol=1e-7)


def test_xyz_intensity_ring_pass_through_unchanged():
    pts = hilti_points()
    out = to_fast_lio2_points(pts, HEADER_STAMP)
    np.testing.assert_array_equal(out["x"], pts["x"])
    np.testing.assert_array_equal(out["y"], pts["y"])
    np.testing.assert_array_equal(out["z"], pts["z"])
    np.testing.assert_array_equal(out["intensity"], pts["intensity"])
    np.testing.assert_array_equal(out["ring"], pts["ring"])


def test_output_dtype_matches_fast_lio2_velodyne_layout():
    out = to_fast_lio2_points(hilti_points(), HEADER_STAMP)
    assert out.dtype.names == ("x", "y", "z", "intensity", "ring", "time")
    assert out.dtype["time"] == np.dtype("<f4")
    assert out.dtype["ring"] == np.dtype("<u2")
