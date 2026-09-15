import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from lio_benchmark.evaluation import EvalConfig, associate, evaluate, umeyama_se3
from lio_benchmark.paths import repo_root
from lio_benchmark.trajectory import SparsePoints, Trajectory, load_tum
from tests.helpers import T0, loop, pose_at, rigidly_moved

WORLD_R = Rotation.from_euler("xyz", [0.3, -0.2, 1.1])
WORLD_T = np.array([5.0, -3.0, 2.0])


def test_repository_eval_config_loads():
    cfg = EvalConfig.from_yaml(repo_root() / "configs/eval/default.yaml")
    assert cfg.rpe_deltas_s == (1.0, 10.0) and cfg.max_gap_s == 0.25


def test_identity_gives_zero_error():
    gt = loop()
    m = evaluate(gt, gt).metrics
    assert m["status"] == "ok" and m["coverage"]["coverage"] == 1.0
    assert m["ate"]["trans_m"]["rmse"] < 1e-9 and m["ate"]["rot_deg"]["max"] < 1e-6
    for r in m["rpe"].values():
        assert r["trans_m"]["n"] > 0 and r["trans_m"]["max"] < 1e-9


def test_rigidly_moved_estimate_aligns_to_zero():
    gt = loop()
    est = rigidly_moved(gt, WORLD_R, WORLD_T)
    m = evaluate(gt, est).metrics
    assert m["ate"]["trans_m"]["rmse"] < 1e-9 and m["ate"]["rot_deg"]["max"] < 1e-6
    np.testing.assert_allclose(np.array(m["alignment"]["R"]), WORLD_R.inv().as_matrix(), atol=1e-9)


def test_unaligned_offset_gives_known_ate():
    gt = loop()
    est = rigidly_moved(gt, Rotation.identity(), np.array([1.0, 2.0, 2.0]))
    assert evaluate(gt, est, align=False).metrics["ate"]["trans_m"]["rmse"] == pytest.approx(3.0)
    assert evaluate(gt, est).metrics["ate"]["trans_m"]["rmse"] < 1e-9


def test_known_perturbation_rmse():
    gt = loop()
    sign = np.where(np.arange(len(gt)) % 2 == 0, 1.0, -1.0)
    est = Trajectory(gt.t, gt.p + 0.1 * sign[:, None] * np.array([0, 0, 1.0]), gt.q)
    assert evaluate(gt, est, align=False).metrics["ate"]["trans_m"]["rmse"] == pytest.approx(0.1)
    assert evaluate(gt, est).metrics["ate"]["trans_m"]["rmse"] == pytest.approx(0.1, abs=2e-3)


def test_rpe_of_constant_velocity_drift():
    gt = loop()
    v = np.array([0.01, 0.0, 0.0])                       # 1 cm/s world-frame drift
    est = Trajectory(gt.t, gt.p + (gt.t - gt.t[0])[:, None] * v, gt.q)
    m = evaluate(gt, est).metrics
    assert m["rpe"]["1s"]["trans_m"]["median"] == pytest.approx(0.01, rel=1e-6)
    assert m["rpe"]["10s"]["trans_m"]["median"] == pytest.approx(0.10, rel=1e-6)
    assert m["rpe"]["10s"]["rot_deg"]["max"] < 1e-6


def test_interpolation_between_offset_samples():
    gt = loop(rate=10)
    est = loop(rate=10, offset=0.05, duration=59.9)      # poses half-way between GT samples
    m = evaluate(gt, est).metrics
    assert m["coverage"]["n_associated"] == len(gt) - 2   # first and last GT outside estimate span
    assert m["ate"]["trans_m"]["max"] < 5e-3


def test_hole_is_not_interpolated_and_reduces_coverage():
    gt = loop()
    hole = (gt.t > T0 + 20.0) & (gt.t < T0 + 25.0)
    est = gt.subset(~hole)
    est.p[est.t >= T0 + 25.0] += [0, 0, 50.0]           # a jump across the hole must not be smeared
    res = evaluate(gt, est, align=False)
    assoc_t = res.assoc.est.t
    assert not np.any((assoc_t > T0 + 20.0 + 1e-6) & (assoc_t < T0 + 25.0 - 1e-6))
    assert res.metrics["coverage"]["n_associated"] == len(gt) - hole.sum()
    assert res.metrics["coverage"]["n_gaps"] == 1
    assert res.metrics["coverage"]["max_gap_s"] == pytest.approx(5.0, abs=1e-5)   # 20.0 -> 25.0
    # No 10 s relative-pose pair spans the hole, so the jump never enters RPE.
    assert res.metrics["rpe"]["10s"]["trans_m"]["max"] < 1e-9


