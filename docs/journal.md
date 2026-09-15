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
