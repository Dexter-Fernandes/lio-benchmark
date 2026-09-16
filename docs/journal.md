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

### 20260915T221224Z_lio_sam_exp16 (held-out)
- **Method / sequence / split:** lio_sam / exp16 / heldout
- **Parent:** `20260915T214917Z_lio_sam_exp14` (frozen config, sweep found no improvement)
- **Hypothesis:** Held-out evaluation of the frozen config (unchanged since the sweep beat
  baseline on neither metric). No changes made in response to this result, per
  `docs/protocol.md` §6.
- **Change:** none — held-out evaluation, config frozen.
- **Config hash:** `de4e1512999fd9c3c858926d26019dfb6cb28b1c0ef53f2ba55b0ff52ccf4cbe` (identical
  to the baseline's, confirming the config really is unchanged)
- **Result:** status **incomplete**, coverage only 83.7% (1674/2001). ATE trans RMSE
  **2297.30 m**, median 1402.54 m, p95 4521.68 m; ATE rot RMSE **141.66 deg**. RPE 1s trans
  RMSE 759.83 m / rot 71.31 deg; RPE 10s trans RMSE 2215.87 m / rot 97.24 deg.
- **Interpretation:** Catastrophic divergence, consistent with and worse than the exp14
  baseline and every sweep trial — the same systemic rotation failure (100+ deg RMSE
  regardless of config) flagged in the sweep entry above as most plausibly the Madgwick
  orientation adapter under this rig's fast handheld motion, not something a parameter
  search over LIO-SAM's own noise/leaf-size/keyframe params can fix. Not tuned around per
  protocol.
- **Decision:** investigate

### 20260915T221224Z_lio_sam_exp18 (held-out)
- **Method / sequence / split:** lio_sam / exp18 / heldout
- **Parent:** `20260915T214917Z_lio_sam_exp14` (frozen config, sweep found no improvement)
- **Hypothesis:** Held-out evaluation of the frozen config. No changes made in response to
  this result, per `docs/protocol.md` §6.
- **Change:** none — held-out evaluation, config frozen.
- **Config hash:** `de4e1512999fd9c3c858926d26019dfb6cb28b1c0ef53f2ba55b0ff52ccf4cbe`
- **Result:** status **incomplete**, coverage only 78.5% (619/789). ATE trans RMSE
  **286.51 m**, median 102.38 m, p95 785.28 m; ATE rot RMSE **147.20 deg**. RPE 1s trans
  RMSE 128.04 m / rot 54.93 deg; RPE 10s trans RMSE 313.82 m / rot 86.94 deg.
- **Interpretation:** Same systemic rotation failure as exp14 and exp16 — every LIO-SAM run
  in this integration, baseline, all 8 sweep trials, and both held-out sequences, shows
  rotation RMSE well over 100 degrees. This consistency across three different sequences and
  9 different parameter configurations makes a structural cause (most likely the orientation
  adapter, see the sweep entry) far more likely than sequence-specific bad luck.
- **Decision:** investigate

### 20260915T222509Z_lio_sam_exp14 (diagnostic, not a sweep trial or kept tuning change)
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T214917Z_lio_sam_exp14` (baseline)
- **Hypothesis:** Is the systemic 100+ deg rotation failure (baseline + all 8 sweep trials +
  both held-out runs) coming from the Madgwick-synthesized orientation being fed into
  `mapOptmization`'s pose graph via `imuRPYWeight`? If rotation RMSE improves substantially
  with `imuRPYWeight=0`, that confirms the orientation adapter (or its influence on the
  graph) as the cause.
- **Change:** `imuRPYWeight: 0.01 -> 0.0` only, isolated single-param diagnostic.
- **Result:** ATE trans RMSE **349.10 -> 29.31 m** (>10x better), ATE rot RMSE **124.74 ->
  129.14 deg** (unchanged, marginally worse). RPE 1s rot RMSE improved 64.03 -> 26.58 deg, but
  RPE 10s rot RMSE stayed large at 81.97 deg.
- **Interpretation:** Partially confirms and partially falsifies the sweep entry's hypothesis.
  `imuRPYWeight` *was* corrupting translation badly via the coupled 6-DoF pose-graph
  optimization -- a real, now-isolated effect. But it is **not** the primary cause of the
  rotation failure itself, which barely moved. Since raw gyro/accel (not the synthesized
  orientation) drive IMU preintegration directly via `extrinsicRot`, and that path is
  unaffected by `imuRPYWeight`, the remaining rotation error more likely comes from IMU
  preintegration or scan-matching itself, not specifically the RPY soft-constraint. The
  extrinsic rotation was re-checked (proper rotation, determinant +1, not a reflection) and
  doesn't look like the cause either. Not conclusive -- genuinely open, and squarely the kind
  of investigation phase-1 manual tuning (explicitly skipped for this method) exists to do.
- **Decision:** investigate. **Do not treat `imuRPYWeight=0` as a fix** -- it's a useful data
  point (isolates one real contributing factor to translation) but does not resolve the
  rotation failure that makes this integration untrustworthy for comparison.

### 20260915T223050Z_lio_sam_exp14 (diagnostic 2: Horizon_SCAN, not a kept change)
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T222509Z_lio_sam_exp14` (imuRPYWeight=0 diagnostic)
- **Hypothesis:** On top of `imuRPYWeight=0`, does correcting `Horizon_SCAN` from the 1800
  datasheet estimate to a measured per-ring point count (mean 1628 / median 1630 over three
  sampled scans) fix the remaining rotation failure?
- **Change:** `imuRPYWeight: 0.01 -> 0.0` (inherited); `Horizon_SCAN: 1800 -> 1630`.
- **Config hash:** `efd44f9aa39855df0458b1f92a8a437d1a92d6041593f6d0c67f7d83f3b35eb4`
- **Result:** status ok, coverage 99.1% (683/689). ATE trans RMSE **373.09 m** (parent 29.31),
  median 126.89 m, p95 990.39 m; ATE rot RMSE **148.60 deg** (parent 129.14). RPE 1 s trans
  147.24 m / rot 70.24 deg; RPE 10 s trans 570.54 m / rot 114.09 deg. 20 "Large velocity"
  resets (parent 0).
- **Interpretation:** Worse on every metric. Falsified as a cause. Note for later: the
  measured 1630 is the *returned* point count per ring, not the sensor's azimuth grid -- the
  raw bag's azimuth step is 0.18 deg (2000 columns; 63.5k points in the fullest scans), so
  1630 bins forced ~18% of returns into already-occupied range-image cells and were dropped,
  which explains "worse" without implicating Horizon_SCAN in the rotation failure. The first
  6 s (rig static per GT) drift identically to the parent (pitch to -30 deg, z to -1.1 m),
  i.e. this change did not touch the actual mechanism.
- **Decision:** revert (config unchanged at 1800; the measured value to try later is 2000).

### 20260915T223332Z_lio_sam_exp14 (diagnostic 3: heading init, not a kept change)
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T222509Z_lio_sam_exp14`
- **Hypothesis:** With `imuRPYWeight=0`, does not seeding the first pose's yaw from the
  Madgwick output (yaw is unobservable without a magnetometer) reduce rotation error?
- **Change:** `imuRPYWeight: 0.01 -> 0.0` (inherited); `useImuHeadingInitialization: true -> false`.
- **Config hash:** `ef07eb74b70ce5db69109f496447368e4606fff5cafb40b131a87fba1e72e497`
- **Result:** status ok, coverage 99.3% (684/689). ATE trans RMSE **804.38 m**, median
  795.22 m, p95 1172.00 m; ATE rot RMSE **125.82 deg**. RPE 1 s trans 103.79 m / rot
  114.86 deg; RPE 10 s trans 414.09 m / rot 117.36 deg. 66 "Large velocity" resets (parent 0,
  original baseline 36).
- **Interpretation:** Much worse in translation and resets, rotation unchanged. A constant
  initial-yaw offset is removed by SE(3) alignment, so this could never have fixed ATE rot;
  that it changed translation at all shows how chaotic the run-to-run trajectory is once the
  estimator is off the rails. Falsified. Same identical static-phase drift as the parent.
- **Decision:** revert.

### 20260915T223606Z_lio_sam_exp14 (diagnostic 4: loop closure on, diagnosis only)
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T222509Z_lio_sam_exp14`
- **Hypothesis:** Is the remaining error ordinary uncorrected drift that loop closure would
  repair (then it is a hard scene, not a bug), or is the online estimate itself broken?
  Loop closure stays disabled in the real config (`docs/protocol.md` #1); diagnosis only.
- **Change:** `imuRPYWeight: 0.01 -> 0.0` (inherited); `loopClosureEnableFlag: false -> true`.
- **Config hash:** `eb87604343a5661a71752135127c6e95ccc2b4ae76e1d96fe618a0ab912a83f7`
- **Result:** status ok, coverage 99.1% (683/689). ATE trans RMSE **340.06 m**, median
  243.84 m, p95 604.24 m; ATE rot RMSE **135.26 deg**. RPE 1 s trans 130.97 m / rot
  88.02 deg; RPE 10 s trans 260.14 m / rot 105.81 deg. 40 "Large velocity" resets.
- **Interpretation:** Worse, not better: the online estimate is genuinely broken, not merely
  uncorrected, and loop closure on a corrupted map adds false matches. Argues for a bug in
  the per-scan estimate. Same identical static-phase drift as the parent.
- **Decision:** revert (never a candidate for the frozen config).

### 20260915T230256Z_lio_sam_exp14 (diagnostic 5: recorded internals, root cause isolated)
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T222509Z_lio_sam_exp14` (same config; `imuRPYWeight: 0.0` is now in
  `configs/lio_sam/hilti22.yaml`)
- **Hypothesis:** Offline analysis of the existing runs showed (a) yaw is tracked (1 s
  yaw-rate correlation with GT 0.69) but roll/pitch are not (0.18 / 0.09), est z spans 72 m
  vs GT 4 m; (b) GT is static for the first 6 s, yet every run tilts identically to ~-30 deg
  pitch and sinks ~1.1 m in that window. Against a fixed single-scan map with nothing
  moving, scan-to-map must be discarding tilt/z updates (`LMOptimization()`'s degeneracy
  projection, hardcoded eigenvalue threshold 100) or skipping optimisation (feature-count
  gate). Record the degenerate flag (`odometry_incremental` covariance[0]), feature-cloud
  sizes, the preintegration guess and the IMU stream LIO-SAM received, and see which fires.
- **Change:** none vs parent; `LIO_SAM_RECORD` diagnostic bag (`scripts/run_lio_sam.sh`) and
  console log captured to the run dir; analysed with the new `scripts/lio_sam_diag.py`.
- **Config hash:** `0875f911a8b8227ba7b42a67126d757b525a5f6fb9ad187e5b48f53672588fec`
  (identical to the parent)
- **Result:** status **incomplete**, coverage 91.3% (629/689). ATE trans RMSE 107.34 m,
  median 75.65 m, p95 181.43 m; ATE rot RMSE 147.09 deg. RPE 1 s trans 130.17 m / rot
  106.08 deg; RPE 10 s trans 150.43 m / rot 99.48 deg. 46 "Large velocity" resets (parent:
  0, same config). Diagnostics: **degenerate flag on 316/349 scans (91%), from scan 1**;
  corner ~480 / surf ~1500 features per scan, "Not enough features" x2; IMU 29539/29539
  received, max gap 2.5 ms.
- **Interpretation:** Root cause isolated to `mapOptmization::LMOptimization()`'s degeneracy
  handling. In the static phase the LM output's per-scan z step equals the preintegration
  guess's z step (e.g. -0.031 vs -0.036 m), so LM is not correcting z at all; the guess
  sinks with a constant ~0.125 m/s^2, matching `imuGravity` 9.805 vs the measured at-rest
  norm 9.663 m/s^2 (`docs/dataset.md`), and the tilt climbs to 34 deg by 6 s while the
  guess's tilt is flat, so the tilt growth is manufactured by the degenerate-projected LM
  step. The hardcoded J^T J eigenvalue threshold of 100 is an outdoor-Velodyne scale;
  rotation-block eigenvalues scale with range squared and this scene's median range is
  ~1 m, so tilt/z read as "degenerate", their updates are zeroed, the pose rides the
  preintegration on those axes, and the corrupted poses feed back through the map and (via
  `correctionNoise2`) through the IMU graph. Feature gate and playback overload are ruled
  out by the counts above. Also learnt: with an identical config this run had 46 resets vs
  the parent's 0, so the earlier single-run diagnostics (Horizon_SCAN, heading init, loop
  closure) were comparing noise once the estimator was off the rails.
- **Decision:** investigate -> fix: `docker/lio_sam/degeneracy_threshold.patch` exposes the
  threshold as `lio_sam/degeneracyThreshold` (default 100, upstream-identical) and logs the
  six eigenvalues per scan; next run sets it from measured values.

### 20260915T230642Z_lio_sam_exp14 (fix: degeneracy projection disabled, eigenvalues logged)
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T230256Z_lio_sam_exp14`
- **Hypothesis:** The isolated root cause is `LMOptimization()`'s hardcoded eigenvalue
  threshold of 100 zeroing the tilt/z update directions on this close-range scene. With the
  patched image (`docker/lio_sam/degeneracy_threshold.patch`: new param
  `lio_sam/degeneracyThreshold`, default 100 = upstream; six eigenvalues logged per scan),
  set the threshold to 0. Prediction: static-phase drift gone, rotation RMSE from ~130 deg
  to single digits, and the log shows the true well-conditioned eigenvalue range.
- **Change:** `degeneracyThreshold: 100 (hardcoded upstream) -> 0.0`; nothing else.
- **Config hash:** `5f42560bfc143a8d363389b52c396b6cd3b61f4de025071caff80cbc675c4b8d`
- **Result:** status ok, coverage 98.0% (675/689). ATE trans RMSE **1.070 m** (parent
  107.34, RPY-weight-0 run 29.31), median 0.962 m, p95 1.746 m; ATE rot RMSE **18.80 deg**
  (parent 147.09, RPY-weight-0 run 129.14). RPE 1 s trans 0.162 m / rot 4.46 deg (605
  pairs); RPE 10 s trans 0.297 m / rot 6.04 deg (352 pairs). Degenerate flag 0/365 scans,
  0 "Large velocity" resets (parent 46), "Not enough features" x2. Static phase: tilt
  within +-0.4 deg and z within 2 cm over the 6 s the rig is still (was 34 deg / -1.1 m).
  Eigenvalues (356 scans, descending index): e0 median 4358, e5 (smallest) min 1.5 / p1
  6.1 / p10 12.6 / median 42.2 / max 261; during the static phase e5 = 30-48; 260 of 356
  scans have e5 < 100, 121 < 30, 15 < 10, 1 < 3.
- **Interpretation:** Root cause confirmed and fixed. Every earlier LIO-SAM run (baseline,
  8 sweep trials, both held-out, 5 diagnostics) shared this: the upstream cutoff, an
  outdoor-Velodyne scale, classified tilt/z as degenerate on ~1 m-range indoor data, zeroed
  those LM updates, and the pose rode the IMU-preintegration guess on those axes until the
  corrupted keyframes poisoned the map. Rotation fell an order of magnitude on every
  horizon. The remaining gap to FAST-LIO2 on this sequence (0.04 m / 0.8 deg) is now
  ordinary integration/tuning work, not a bug hunt; the preintegration guess's z step is
  still visibly biased during motion, consistent with `imuGravity` 9.805 vs the measured
  at-rest 9.663 m/s^2, which is the next single-parameter test. The eigenvalue log gives a
  measured basis for a non-zero config value (below the static-phase floor of ~30) rather
  than leaving the safety net off.
- **Decision:** keep (the patch/param; the config value is set from these measurements in
  the next run, not left at 0).

### 20260915T231202Z_lio_sam_exp14 (degeneracyThreshold 10, measured value test)
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T230642Z_lio_sam_exp14` (threshold 0)
- **Hypothesis:** A non-zero, measured threshold (10: 3x below the static-phase floor of ~30,
  fires on the ~4% worst-conditioned scans) keeps upstream's safety net without re-triggering
  the failure. Prediction: within noise of the threshold-0 run.
- **Change:** `degeneracyThreshold: 0.0 -> 10.0`; nothing else.
- **Config hash:** `38925c386948acdb79fc4d2c33639dde74948d0acb18571685ad5d2bbedcaf36`
- **Result:** status ok, coverage 98.1% (676/689). ATE trans RMSE 0.698 m (parent 1.070),
  median 0.670 m, p95 1.083 m; ATE rot RMSE 20.02 deg (parent 18.80). RPE 1 s trans 0.177 m /
  rot 4.41 deg (593 pairs); RPE 10 s trans **0.737 m / rot 14.63 deg** (parent 0.297 m /
  6.04 deg, 474 pairs). Degenerate flag on 27/366 scans (7%), 0 resets, static phase held.
- **Interpretation:** Mixed, not better: ATE trans improved, ATE rot flat, RPE 10 s clearly
  worse. Whenever the projection fires on this data the pose rides the IMU guess on the
  zeroed axes, and nothing observed so far shows it helping; a single run cannot separate
  the ATE gain from run-to-run variance (an identical config earlier gave 0 vs 46 resets).
- **Decision:** revert to `degeneracyThreshold: 0.0` (projection off, so `imuPreintegration`
  never sees the "degenerate" covariance flag either). 0 vs 10 is a phase-1 item to settle
  with repeated runs, not a root-cause question.

### 20260915T231502Z_lio_sam_exp14 (imuGravity measured)
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T230642Z_lio_sam_exp14` (threshold 0)
- **Hypothesis:** The preintegration guess's z step is still biased during motion, and in the
  pre-fix runs it sank on the static rig at a constant ~0.125 m/s^2, matching `imuGravity`
  9.80511 vs the measured at-rest norm 9.663 m/s^2 (`docs/dataset.md`, all three sequences
  9.660-9.668). LIO-SAM fixes gravity magnitude in GTSAM and its accel-bias random walk is far
  too tight to absorb 0.14 m/s^2 (FAST-LIO2 estimates gravity as a state, so it never saw
  this). Prediction: ATE trans and RPE 10 s improve, rotation unchanged.
- **Change:** `imuGravity: 9.80511 -> 9.663`; nothing else.
- **Config hash:** `a75f610db544c51c9c7e1a12d264c6efdeb5b04d3c1b0cf0b23b85dd69d17c7e`
- **Result:** status ok, coverage 97.8% (674/689). ATE trans RMSE **0.647 m** (parent 1.070),
  median 0.584 m, p95 0.902 m; ATE rot RMSE 20.95 deg (parent 18.80). RPE 1 s trans 0.178 m /
  rot 5.14 deg (599 pairs); RPE 10 s trans 0.794 m / rot 17.41 deg (parent 0.297 / 6.04;
  483 pairs). 0 resets, 0 degenerate scans. Mechanism check (`lio_sam_diag.py`): the guess's
  per-scan z step over the 6 s static phase is now 0.000-0.004 m (was -0.008..-0.037 m,
  growing linearly).
- **Interpretation:** Mechanism confirmed and removed at the source. The headline pattern
  (ATE trans better, RPE 10 s worse than the parent) is the same one the threshold-10 run
  showed, which prompted the repeat below: the parent's RPE 10 s of 6.0 deg turns out to be
  the outlier of the fixed config's own spread, so this run is inside noise on every metric
  and 40% better on ATE trans. Kept as a measured sensor constant, not a tuning choice.
- **Decision:** keep (`configs/lio_sam/hilti22.yaml` now `imuGravity: 9.663`).

### 20260915T231728Z_lio_sam_exp14 (repeat of the threshold-0 config, variance check)
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T230642Z_lio_sam_exp14` (identical config)
- **Hypothesis:** Both single-change follow-ups improved ATE trans to ~0.65-0.70 m but showed
  RPE 10 s rot of 15-17 deg vs the parent's 6.0 deg. If an identical repeat also lands near
  15 deg, the parent's 6.0 was luck; if it reproduces 6 deg, the follow-ups genuinely cost
  long-horizon rotation.
- **Change:** none (config hash identical to the parent).
- **Config hash:** `5f42560bfc143a8d363389b52c396b6cd3b61f4de025071caff80cbc675c4b8d`
- **Result:** status ok, coverage 96.8% (667/689). ATE trans RMSE 0.744 m, median 0.739 m,
  p95 1.014 m; ATE rot RMSE 22.01 deg. RPE 1 s trans 0.186 m / rot 5.37 deg (558 pairs);
  RPE 10 s trans 0.961 m / rot **27.08 deg** (158 pairs). 0 resets.
- **Interpretation:** The fixed config's run-to-run spread on exp14 is ATE trans 0.74-1.07 m,
  rot 18.8-22.0 deg, RPE 10 s rot 6-27 deg. The parent's 6.0 deg was the outlier; the
  threshold-10 and gravity follow-ups were inside noise, not regressions. Any phase-1
  judgement on a change smaller than this spread needs >=3 repeats. Playback at rate 1.0 on
  a 2c/4t machine is the suspected variance source (LIO-SAM drops scans it cannot process
  in time; queue size 1 on the mapping node), so rate-0.5 repeats are the first phase-1 item.
- **Decision:** investigate (informational; nothing changed).

### 20260915T235638Z_lio_sam_exp14 (Horizon_SCAN 2000, measured azimuth grid)
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T231502Z_lio_sam_exp14` (fixed config: degeneracy off, measured gravity)
- **Hypothesis:** `Horizon_SCAN: 1800` is a ~0.2 deg datasheet guess. The bag's measured
  azimuth step is 0.18 deg, i.e. a 2000-column grid. Replicating
  `imageProjection::projectPointCloud()`'s range-image packing over 60 real scans: at 1800,
  9.7% of in-range points collide into already-occupied cells and are discarded; at 2000,
  2.0%. So 2000 should hand scan-to-map ~8% more surviving returns. Prediction: at least as
  good as the parent, within the run-to-run spread. (Checked while verifying this integration
  against upstream's README data-preparation requirements.)
- **Change:** `Horizon_SCAN: 1800 -> 2000`; nothing else.
- **Config hash:** `76f29c8cda2688668e4cbb0080d17d4f4c4a76fbad288620748fb534d5c31bf2`
- **Result:** status ok, coverage **95.1%** (655/689; every other post-fix run 96.8-98.1%).
  ATE trans RMSE 0.841 m (spread 0.65-1.07, inside), median 0.721 m, p95 1.379 m; ATE rot RMSE
  **25.39 deg** (spread 19-22 over four runs, outside). RPE 1 s trans 0.266 m / rot **7.77 deg**
  (spread 4.4-5.4, clearly outside); RPE 10 s trans 1.322 m / rot 26.61 deg. 0 resets, 0
  degenerate scans, 357 scans processed (others 365-366), corner features median 457 (was 447).
- **Interpretation:** Mechanism confirmed (more features survive, estimator health unchanged)
  but the run scored at or outside the worse edge of the spread on rotation and coverage, so
  the change is not shown better. Reverted, with the tension stated plainly: 1800 is a
  known-wrong value for this sensor, kept only because one run at the correct value scored
  worse, and one run cannot rank a change this size against a spread of 19-22 deg ATE rot and
  6-27 deg RPE 10 s rot. Needs >=3 repeats per value, ideally at playback rate 0.5.
- **Decision:** revert (config stays 1800, comment records that this is unsettled, not right).

### 9-axis IMU experiment (2x2, exp14) — `20260916T0006*`, two cells GT-fed and NOT reportable
- **Method / sequence / split:** lio_sam / exp14 / tune
- **Parent:** `20260915T231502Z_lio_sam_exp14` (frozen post-fix config)
- **Why:** upstream's README requires a 9-axis IMU. This sensor is 6-axis with an all-zero
  quaternion, so a Madgwick filter substitutes (`adapters/lio_sam/orientation_filter.py`,
  measured tilt error 0.70 deg at init / 1.60 deg mean vs GT). Question: what does that
  substitute actually cost, and would a real 9-axis IMU buy anything? Hilti's own GT
  orientation, interpolated to 400 Hz, stands in for a perfect 9-axis sensor.
- **Protocol status:** the two GT-fed cells **violate `docs/protocol.md` §3** ("Ground truth is
  never fed into a method: not into initialisation, orientation, deskewing or the estimator")
  and can never be reported, exactly like the loop-closure diagnostic above. The node lives in
  the session scratchpad, never in `adapters/`, and logs a `ROS_WARN` on every run. The
  Madgwick x 0.01 cell is fully compliant and is the control.
- **Change:** orientation source {Madgwick, GT-interpolated} x `imuRPYWeight` {0.0, 0.01};
  everything else at the frozen config. GT node mounted over `imu_orientation_node.py`.

  | orientation | imuRPYWeight | ATE trans (m) | ATE rot (deg) | RPE 1s rot | RPE 10s rot | cov |
  |---|---|---|---|---|---|---|
  | Madgwick (frozen, 4 runs) | 0.0 | 0.65-1.07 | 18.8-22.0 | 4.4-5.4 | 6.0-27.1 | 96.8-98.1% |
  | GT *(not reportable)* | 0.0 | 0.832 | 18.49 | 5.88 | 20.35 | 95.8% |
  | Madgwick (compliant control) | 0.01 | 0.690 | 20.87 | 5.05 | 17.61 | 98.7% |
  | **GT** *(not reportable)* | **0.01** | **0.498** | **17.07** | **4.42** | **11.73** | 98.4% |

  All four: 0 preintegration resets, 0 degenerate scans.
- **Interpretation:** three findings.
  1. **At `imuRPYWeight: 0.0` the orientation source does not matter.** A perfect 9-axis IMU
     lands inside the Madgwick spread on every metric, because at weight 0 the quaternion only
     seeds the initial attitude and the fallback guess. The README's 9-axis requirement is
     effectively moot for the currently frozen config.
  2. **It stops being moot once the constraint is on.** GT x 0.01 is the best result of this
     entire integration (ATE trans 0.498 m, below the whole observed spread) and beats GT x 0
     by 0.83 -> 0.50 m and 20.35 -> 11.73 deg RPE 10s rot. Against the compliant control, the
     cost of our synthesized orientation is about 0.19 m ATE trans, 3.8 deg ATE rot and
     5.9 deg RPE 10s rot. That is the price of the 9-axis deviation, and it is real but modest.
  3. **The `imuRPYWeight: 0.0` decision needs revisiting.** It was set because 0.01 was
     catastrophic (`20260915T222509Z`: ATE trans 349 -> 29 m), but that predates the
     degeneracy fix and the damage was entangled with the actual bug. Post-fix, 0.01 with our
     own orientation is neutral (inside the spread), not harmful. The frozen config stays at
     0.0 for now on the not-shown-better rule, but this is an open phase-1 item.
- **Decision:** investigate (all three). Config unchanged. The GT cells bound what a 9-axis
  IMU would be worth; they are not this method's performance and must never be quoted as such.

### Cross-dataset validation on LIO-SAM's own `walking_dataset` (not a protocol run)
- **Method / sequence / split:** lio_sam / LIO-SAM `walking_dataset.bag` / **not in this
  benchmark's manifest** — no `runs/` record, no `lio-bench eval`, no ATE/RPE, because the
  author's demo bags ship no ground truth. Artifacts in the session scratchpad.
- **Why:** upstream's README requires a 9-axis IMU, which Hilti's rig lacks. This bag is the
  author's own: Velodyne VLP-16 in native format and a Microstrain 3DM-GX5-25 publishing a
  real unit-norm orientation quaternion (verified: norm 1.0000, `orientation_covariance[0]`
  0.01), played against upstream's own `config/params.yaml` verbatim. Three questions: does
  our patched image reproduce upstream behaviour on reference data; does the genuine 9-axis
  path work; and **is the degeneracy threshold of 100 actually well-calibrated where LIO-SAM
  was developed**, which would confirm the root cause is range-dependence rather than a fault
  in this repo's integration.
- **Setup:** no adapters at all (native cloud, real 9-axis IMU), upstream params verbatim,
  `degeneracyThreshold` left unset so the patch falls back to its default of 100, i.e. exactly
  upstream's hardcoded behaviour. 655 s bag, playback rate 1.0.
- **Result:** clean run, 3222 poses over 655 s. **Zero** warnings of any kind: no "Large
  velocity", no "Not enough features", no "Invalid quaternion", no "Large bias". Trajectory is
  physically sensible: 808 m path length over a 149 x 245 m area, z range 4.7 m, speed mean
  1.23 m/s and p95 1.55 m/s, i.e. human walking pace.

  LM eigenvalues, smallest of the six, against upstream's threshold of 100:

  | dataset | median smallest | p10 | scans below 100 | margin |
  |---|---|---|---|---|
  | `walking_dataset` (VLP-16, outdoor) | 564.6 | 256.3 | 78/3174 (2.5%) | 5.6x above |
  | Hilti exp14 (PandarXT-32, basement) | 42.2 | 12.6 | 260/356 (73.0%) | 0.42x, i.e. below |

- **Interpretation:** independent confirmation of this session's root cause, from the author's
  own data. The hardcoded threshold of 100 is well-calibrated for what LIO-SAM was developed
  on, sitting 5.6x below the typical smallest eigenvalue there and tripping on 2.5% of scans.
  On Hilti's close-range indoor scene the same quantity is 13x smaller and trips on 73% of
  scans. Rotation-block eigenvalues scale with range squared, and this scene's median range is
  ~1 m, so nothing about our integration is wrong: upstream simply encodes a range assumption
  as a constant. It also validates the build end to end on reference data, confirms the patch
  is behaviour-preserving when the param is unset, and exercises the genuine 9-axis path that
  Hilti cannot.
- **Second run, with map capture and a rotation reference:** repeated identically (3208 poses
  vs 3222, path 808.1 m vs 808.0 m, start-to-end 104.5 m both times; pose-to-pose difference
  between the two runs median 0.27 m, max 1.35 m over an 808 m walk). Eigenvalues reproduce:
  median smallest 568.7, 2.5% below 100. The saved map (64 MB) is sharp — straight paths,
  crisp building edges, individual tree canopies, no ghosting or doubled walls.
  - **Rotation checked against an independent reference.** This bag has no ground truth, and
    its 2623 GPS messages all carry an invalid fix status, while `/gx5/nav/odom` is a constant
    identity placeholder — so position cannot be scored at all. But `/imu_correct` carries the
    Microstrain's real 9-axis AHRS attitude, which is independent of LIO-SAM. Comparing
    body-frame rotation over 1 s windows (invariant to both the differing world frames and the
    unknown IMU-to-lidar extrinsic, since a similarity transform preserves rotation angle):
    **correlation 0.9866, slope 0.971**, absolute difference mean 1.91 deg, median 1.22 deg,
    p95 6.11 deg. LIO-SAM's rotation tracks a real 9-axis AHRS to about a degree here — the
    behaviour the Hilti runs could not produce before the degeneracy fix.
  - **Run-to-run variance is tiny here**, unlike Hilti (same config, ATE trans 0.65-1.07 m and
    0 vs 46 resets). Supports the standing hypothesis that Hilti's variance is this machine
    dropping scans at rate 1.0: the PandarXT-32 delivers ~61k points over 32 rings per scan
    against the VLP-16's ~30k over 16, so the demo bag is roughly half the per-scan load.
- **Decision:** n/a (validation, not a tuning run). Nothing in `configs/` changed.

### LIO-SAM integration summary
Every early run in this integration (exp14 baseline, all 8 sweep trials, both held-out
evaluations, four single-parameter diagnostics) shared one catastrophic rotation failure (ATE
rot RMSE 100-170 deg regardless of config). It is now root-caused and fixed, in three steps:

1. `imuRPYWeight: 0.01 -> 0.0` (`20260915T222509Z`): the Madgwick roll/pitch slerp was costing
   >10x in translation (349 -> 29 m) and every preintegration reset; rotation unchanged.
2. **The root cause** (`20260915T230256Z` diagnosis, `20260915T230642Z` fix):
   `mapOptmization::LMOptimization()` zeroes any scan-to-map update direction whose J^T J
   eigenvalue is below a hardcoded 100, an outdoor-Velodyne scale. On this ~1 m-range scene
   that flagged 91% of scans, discarded the tilt/z updates, and let the pose ride the IMU
   guess -- visible as an identical, deterministic tilt to -30 deg and 1.1 m sink during the
   6 s the rig is provably static at the start of exp14. `docker/lio_sam/degeneracy_threshold.patch`
   exposes the cutoff as `degeneracyThreshold` (default 100 = upstream); the frozen config
   sets 0 (off). exp14: 29.3 m / 129 deg -> 1.07 m / 18.8 deg, RPE 1 s rot 26.6 -> 4.5 deg.
   A measured 10 (`20260915T231202Z`) was not better; reverted. Confirmed independently on
   LIO-SAM's own `walking_dataset`, where the same quantity is 13x larger (median smallest
   eigenvalue 564.6 vs Hilti's 42.2) and upstream's 100 trips on only 2.5% of scans vs 73%.
3. `imuGravity: 9.80511 -> 9.663` (`20260915T231502Z`): the measured at-rest norm; the
   preintegration guess no longer sinks on a static rig. Kept on mechanism evidence.

A repeat (`20260915T231728Z`) measured the fixed config's run-to-run spread on exp14: ATE
trans 0.74-1.07 m, rot 19-22 deg, RPE 10 s rot 6-27 deg. What remains is ordinary work, not
a bug hunt: the phase-1 manual tuning this method skipped (repeats, ideally at rate 0.5;
`degeneracyThreshold` 0 vs 10; `Horizon_SCAN` 1800 vs the measured-correct 2000 -- one run
each so far, both reverted as not-shown-better and both genuinely unsettled against this
spread), plus `imuRPYWeight` 0.0 vs 0.01, which the 9-axis experiment showed is no longer
harmful post-fix and is worth real accuracy if the orientation is good), then a bounded
phase-2 sweep and a fresh held-out evaluation. The old sweep and held-out
results describe the bug and must not be used for comparison. Tooling added:
`LIO_SAM_RECORD` in `scripts/run_lio_sam.sh` and `scripts/lio_sam_diag.py`.

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
