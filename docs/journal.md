# Experiment journal

One entry per run, newest last. The run record (`runs/<run_id>/run.json`) is the source of
truth; this journal is the readable narrative that links runs into a tuning history.
Record every attempt, including failed and reverted ones. See [protocol.md](protocol.md) §6.

## Workflow

```bash
run=$(lio-bench run init --method fast_lio2 --sequence exp14 --config <resolved.yaml> \
        --hypothesis "..." --change "..." --parent <run_id> --playback-rate 0.5)
# ... run the method, export its trajectory as TUM ...
lio-bench eval exp14 <trajectory.tum> --frame imu --run-dir "$run"
lio-bench run close "$run" --interpretation "..." --decision keep|revert|investigate
lio-bench log "$run"          # mirror to W&B (online unless WANDB_MODE=offline)
```

## Entry template

```markdown
### <run_id>
- **Method / sequence / split:**
- **Parent:** <run_id or "none (baseline)">
- **Hypothesis:**
- **Change:** <exact parameter or code change; one parameter family at a time>
- **Config hash:**
- **Result:** status, coverage, ATE RMSE / p95, RPE 1 s / 10 s, runtime
- **Interpretation:**
- **Decision:** keep | revert | investigate
```

## Entries

### 20260915T125456Z_fast_lio2_exp14
- **Method / sequence / split:** fast_lio2 / exp14 / tune
- **Parent:** none (baseline)
- **Hypothesis:** First FAST-LIO2 integration on exp14: dataset-adapted config (point-time
  adapter, blind zone, T_I_L extrinsic) with no tuning yet.
- **Change:** First run of this method; no parent.
- **Config hash:** `ac054ee5bed3a7818239b5115579636aa70b12a70d3eb38d869847491b8d30fa`
- **Result:** status ok, coverage 99.6% (686/689); ATE RMSE 0.160 m, median 0.105 m,
  p95 0.333 m, rot RMSE 4.86 deg; RPE 1 s trans RMSE 0.057 m / rot RMSE 1.18 deg (638 pairs);
  RPE 10 s trans RMSE 0.210 m / rot RMSE 2.96 deg (536 pairs). Played at 0.5x in
  `docker/fast_lio2` (`lio-benchmark/fast_lio2:dev`, hku-mars/FAST_LIO @ `7cc4175`).
- **Interpretation:** First verified end-to-end FAST-LIO2 baseline on exp14, dataset-adapted
  but not tuned. Translational accuracy is already solid for a first pass; rotational ATE
  RMSE (4.86 deg) is high relative to translation and worth investigating before further
  tuning, e.g. the untuned `acc_cov`/`gyr_cov` defaults or the extrinsic rotation sign.
- **Decision:** investigate

### 20260915T133833Z_fast_lio2_exp14
- **Method / sequence / split:** fast_lio2 / exp14 / tune
- **Parent:** `20260915T125456Z_fast_lio2_exp14`
- **Hypothesis:** The baseline's high rotational ATE RMSE (4.86 deg vs 0.16 m translation) is
  driven by `mapping.acc_cov`/`gyr_cov` (0.1/0.1), hku-mars's generic Velodyne-config
  placeholders, not measured from this rig's BMI085. Setting them from real static noise
  should let the ESKF trust the IMU more appropriately and reduce rotational drift.
- **Change:** `mapping.acc_cov`: 0.1 -> 3.677e-04, `mapping.gyr_cov`: 0.1 -> 1.183e-05,
  measured as std² over `calibration/imu_noise_calibration.bag` (`lio-bench imu-noise`,
  `src/lio_benchmark/inspection.py::imu_noise`, a simple white-noise std, not a full
  Allan-variance fit). `b_acc_cov`/`b_gyr_cov` left at defaults (1e-4) — one parameter family
  per protocol §6.
- **Config hash:** `fb3639fd391d7c10ff0e23aa51bdeb7f26e6663bc19986527e7604bf95f63ed5`
- **Result:** status ok, coverage 99.6% (686/689, unchanged); ATE RMSE 0.125 m (was 0.160),
  median 0.079 m (was 0.105), p95 0.236 m (was 0.333), rot RMSE 1.34 deg (was 4.86); RPE 1 s
  trans RMSE 0.033 m (was 0.057) / rot RMSE 0.32 deg (was 1.18); RPE 10 s trans RMSE 0.126 m
  (was 0.210) / rot RMSE 0.91 deg (was 2.96).
- **Interpretation:** Confirms the baseline hypothesis — the untuned noise covariance, not
  the extrinsic sign, was the leading cause of the high rotational ATE. Every metric improved,
  rotation substantially so. `b_acc_cov`/`b_gyr_cov` (bias random-walk) are still untuned
  defaults; a follow-up Allan-variance fit of those is the natural next candidate if further
  improvement is wanted, but this result is already a clear keep.
- **Decision:** keep

### 20260915T152627Z_fast_lio2_exp14
- **Method / sequence / split:** fast_lio2 / exp14 / tune
- **Parent:** `20260915T133833Z_fast_lio2_exp14`
- **Hypothesis:** Measured point spacing on exp14 is ~0.36 cm at median range (1.1 m) and
  ~3.4 cm at p99 range (10.2 m), derived from `points_per_scan` (60948.5 median / 32 rings =
  0.189 deg azimuthal resolution). The default `filter_size_surf`/`filter_size_map` (0.5 m)
  voxel-merges 15-140x more points than the scene's actual density, destroying local plane
  detail in this close-range indoor sequence. A finer, indoor-scale voxel should preserve more
  geometric structure for registration.
