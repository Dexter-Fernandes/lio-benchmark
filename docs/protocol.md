# Benchmark protocol

This document is normative: reported numbers follow it, and changing it after results exist
means versioning the affected configuration (`configs/eval/default_v2.yaml`) and re-running.
Implementation: `src/lio_benchmark/evaluation.py`; parameters: `configs/eval/default.yaml`.

## 1. What is compared

**Primary comparison: online odometry.** Loop closure, GPS, prior maps and offline refinement
are disabled. Each method keeps its own local estimation and mapping machinery (local maps,
sliding windows, keyframes). The poses evaluated are those the method emitted online, as
it emitted them. Retrospectively optimised poses are never substituted.

Full SLAM or global refinement (for example GLIM's global mapping) may be reported as a
separate **secondary** comparison, never mixed with the primary one.

For each method we compare two configurations:

- **Adapted baseline:** upstream defaults with only dataset adaptation, meaning topics, units,
  point fields, extrinsics and supplied IMU calibration. These must already be correct in the
  baseline, so tuning never hides an integration error.
- **Tuned:** manually guided changes on exp14 (see §6), frozen before held-out evaluation.

## 2. Data split

| Role | Sequence | Use |
|---|---|---|
| tune | exp14 | development, integration checks, manual tuning |
| heldout | exp16, exp18 | evaluated once per frozen configuration |

Configurations are frozen (hash recorded) before any held-out run. Held-out results are
never used to choose parameters. This is a held-out split within one dataset and one sensor
rig. It is not evidence of generalisation to other sensors or environments.

## 3. Frames and inputs

- Ground truth is T_W_I, the **IMU frame** in a z-up world. Quaternions are (x, y, z, w). This
  was confirmed by a gravity check: the at-rest specific force rotated by the ground-truth
  orientation lies 0.65° from +z_W with (x, y, z, w) and 91° with (w, x, y, z)
  (`lio-bench inspect`).
- Estimates are converted to the IMU frame before evaluation: T_W'_I = T_W'_S · (T_I_S)⁻¹,
  where T_I_L comes from `lidar_calibration.yaml`. Each method adapter declares its output
  body frame (`lio-bench eval --frame imu|lidar`).
- Ground truth is never fed into a method: not into initialisation, orientation, deskewing
  or the estimator.
- ROS 1 methods read the original bags. ROS 2 methods read MCAP conversions that passed the
  equivalence check (`lio-bench data convert`: per-topic counts, stamps and a content SHA-256).

## 4. Metrics

All metrics are computed at **dense ground-truth timestamps**.

**Association.** The estimate is interpolated at a ground-truth time (linear in position,
SLERP in rotation) only between two consecutive estimate poses at most `max_gap_s` = 0.25 s
apart. That is one dropped scan at 10 Hz, never two. A ground-truth time that coincides with
an estimate pose (within 1 µs) is also associated. There is no extrapolation. Ground truth is
never interpolated. Its own gaps (up to 0.61 s in exp14 and 1.3 s in exp18) simply contribute
no samples.

**Alignment.** One SE(3) transform per run (Umeyama, **no scale**), fitted on all associated
positions. Its only purpose is to remove the arbitrary world frame of the estimator. A
trajectory whose associated positions are collinear cannot be aligned and is `failed`.

| Measure | Definition | Reported |
|---|---|---|
| ATE translation | ‖p_gt − (R p_est + t)‖ per sample | RMSE, mean, median, p95, max (m) |
| ATE rotation | angle(R_gtᵀ · R_align · R_est) | same statistics (deg) |
| RPE | for Δ ∈ {1 s, 10 s}: E = (G_i⁻¹G_j)⁻¹(P_i⁻¹P_j), with j the associated sample nearest t_i + Δ (±0.05 s) and **no estimate gap between i and j** | translation (m) and rotation (deg): RMSE, mean, median, p95, max, pair count |
| Control points (secondary) | aligned estimate vs surveyed sparse positions, using the dense alignment | per-point error, RMSE (m) |
| Coverage | associated ÷ dense ground-truth samples | fraction, init delay, end shortfall, gap count and maximum |
| Status | `failed` (< 10 associated samples, no overlap, degenerate alignment), `incomplete` (coverage < 0.95), `ok` | |

Rules:

- Coverage is always reported next to accuracy, so a partial trajectory cannot appear to
  win. `incomplete` and `failed` runs appear in every table with their status.
- Metrics with different definitions (for example RPE per metre versus per second, or aligned
  versus unaligned) are never averaged together.
- Rotation ATE is always reported. A frame mistake (LiDAR poses declared as IMU) changes
  translation ATE by only about 9 mm on exp14, because the lever arm is 5.6 cm, but it gives
  about 180° of rotation error.

Why two ground-truth types: the dense 6-DoF files and the sparse 3-DoF files have
**different provenance**. The sparse points are millimetre-accurate surveyed control points.
The dense trajectories (only for exp14, exp16 and exp18) come from a separate
reconstruction, and their accuracy is not documented at the same level. The primary metrics
use the dense trajectories because rotation and drift need them. The sparse errors are a
secondary, independent check. See [dataset.md](dataset.md).

## 5. Replay and compute

- **Accuracy runs** use playback slow enough that nothing is dropped, with original sensor
  timestamps preserved. Record the playback rate and verify complete processing (input
  message counts against processed counts, no queue overflow). Slow replay is not evidence of
  real-time capability.
- **Real-time runs** are separate: 1× replay, reporting backlog, dropped measurements and
  pose latency. Latency is measured between compatible clocks (the wall-clock time a message
  was published by the player versus the wall-clock time its pose was emitted). It is never
  measured as bag timestamps subtracted from the current wall time. In these bags, log time
  equals header stamp, so the recording itself carries no receive-time information.
- **Compute**: median and p95 per-scan processing time, total wall runtime, peak RSS. Each
  method notes what its timing includes (preprocessing, queues, registration, mapping).
- **Hardware**: one headless experiment at a time on a 2-core / 4-thread i7-7500U with
  11.5 GiB RAM. Thread limits are recorded per run (`env.json`). GLIM runs CPU-only.
- **Fresh state**: every run starts a new container with no persisted maps or caches.

## 6. Manually guided tuning

Tuning is manual and hypothesis-driven, not an automated sweep. Each attempt is a run record
(`lio-bench run init … / eval --run-dir … / run close …`) containing:

- the hypothesis and parent run;
- the exact change;
- the full resolved configuration and its hash;
- the environment (commit, dirty flag, image, threads, package versions);
- dataset hashes, playback rate, metrics, trajectory, plots and logs;
- the interpretation and a keep/revert/investigate decision.

Rules:

- Establish the adapted baseline first.
- Change one parameter family at a time.
- Repeat shortlisted configurations enough to see run-to-run variability, since
  multi-threaded methods are not deterministic.
- Record every attempt, including failures, and report the tuning effort per method. Equal
  effort across methods is not claimed.

## 7. Reporting

Tables report, per method, configuration (baseline or tuned) and sequence:
- status and coverage;
- ATE (RMSE, median, p95; translation and rotation);
- RPE at 1 s and 10 s;
- control-point errors;
- compute.

Rankings are only stated where runs exist. Limitations are stated next to the results.
