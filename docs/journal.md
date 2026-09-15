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

### 20260915T183220Z_fast_lio2_exp16 (held-out)
- **Method / sequence / split:** fast_lio2 / exp16 / heldout
- **Parent:** `20260915T152627Z_fast_lio2_exp14` (frozen baseline config)
- **Hypothesis:** Held-out evaluation of the config frozen on exp14 (measured IMU noise
  covariance + 0.2 m voxel; a 15-trial Bayesian sweep found nothing better). No changes made
  in response to this result, per `docs/protocol.md` §6.
- **Change:** None — held-out evaluation, config frozen.
- **Config hash:** `a4ef79abf697a2f56cc502c93223060ff802b1d2f1f81d12998a82cc721379a4`
- **Result:** status ok, coverage 99.9% (1998/2001); ATE RMSE 66.39 m, median 24.65 m, p95
  178.35 m, rot RMSE 62.91°; RPE 1 s trans RMSE 6.07 m / rot RMSE 2.30° (1987 pairs); RPE 10 s
  trans RMSE 45.11 m / rot RMSE 11.93° (1897 pairs).
- **Interpretation:** Catastrophic divergence, not a coverage/dropout failure (coverage is
  fine, no gaps). Inspecting the raw trajectory: positions stay in a sane range (roughly
  -17..+13 m per axis, z rising to ~7 m — plausible for the "attic_to_upper_gallery"
  multi-floor transition) for the first ~170 s, then blow up — at t=170s position is
  `[12.6, -10.8, 0.9]`, by t=190s `[153, 140, 14]`, ending at `[330, 159, 60]` — an
  exponentially accelerating runaway characteristic of an IESKF that lost tracking in a
  degenerate area and never recovered. exp18 (below) shows the frozen config generalizes
  reasonably to a held-out sequence in general, which makes this look like a sequence-specific
  trigger (plausibly the attic transition itself) rather than evidence the tuning doesn't
  transfer. Root cause of the trigger is not yet investigated — open.
- **Decision:** investigate

### 20260915T183321Z_fast_lio2_exp18 (held-out)
- **Method / sequence / split:** fast_lio2 / exp18 / heldout
- **Parent:** `20260915T152627Z_fast_lio2_exp14` (frozen baseline config)
- **Hypothesis:** Held-out evaluation of the same frozen config. No changes made in response
  to this result, per `docs/protocol.md` §6.
- **Change:** None — held-out evaluation, config frozen.
- **Config hash:** `a4ef79abf697a2f56cc502c93223060ff802b1d2f1f81d12998a82cc721379a4`
- **Result:** status ok, coverage 99.6% (786/789); ATE RMSE 0.2068 m, median 0.1496 m, p95
  0.3747 m, rot RMSE 2.258°; RPE 1 s trans RMSE 0.0540 m / rot RMSE 0.708° (718 pairs); RPE
  10 s trans RMSE 0.2163 m / rot RMSE 2.221° (616 pairs).
- **Interpretation:** A normal, bounded generalization gap, not a failure — accuracy degrades
  roughly 5x on translation and 2.7x on rotation versus exp14 (the sequence the config was
  tuned on), consistent with applying a frozen config to a different scene without further
  tuning. RPE stays sane at both 1 s and 10 s (no runaway growth), unlike exp16's divergence.
  This is evidence the frozen config generalizes reasonably in general.
- **Decision:** keep

### 20260915T214917Z_lio_sam_exp14
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** none (baseline)
- **Hypothesis:** First LIO-SAM integration on exp14: dataset-adapted baseline (Madgwick
  orientation adapter, point-cloud adapter, `T_L_I` extrinsics, 0.1 m blind zone, GPS/loop
  closure disabled), no tuning yet — noise/leaf-size/keyframe params left at upstream
  defaults, deferred to the phase-2 sweep since phase-1 manual tuning is explicitly skipped
  for this method (confirmed decision, see `docs/methods.md` "LIO-SAM integration").
- **Change:** first run of this method; no parent.
- **Config hash:** `de4e1512999fd9c3c858926d26019dfb6cb28b1c0ef53f2ba55b0ff52ccf4cbe`
- **Result:** status ok, coverage 99.3% (684/689). ATE trans RMSE **349.10 m**, median
  180.45 m, p95 707.47 m; ATE rot RMSE **124.74 deg**. RPE 1s trans RMSE 156.02 m / rot
  64.03 deg; RPE 10s trans RMSE 337.49 m / rot 107.23 deg.
