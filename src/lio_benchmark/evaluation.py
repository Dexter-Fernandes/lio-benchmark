"""Gap-aware trajectory evaluation against the dense 6-DoF ground truth.

Definitions (docs/protocol.md is the normative description):

Association
    Errors are evaluated at ground-truth timestamps. The estimate is interpolated at a
    ground-truth time t (linear position, SLERP rotation) only between two consecutive estimate
    poses at most `max_gap_s` apart. A ground-truth time that coincides with an estimate pose
    (within 1 us) is associated even at the edge of a gap. There is no extrapolation beyond
    the first or last estimate pose.
Alignment
    One SE(3) transform (Umeyama, no scale) maps estimate positions to ground-truth positions
    over all associated samples. It removes the arbitrary estimator world frame only.
ATE
    Per-sample position error |p_gt - (R p_est + t)| in metres, and rotation error
    angle(R_gt^T R R_est) in degrees, summarised as RMSE / mean / median / p95 / max.
RPE
    For each associated sample i and each delta d, the associated sample j nearest to t_i + d
    (within `rpe_match_tol_s`) and in the same gap-free segment. The error is
    E = (G_i^-1 G_j)^-1 (P_i^-1 P_j); translation |t_E| in metres, rotation angle(R_E) in
    degrees. RPE is independent of the alignment.
Coverage
    Share of ground-truth samples associated. A run below `min_coverage` is `incomplete`; a
    run with too few samples to align is `failed`. Coverage is always reported with accuracy
    so a partial run cannot look better than a complete one.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import yaml
from scipy.spatial.transform import Rotation

from .se3 import SE3
from .trajectory import SparsePoints, Trajectory

EXACT_TOL_S = 1e-6


@dataclass(frozen=True)
class EvalConfig:
    max_gap_s: float = 0.25
    rpe_deltas_s: tuple[float, ...] = (1.0, 10.0)
    rpe_match_tol_s: float = 0.05
    min_coverage: float = 0.95
    min_pairs: int = 10

    @classmethod
    def from_yaml(cls, path) -> "EvalConfig":
        raw = yaml.safe_load(Path(path).read_text()) or {}
        if "rpe_deltas_s" in raw:
            raw["rpe_deltas_s"] = tuple(float(d) for d in raw["rpe_deltas_s"])
        return cls(**raw)


@dataclass
class Association:
    gt_idx: np.ndarray       # indices of associated ground-truth samples
    est: Trajectory          # estimate interpolated at gt.t[gt_idx]
    segment: np.ndarray      # gap-free segment id of each associated sample


def associate(ref_t: np.ndarray, est: Trajectory, max_gap_s: float) -> Association:
    """Interpolate `est` at the reference times it covers without crossing gaps."""
    ref_t = np.asarray(ref_t, dtype=float)
    n = len(est)
    if n == 0:
        return Association(np.array([], int), Trajectory(np.empty(0), np.empty((0, 3)), np.empty((0, 4))),
                           np.array([], int))
    i0 = np.searchsorted(est.t, ref_t, side="right") - 1        # est.t[i0] <= t
    inside = i0 >= 0
    i0c = np.clip(i0, 0, n - 1)
    exact = inside & (np.abs(ref_t - est.t[i0c]) <= EXACT_TOL_S)
    i1c = np.clip(i0c + 1, 0, n - 1)
    bridged = inside & (i0 < n - 1) & ((est.t[i1c] - est.t[i0c]) <= max_gap_s)
    valid = exact | bridged

    idx = np.nonzero(valid)[0]
    a, b = i0c[idx], np.where(exact[idx], i0c[idx], i1c[idx])
    span = est.t[b] - est.t[a]
    alpha = np.where(span > 0, (ref_t[idx] - est.t[a]) / np.where(span > 0, span, 1.0), 0.0)

    p = est.p[a] + alpha[:, None] * (est.p[b] - est.p[a])
    Ra, Rb = Rotation.from_quat(est.q[a]), Rotation.from_quat(est.q[b])
    q = (Ra * Rotation.from_rotvec(alpha[:, None] * (Ra.inv() * Rb).as_rotvec())).as_quat() if len(idx) else np.empty((0, 4))

    gap_ends = est.t[1:][np.diff(est.t) > max_gap_s]
    segment = np.searchsorted(gap_ends, ref_t[idx], side="right")
    return Association(idx, Trajectory(ref_t[idx], p, q), segment)


class DegenerateAlignment(ValueError):
    pass


def umeyama_se3(src: np.ndarray, dst: np.ndarray) -> SE3:
    """Rigid (no scale) T minimising sum |dst - (R src + t)|^2."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    if len(src) < 3:
        raise DegenerateAlignment("fewer than 3 points")
    mu_s, mu_d = src.mean(0), dst.mean(0)
    sv = np.linalg.svd(src - mu_s, compute_uv=False)
    if sv[1] < 1e-9 * max(sv[0], 1.0):
        raise DegenerateAlignment("estimate positions are (nearly) collinear; rotation is unobservable")
    S = (dst - mu_d).T @ (src - mu_s) / len(src)
    U, _, Vt = np.linalg.svd(S)
    W = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        W[2, 2] = -1.0
    R = U @ W @ Vt
    return SE3(R, mu_d - R @ mu_s)


