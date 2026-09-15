import numpy as np
import pytest

from lio_benchmark.trajectory import (TrajectoryError, detect_time_unit, load_sparse,
                                      load_tum, save_tum, validate)
from tests.helpers import T0, loop

# Rows copied from the real exp14 sparse file: the header does not match the 8 columns.
SPARSE_EXP14 = """\
# timestamp_s id x y z
1649764530.9306633 122.60485 17.2029 -1.00685 0 0 0 1
1649764557.0725057 116.6592 20.9433 -4.0908 0 0 0 1
1649764598.958497 101.2687 16.9858 -0.4808 0 0 0 1
"""


def test_tum_round_trip(tmp_path):
    traj = loop(duration=5)
    save_tum(tmp_path / "a.tum", traj)
    back = load_tum(tmp_path / "a.tum")
    np.testing.assert_allclose(back.t, traj.t, atol=1e-9)
    np.testing.assert_allclose(back.p, traj.p, atol=1e-6)


@pytest.mark.parametrize("unit,scale", [("ns", 1e9), ("us", 1e6), ("ms", 1e3), ("s", 1.0)])
def test_timestamp_units_detected_and_converted(tmp_path, unit, scale):
    traj = loop(duration=2)
    assert detect_time_unit(traj.t * scale)[0] == unit
    a = traj.as_array()
    a[:, 0] = traj.t * scale if unit == "s" else np.round(traj.t * scale)
    np.savetxt(tmp_path / "x.tum", a, fmt="%.9f " + " ".join(["%.9f"] * 7))
    back = load_tum(tmp_path / "x.tum")
    np.testing.assert_allclose(back.t, traj.t, atol=1e-3)


def test_rejects_non_unit_quaternion():
    traj = loop(duration=1)
    traj.q[3] *= 1.1
    with pytest.raises(TrajectoryError, match="unit norm"):
        validate(traj)


def test_rejects_non_monotonic_time():
    traj = loop(duration=1)
    traj.t[5] = traj.t[4]
    with pytest.raises(TrajectoryError, match="strictly increasing"):
        validate(traj)


def test_rejects_wrong_column_count(tmp_path):
    (tmp_path / "bad.tum").write_text(f"{T0} 1 2 3\n")
    with pytest.raises(TrajectoryError, match="8 columns"):
        load_tum(tmp_path / "bad.tum")


def test_sparse_parser_reads_rows_not_header(tmp_path):
    f = tmp_path / "exp14_3dof.txt"
    f.write_text(SPARSE_EXP14)
    sp = load_sparse(f)
    assert len(sp.t) == 3
    np.testing.assert_allclose(sp.p[0], [122.60485, 17.2029, -1.00685])