- **Interpretation:** Catastrophic divergence on exp14 itself, not a normal baseline gap —
  positions grow from a plausible few metres to hundreds of metres within the 74 s sequence.
  The run log shows 36 `"Large velocity, reset IMU-preintegration!"` warnings and 2
  `"Not enough features!"` warnings starting partway through, i.e. a sustained
  preintegration/scan-matching feedback loop, not a one-off blip. Likely contributors, not
  isolated here (phase-1 manual root-causing is explicitly out of scope for this method): (1)
  the Madgwick filter's accel-based tilt correction assumes near-static conditions to treat
  the accelerometer as a gravity reference, which a handheld, fast-moving rig violates during
  motion, and `imuRPYWeight: 0.01` feeds that synthesized roll/pitch into
  `mapOptmization`'s pose graph as a soft constraint; (2) `Horizon_SCAN: 1800` is a
  datasheet-derived estimate for the PandarXT-32, not a measured value, and may not match
  this sensor's real per-scan azimuth binning (consistent with the feature-count warnings);
  (3) every noise/leaf-size/keyframe param is still at LIO-SAM's own upstream default. (1)
  and (3) are directly addressed by the sweep's search dimensions; (2) is a fixed
  dataset-adaptation choice, not a sweep parameter, and is worth revisiting if the sweep
  doesn't recover a reasonable trajectory.
- **Decision:** investigate