def stats(x) -> dict:
    x = np.asarray(x, dtype=float)
    if not len(x):
        return {"n": 0, "rmse": None, "mean": None, "median": None, "p95": None, "max": None}
    return {"n": int(len(x)), "rmse": float(np.sqrt(np.mean(x**2))), "mean": float(x.mean()),
            "median": float(np.median(x)), "p95": float(np.percentile(x, 95)), "max": float(x.max())}


def rpe(gt: Trajectory, assoc: Association, delta_s: float, tol_s: float) -> dict:
    ta = assoc.est.t
    if len(ta) < 2:
        return {"delta_s": delta_s, "trans_m": stats([]), "rot_deg": stats([])}
    target = ta + delta_s
    j = np.clip(np.searchsorted(ta, target), 1, len(ta) - 1)
    j = np.where(np.abs(ta[j - 1] - target) < np.abs(ta[j] - target), j - 1, j)
    i = np.arange(len(ta))
    ok = (np.abs(ta[j] - target) <= tol_s) & (j > i) & (assoc.segment[j] == assoc.segment[i])
    i, j = i[ok], j[ok]

    g = gt.subset(assoc.gt_idx)
    Rg, Re = g.rotations, assoc.est.rotations
    # Relative motions i -> j expressed in frame i, for ground truth and estimate.
    Rg_ij = Rg[i].inv() * Rg[j]
    tg_ij = Rg[i].inv().apply(g.p[j] - g.p[i])
    Re_ij = Re[i].inv() * Re[j]
    te_ij = Re[i].inv().apply(assoc.est.p[j] - assoc.est.p[i])
    # E = (G_ij)^-1 P_ij
    t_err = np.linalg.norm(Rg_ij.inv().apply(te_ij - tg_ij), axis=1) if len(i) else np.empty(0)
    r_err = np.degrees((Rg_ij.inv() * Re_ij).magnitude()) if len(i) else np.empty(0)
    return {"delta_s": delta_s, "trans_m": stats(t_err), "rot_deg": stats(r_err)}


@dataclass
class EvalResult:
    metrics: dict
    assoc: Association | None = None
    aligned: Trajectory | None = None
    ate_trans: np.ndarray = field(default_factory=lambda: np.empty(0))
    ate_rot: np.ndarray = field(default_factory=lambda: np.empty(0))


def _coverage(gt: Trajectory, est: Trajectory, assoc: Association, cfg: EvalConfig) -> dict:
    n_gt, n_assoc = len(gt), len(assoc.gt_idx)
    in_span = (est.t[:-1] < gt.t[-1]) & (est.t[1:] > gt.t[0]) if len(est) > 1 else np.array([], bool)
    gaps = np.diff(est.t)[in_span] if len(est) > 1 else np.empty(0)
    big = gaps[gaps > cfg.max_gap_s]
    return {
        "n_gt": n_gt,
        "n_associated": n_assoc,
        "coverage": n_assoc / n_gt if n_gt else 0.0,
        "gt_span_s": [float(gt.t[0]), float(gt.t[-1])],
        "est_span_s": [float(est.t[0]), float(est.t[-1])] if len(est) else None,
        "n_est_poses": len(est),
        "init_delay_s": float(assoc.est.t[0] - gt.t[0]) if n_assoc else None,
        "end_shortfall_s": float(gt.t[-1] - assoc.est.t[-1]) if n_assoc else None,
        "n_gaps": int(len(big)),
        "max_gap_s": float(gaps.max()) if len(gaps) else None,
    }