- **Change:** `launch.filter_size_surf`/`filter_size_map`: 0.5 -> 0.2 (these are
  `mapping_velodyne.launch` top-level params, not nested under `mapping:` in FAST-LIO2's own
  schema — now recorded in `configs/fast_lio2/hilti22.yaml`'s `launch:` section so the
  resolved config actually captures them, and read by `scripts/run_fast_lio2.sh`).
- **Config hash:** `a4ef79abf697a2f56cc502c93223060ff802b1d2f1f81d12998a82cc721379a4`
- **Result:** status ok, coverage 99.6% (686/689, unchanged); ATE RMSE 0.041 m (was 0.125),
  median 0.027 m (was 0.079), p95 0.069 m (was 0.236), rot RMSE 0.83 deg (was 1.34); RPE 1 s
  trans RMSE 0.019 m (was 0.033) / rot RMSE 0.27 deg (was 0.32); RPE 10 s trans RMSE 0.056 m
  (was 0.126) / rot RMSE 0.67 deg (was 0.91).
- **Interpretation:** Confirms the hypothesis strongly — every metric improved substantially,
  ATE trans RMSE by 67%. The 0.5 m default was clearly far too coarse for this sequence.
- **Decision:** keep

### 20260915T152922Z_fast_lio2_exp14
- **Method / sequence / split:** fast_lio2 / exp14 / tune
- **Parent:** `20260915T133833Z_fast_lio2_exp14`
- **Hypothesis:** Same measured point-spacing reasoning as the 0.2 m sibling; testing a more
  aggressive 0.1 m voxel to see whether accuracy keeps improving with finer resolution or
  starts to degrade.
- **Change:** `launch.filter_size_surf`/`filter_size_map`: 0.5 -> 0.1 (sibling of
  `20260915T152627Z`, same parent).
- **Config hash:** `c0409dfd9d381d0660d1d14081de2d495cfebd51962789aba9a2dae9978ea1bc`
- **Result:** status ok, coverage 99.6% (686/689, unchanged); ATE RMSE 0.080 m, median 0.056 m,
  p95 0.144 m, rot RMSE 1.33 deg; RPE 1 s trans RMSE 0.033 m / rot RMSE 0.38 deg; RPE 10 s
  trans RMSE 0.147 m / rot RMSE 1.40 deg.
- **Interpretation:** Non-monotonic — finer is not always better. Vs. parent (0.5 m, still
  untouched there): ATE trans improved (0.125->0.080) but ATE rot was flat (1.34->1.33) and
  RPE 10 s got worse in both trans and rot. Vs. the 0.2 m sibling: strictly worse on every
  metric. Likely cause: at 0.1 m the local map fragments into voxels with too few points to
  fit a stable plane, especially at longer range, making registration noisier. 0.2 m is a
  measured sweet spot for this sequence's point density, not the finest tested value.
- **Decision:** revert

### Bayesian sweep `yf5zcpr1` (phase 2, `docs/protocol.md` §6.2) — 15 trials, no keep
- **Method / sequence / split:** fast_lio2 / exp14 / tune
- **Parent:** `20260915T152627Z_fast_lio2_exp14` (current kept baseline)
- **Search region (from phase 1):** `acc_cov`/`gyr_cov` log-uniform around the measured
  values (1e-5–1e-2, 1e-6–1e-3); `b_acc_cov`/`b_gyr_cov` log-uniform 1e-6–1e-2 (never
  measured); `voxel_size` (coupled `filter_size_surf`/`filter_size_map`) uniform 0.1–0.4 m,
  bracketing the found sweet spot; `point_filter_num` int 1–6; `max_iteration` int 2–6.
  `wandb.sweep`, method `bayes`, objective `ate.trans_m.rmse` (minimize). Trials: `scripts/
  fast_lio2_sweep.py`, each a full run record (`*_fast_lio2_exp14_sweep` in `runs/`) tagged
  `sweep` in W&B, same as any other run — `docker/fast_lio2` unchanged. (A separate 1-trial
  smoke-test sweep, `cmnwpb0x`, run `20260915T171523Z_fast_lio2_exp14_sweep`, validated the
  script beforehand with the same search space; its result — trans RMSE 0.0453 m — is
  consistent with the 15 below but isn't counted as one of them.)
- **Result:** 15 trials, all status ok, coverage unchanged. Best by objective: trans RMSE
  0.0406 m (run `20260915T175257Z_fast_lio2_exp14_sweep`), essentially tied with the
  baseline's 0.0413 m, but its rotation RMSE (0.95°) is worse than the baseline's 0.83°. No
  trial beat the baseline on *both* metrics — the best-rotation trial (0.68°, run
  `20260915T175011Z_fast_lio2_exp14_sweep`) had worse translation (0.0486 m). Trans RMSE
  across all 15 trials ranged 0.041–0.106 m; the baseline sits at the good end.
- **Interpretation:** The sweep confirms rather than improves on phase 1 — the manually
  measured/found region (real noise covariance, 0.2 m voxel) was already close to a local
  optimum for `ate.trans_m.rmse` on exp14, at least across this parameter set and 15 trials.
  `point_filter_num`/`max_iteration` varied across trials without a clear pattern, suggesting
  they're not major levers here. No config change is warranted; the existing baseline stays
  the frozen config. A negative result, but a real one — worth recording per protocol §6.2
  rather than treated as if the sweep never ran.
- **Decision:** revert (no trial promoted; baseline config unchanged)