### Bayesian sweep `udrqijbp` (phase 2, `docs/protocol.md` §6.2, phase 1 explicitly skipped) — 8 trials, no keep
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T214917Z_lio_sam_exp14` (catastrophically divergent baseline, decision
  investigate)
- **Search region:** wide, centered on LIO-SAM's own upstream defaults (`config/params.yaml`),
  **not** phase-1-measured — this method's phase-1 manual tuning is explicitly skipped
  (confirmed decision, `docs/methods.md`). Per `docs/protocol.md` §6.2 this is a documented
  deviation ("sweeping without a phase-1-justified region is guessing with extra steps, not a
  real phase 2"), not equivalent rigor to `fast_lio2_sweep.py`'s measured-region search. IMU
  noise (4 params) log-uniform 1-2 orders of magnitude either side of upstream defaults;
  feature/registration leaf sizes (3 params) uniform 0.05-1.0 m; keyframe distance/angle
  thresholds (2 params) uniform 0.1-2.0 m / 0.05-0.5 rad. `wandb.sweep`, method `bayes`,
  objective `ate.trans_m.rmse` (minimize). 8 trials (not FAST-LIO2's 15) sized to this
  hardware given LIO-SAM's heavier per-trial runtime. `scripts/lio_sam_sweep.py`.
- **Result:** 8 trials, all status ok. Translation RMSE varied enormously across trials
  (7.9 m to 2877 m), but **rotation RMSE stayed catastrophically bad in every single trial**
  (100-170°, i.e. essentially no usable heading estimate) regardless of which IMU-noise/
  leaf-size/keyframe values were sampled:

  | trial | ATE trans RMSE (m) | ATE rot RMSE (deg) |
  |---|---|---|
  | solar-sweep-3 (best by objective) | 7.95 | 170.23 |
  | wandering-sweep-2 | 17.17 | 122.21 |
  | sweet-sweep-5 | 28.34 | 158.26 |
  | worthy-sweep-7 | 360.42 | 130.24 |
  | revived-sweep-6 | 362.84 | 129.25 |
  | volcanic-sweep-1 | 463.48 | 134.99 |
  | rural-sweep-4 | 466.02 | 126.81 |
  | lyric-sweep-8 | 2877.37 | 119.83 |
  | baseline (parent) | 349.10 | 124.74 |

  Best by the chosen objective (translation RMSE): `solar-sweep-3`
  (`imuAccNoise=1.475e-5, imuGyrNoise=1.784e-3, imuAccBiasN=2.033e-7, imuGyrBiasN=5.060e-4,
  odometrySurfLeafSize=0.897, mappingCornerLeafSize=0.152, mappingSurfLeafSize=0.978,
  keyframe dist=1.763 m, angle=0.099 rad`) — but its rotation RMSE (170.2°) is *worse* than
  the baseline's (124.7°), the same "no trial beats baseline on both metrics" pattern
  FAST-LIO2's own sweep found, just far more extreme here.
- **Interpretation:** The complete lack of any trend in rotation RMSE across a 9-dimensional,
  wide-range sweep of noise/leaf-size/keyframe params strongly suggests the rotation failure
  is **not** something this parameter family can fix — it points at something structural,
  most plausibly the Madgwick orientation adapter (`adapters/lio_sam/orientation_filter.py`):
  its accel-based tilt correction assumes near-static conditions to treat the accelerometer
  as a gravity reference, which a handheld, fast-moving rig genuinely violates during motion,
  independent of any of LIO-SAM's own tunable params. This is exactly the kind of root cause
  phase-1 manual/hypothesis-driven investigation (`docs/protocol.md` §6.1, explicitly skipped
  for this method per the confirmed decision) exists to catch before reaching a sweep — its
  absence here is a direct, visible cost of that decision, not a hidden one.
- **Decision:** revert (no trial promoted; `configs/lio_sam/hilti22.yaml` unchanged and
  remains the frozen config, matching FAST-LIO2's "no trial beats baseline on both metrics ->
  keep" precedent). The rotation failure is flagged **open/investigate**, not resolved, ahead
  of held-out evaluation below.

### Map capture repeats (`_mapcapture`, 20260915T1905-1907Z) — pcd_save_en, rate 1.0, no sim-time
- **Method / sequence / split:** fast_lio2 / exp14+exp16+exp18 / tune+heldout
- **Parents:** `20260915T133833Z_fast_lio2_exp14`, `20260915T152627Z_fast_lio2_exp14`,
  `20260915T183220Z_fast_lio2_exp16`, `20260915T183321Z_fast_lio2_exp18` (one repeat each)
- **Hypothesis:** Not a tuning attempt — repeats of the four runs above to capture the map
  artifact (`pcd_save.pcd_save_en`, previously off) now that `configs/fast_lio2/hilti22.yaml`
  enables it by default, and at the new default playback rate 1.0 (was 0.5, real-time rather
  than half-speed).
- **Change:** `pcd_save.pcd_save_en: false -> true`; playback rate 0.5 -> 1.0. Also fixed a
  real bug found while implementing this: `scripts/run_fast_lio2.sh` set `/use_sim_time true`
  and played the bag with `rosbag play --clock`, but FAST-LIO2's `fastlio_mapping` only saves
  its PCD map on `SIGINT` (its registered signal handler) — and `ros::Rate::sleep()` in its
  main loop blocks on `/clock` under sim time, which stops advancing the moment `rosbag play`
  finishes. The node's main loop (which only checks the shutdown flag between `rate.sleep()`
  calls) could never wake up to see it, so it hung forever after `SIGINT` and no map was ever
  written even with `pcd_save_en` on. Fixed by dropping `--clock`/`use_sim_time` entirely
  (FAST-LIO2 and the adapters key off each message's own `header.stamp`, never
  `ros::Time::now()`, so wall-clock ROS time costs nothing and sidesteps the freeze).
- **Result:** All 4 repeats reproduced their parent's metrics almost exactly (e.g. exp16:
  66.39 m / 62.91° both times, confirming the divergence is deterministic here, not a fluke),
  confirming the sim-time removal and rate change don't change estimation behavior. Each
  produced a `map.pcd` (337-905 MB) and a rendered `map.png` (`plots.plot_pcd_map`, Open3D
  headless/EGL, top-down orthographic, colored by height). exp16's map is the notable one: a
  clean, coherent multi-room structure for the pre-divergence portion of the trajectory, then
  a dense tangled mass of misregistered points where the filter diverged — visual confirmation
  of the failure described above.
- **Interpretation:** Artifact-capture repeats, not new findings; each keeps its parent's
  decision. Useful side effect: independently confirms run-to-run determinism for this method
  on this hardware (protocol §6.1 calls for checking this).
- **Decision:** keep (exp14 x2, exp18); investigate (exp16, matching its parent)