def evaluate(gt: Trajectory, est: Trajectory, cfg: EvalConfig = EvalConfig(),
             sparse: SparsePoints | None = None, align: bool = True) -> EvalResult:
    """Evaluate an IMU-frame estimate against IMU-frame ground truth (both in seconds).

    `align=False` skips the SE(3) alignment. It is a diagnostic only (e.g. checking a
    trajectory already expressed in the ground-truth world); reported results always align.
    """
    assoc = associate(gt.t, est, cfg.max_gap_s)
    metrics: dict = {"config": {**asdict(cfg), "rpe_deltas_s": list(cfg.rpe_deltas_s)},
                     "coverage": _coverage(gt, est, assoc, cfg), "reasons": []}
    reasons = metrics["reasons"]

    if len(est) and (est.t[-1] < gt.t[0] or est.t[0] > gt.t[-1]):
        reasons.append(f"no temporal overlap: estimate [{est.t[0]:.3f}, {est.t[-1]:.3f}] vs "
                       f"ground truth [{gt.t[0]:.3f}, {gt.t[-1]:.3f}]; check timestamp units/clock")
    if len(assoc.gt_idx) < cfg.min_pairs:
        reasons.append(f"only {len(assoc.gt_idx)} associated samples (< {cfg.min_pairs})")
        metrics.update(status="failed", alignment=None, ate=None, rpe=None, sparse=None)
        return EvalResult(metrics, assoc)

    g = gt.subset(assoc.gt_idx)
    try:
        T = umeyama_se3(assoc.est.p, g.p) if align else SE3()
    except DegenerateAlignment as exc:
        reasons.append(f"alignment failed: {exc}")
        metrics.update(status="failed", alignment=None, ate=None, rpe=None, sparse=None)
        return EvalResult(metrics, assoc)

    aligned_p = T.act(assoc.est.p)
    aligned_R = Rotation.from_matrix(T.R) * assoc.est.rotations
    aligned = Trajectory(assoc.est.t, aligned_p, aligned_R.as_quat())
    ate_t = np.linalg.norm(g.p - aligned_p, axis=1)
    ate_r = np.degrees((g.rotations.inv() * aligned_R).magnitude())

    metrics["alignment"] = {"method": "umeyama_se3_no_scale" if align else "none", "n_pairs": int(len(ate_t)),
                            "R": T.R.tolist(), "t": T.t.tolist()}
    metrics["ate"] = {"trans_m": stats(ate_t), "rot_deg": stats(ate_r)}
    metrics["rpe"] = {f"{d:g}s": rpe(gt, assoc, d, cfg.rpe_match_tol_s) for d in cfg.rpe_deltas_s}
    metrics["sparse"] = sparse_errors(sparse, est, T, cfg) if sparse is not None else None

    if metrics["coverage"]["coverage"] < cfg.min_coverage:
        reasons.append(f"coverage {metrics['coverage']['coverage']:.3f} < {cfg.min_coverage}")
        metrics["status"] = "incomplete"
    else:
        metrics["status"] = "ok"
    return EvalResult(metrics, assoc, aligned, ate_t, ate_r)


def sparse_errors(sparse: SparsePoints, est: Trajectory, T: SE3, cfg: EvalConfig) -> dict:
    """Aligned-estimate position error at the surveyed control points (secondary metric).

    Uses the alignment fitted to the dense ground truth; control points are not used for
    alignment. Points the estimate does not cover are reported as not covered.
    """
    a = associate(sparse.t, est, cfg.max_gap_s)
    err = np.linalg.norm(sparse.p[a.gt_idx] - T.act(a.est.p), axis=1) if len(a.gt_idx) else np.empty(0)
    per_point = [{"t": float(sparse.t[k]), "error_m": None} for k in range(len(sparse.t))]
    for k, e in zip(a.gt_idx, err):
        per_point[k]["error_m"] = float(e)
    return {"n_points": int(len(sparse.t)), "n_covered": int(len(a.gt_idx)),
            "trans_m": stats(err), "points": per_point}