def test_truncated_run_is_incomplete():
    gt = loop()
    est = gt.subset(gt.t < T0 + 30.0)
    m = evaluate(gt, est).metrics
    assert m["status"] == "incomplete"
    assert m["coverage"]["coverage"] == pytest.approx(0.5, abs=0.01)
    assert m["coverage"]["end_shortfall_s"] == pytest.approx(30.0, abs=0.11)


def test_late_initialisation_reported():
    gt = loop()
    m = evaluate(gt, gt.subset(gt.t >= T0 + 2.0)).metrics
    assert m["coverage"]["init_delay_s"] == pytest.approx(2.0, abs=1e-6)
    assert m["status"] == "ok"


def test_nanosecond_estimate_file_is_converted(tmp_path):
    gt = loop()
    a = gt.as_array()
    a[:, 0] = np.round(gt.t * 1e9)
    np.savetxt(tmp_path / "est_ns.tum", a, fmt="%d " + " ".join(["%.9f"] * 7))
    est = load_tum(tmp_path / "est_ns.tum")
    m = evaluate(gt, est).metrics
    assert m["status"] == "ok" and m["ate"]["trans_m"]["rmse"] < 1e-5


def test_relative_timestamps_fail_loudly():
    gt = loop()
    est = Trajectory(gt.t - gt.t[0], gt.p, gt.q)         # e.g. estimator stamped from zero
    m = evaluate(gt, est).metrics
    assert m["status"] == "failed" and "no temporal overlap" in m["reasons"][0]


def test_collinear_estimate_fails_alignment():
    gt = loop()
    est = Trajectory(gt.t, np.column_stack([gt.t - gt.t[0], np.zeros(len(gt)), np.zeros(len(gt))]), gt.q)
    m = evaluate(gt, est).metrics
    assert m["status"] == "failed" and "collinear" in m["reasons"][0]


def test_umeyama_recovers_transform():
    rng = np.random.default_rng(0)
    src = rng.normal(size=(100, 3))
    dst = WORLD_R.apply(src) + WORLD_T
    T = umeyama_se3(src, dst)
    np.testing.assert_allclose(T.R, WORLD_R.as_matrix(), atol=1e-10)
    np.testing.assert_allclose(T.t, WORLD_T, atol=1e-10)


def test_sparse_control_points_use_dense_alignment():
    gt = loop()
    est = rigidly_moved(gt, WORLD_R, WORLD_T)
    t_sparse = gt.t[[50, 300, 551]] + 0.03                                  # between GT samples
    sparse = SparsePoints(t_sparse, pose_at(t_sparse).p + [0.0, 0.0, 0.02])
    sp = evaluate(gt, est, sparse=sparse).metrics["sparse"]
    assert sp["n_covered"] == 3
    # 2 cm offset plus the chord error of linear interpolation over 3 cm of a 10 m-radius path
    assert sp["trans_m"]["max"] == pytest.approx(0.02, abs=1e-3)


def test_sparse_points_outside_estimate_not_covered():
    gt = loop()
    est = gt.subset(gt.t < T0 + 30)
    sparse = SparsePoints(np.array([T0 + 10.0, T0 + 50.0]), gt.p[[100, 500]])
    sp = evaluate(gt, est, sparse=sparse).metrics["sparse"]
    assert sp["n_covered"] == 1 and sp["points"][1]["error_m"] is None


def test_association_exact_match_at_gap_edge():
    est = Trajectory(np.array([0.0, 0.1, 1.0, 1.1]), np.zeros((4, 3)), np.tile([0, 0, 0, 1.0], (4, 1)))
    a = associate(np.array([0.05, 0.1, 0.5, 1.0, 1.2]), est, max_gap_s=0.25)
    np.testing.assert_array_equal(a.gt_idx, [0, 1, 3])          # 0.5 is inside the gap, 1.2 past the end
    np.testing.assert_array_equal(a.segment, [0, 0, 1])


def test_ate_matches_evo_on_gapless_case():
    evo_traj = pytest.importorskip("evo.core.trajectory")
    evo_metrics = pytest.importorskip("evo.core.metrics")
    gt = loop()
    rng = np.random.default_rng(1)
    noisy = rigidly_moved(gt, WORLD_R, WORLD_T)
    noisy.p += rng.normal(scale=0.05, size=noisy.p.shape)
    ours = evaluate(gt, noisy).metrics["ate"]["trans_m"]["rmse"]

    def to_evo(tr):
        return evo_traj.PoseTrajectory3D(positions_xyz=tr.p, orientations_quat_wxyz=np.roll(tr.q, 1, axis=1),
                                         timestamps=tr.t)
    ref, est = to_evo(gt), to_evo(noisy)
    est.align(ref, correct_scale=False)
    ape = evo_metrics.APE(evo_metrics.PoseRelation.translation_part)
    ape.process_data((ref, est))
    assert ours == pytest.approx(ape.get_statistic(evo_metrics.StatisticsType.rmse), rel=1e-9)
