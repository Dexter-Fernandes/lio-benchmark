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
