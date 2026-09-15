# Methods

FAST-LIO2 is fully integrated (`docker/fast_lio2/`, `adapters/fast_lio2/`), merged to `main`.
LIO-SAM integration is in progress (`docker/lio_sam/`, `adapters/lio_sam/`). This page records
scope decisions, the variants we mean, and
the integration questions each method raises for this dataset. The measured input facts are
in [dataset.md](dataset.md). Any claim about upstream behaviour below that is marked
**verify** has not yet been checked against the pinned source.

## Scope

| Method | Role | Planned environment | Status |
|---|---|---|---|
| FAST-LIO2 | core tightly coupled LIO, **first integration** | Ubuntu 20.04 / ROS Noetic | done, merged to `main` |
| FAST-LIO (original) | separate implementation, pinned to its own revision | its supported environment | not started |
| LIO-SAM | core LIO, GPS and loop closure disabled | Ubuntu 20.04 / Noetic, pinned GTSAM | integrating, see below |
| GLIM | CPU LiDAR-inertial odometry; global mapping only as secondary | Ubuntu 22.04 / ROS 2 Humble, no CUDA | not started |
| DLIO | recommended addition (not yet confirmed by the project owner) | Ubuntu 20.04 / Noetic | not started |
| RTAB-Map ICP + IMU | IMU-assisted ICP baseline | Ubuntu 22.04 / Humble | not started |
| LOAM | conditional on the chosen implementation | depends on implementation | undecided |

Environments are design targets, not validated builds. Each method gets its own
`docker/<method>/` and `.devcontainer/<method>/` when it is integrated. Every image pins its
source revision and base-image digest.

## Distinctions that must stay explicit

- **FAST-LIO vs FAST-LIO2.** FAST-LIO2 (direct point registration with an ikd-tree map) is
  not original FAST-LIO (feature-based, 2021 RA-L). The `hku-mars/FAST_LIO` repository now
  hosts FAST-LIO2. Running it with feature extraction enabled does **not** reproduce
  original FAST-LIO, because map management and other parts changed. "FAST-LIO" in results
  means a separately pinned original implementation, or it is left out with the reason
  stated.
- **LOAM** is ambiguous. Original-style implementations can use IMU assistance; many
  derivatives (for example `laboshinl/loam_velodyne`) are LiDAR-only or use the IMU only
  loosely. Results name the exact repository and revision and say how the IMU is actually
  used. A LiDAR-only LOAM is labelled a LiDAR-only baseline, not LIO.
- **RTAB-Map** is a framework with several odometry back ends. Our baseline is its own
  **ICP odometry with IMU**, described by how the IMU is actually used (**verify** in
  source: guess and deskew versus in the estimator). It is not called tightly coupled LIO
  without evidence. RTAB-Map's LIO-SAM wrapper is not an independent estimator and is not
  used.
- **LIO-SAM** upstream expects a 9-axis IMU with orientation estimates. See below.

## Dataset-specific integration questions

These come from `lio-bench inspect` and hold identically on exp14, exp16 and exp18.

1. **IMU orientation is absent but not flagged.** Every `/alphasense/imu` message has an
   all-zero orientation quaternion with `orientation_covariance[0] = 0`, not the ROS
   "unknown" flag of −1. The BMI085 is a 6-axis IMU. Any method that reads
   `msg.orientation` gets an invalid quaternion without warning.
   - **LIO-SAM (resolved):** a documented, sensor-only Madgwick filter adapter
     (`adapters/lio_sam/orientation_filter.py`, `imu_orientation_node.py`), never ground
     truth. This is necessary, not precautionary: `TixiaoShan/LIO-SAM`'s own
     `include/utility.h::imuConverter()` checks the rotated quaternion's norm and calls
     `ros::shutdown()` with `"Invalid quaternion, please use a 9-axis IMU!"` if it's near
     zero, which an all-zero passthrough triggers immediately (confirmed against source, not
     assumed) -- so this is genuine upstream LIO-SAM with a sensor-only adapter, not a
     relabeled derivative. See "LIO-SAM integration" below for the filter, `beta`, and a
     real bug the adapter's own unit test caught (a gradient-descent singularity from seeding
     the filter at a fixed identity quaternion instead of the first accel reading).
   - All other methods: confirm they ignore `orientation` (**verify** per method).
2. **Per-point time is absolute.** The PointCloud2 `timestamp` field is float64 **absolute
   epoch seconds**. The first point equals the header stamp (median +1 µs) and scans span
   0.100 s. Methods that expect a relative offset (for example FAST-LIO2's Velodyne handler,
   which reads a `time` field) need an input adapter that subtracts the header stamp and
   renames or retypes the field. Such adapters live in `adapters/`, carry unit tests against
   known scans, and are applied identically in baseline and tuned runs.
3. **Ring** is uint16 `ring` in 0–31 (32 channels).
4. **Very short ranges.** The median range is 0.8–1.1 m and 1% of points are within
   0.17–0.20 m (the operator and rig in narrow indoor spaces). Minimum-range and blind-zone
   parameters are dataset adaptation, not tuning, and are set in the baseline from these
   measurements.
5. **Extrinsics.** T_I_L rotates z_L to −z_I (the LiDAR is mounted upside down relative to
   the IMU), with a 5.6 cm lever arm. Each method's extrinsic convention (T_I_L versus T_L_I,
   rotation matrix order) is checked with a known-answer test before the first run.
   - **LIO-SAM (resolved):** needs `T_L_I` (`T_I_L` inverted), not `T_I_L` directly, despite
     `config/params.yaml`'s own comment calling it `"T_lb (lidar -> imu)"`. Confirmed by
     reading `imuConverter()`'s actual usage (`acc = extrinsicRot * acc_imu`, rotating an
     IMU-frame vector into the lidar/`base_link`-aligned frame LIO-SAM assumes throughout),
     not the misleading comment. See `configs/lio_sam/hilti22.yaml` and
     `tests/test_frames.py::test_lio_sam_extrinsic_is_T_L_I_not_T_I_L`.
6. **Output frame.** Each adapter records whether the method publishes IMU or LiDAR body
   poses, so that `lio-bench eval --frame` converts them correctly.
   - **LIO-SAM (resolved):** LiDAR-frame, the opposite of FAST-LIO2. `mapOptmization.cpp`
     keeps `lidarFrame == baselinkFrame == "base_link"` and publishes its optimized pose
     directly on `lio_sam/mapping/odometry` with no further frame conversion -- use
     `--frame lidar`.
7. **ROS 2 input.** The rosbag2 conversions currently use metadata version 9. ROS 2 Humble
   (GLIM, RTAB-Map) may need `lio-bench data convert --dst-version N` with an older version
   (**verify** when the Humble images are built).

## FAST-LIO2 integration

`docker/fast_lio2/Dockerfile` builds `hku-mars/FAST_LIO` pinned at `7cc4175` (2024-07-23) with
its `livox_ros_driver` build dependency, on `ros:noetic-ros-base` pinned by digest.

- **Point-time adapter.** `adapters/fast_lio2/ros_node.py` republishes `/hesai/pandar` as
  `/hesai/pandar/fast_lio2` in FAST-LIO2's velodyne layout (x, y, z, intensity, ring, time),
  with `time` the per-point `timestamp` minus the scan's header stamp, in seconds. The pure
  conversion (`adapters/fast_lio2/pointcloud_adapter.py`) is unit-tested in
  `tests/test_adapters.py` against synthetic scans built from the measured facts above (point
  2). `configs/fast_lio2/hilti22.yaml` sets `preprocess.timestamp_unit: 0` (seconds) to match.
- **Blind zone (point 4).** Set to 0.1 m, below the measured p01 range (0.17-0.20 m across
  exp14/16/18), so real short-range returns from the handheld rig are not dropped.
- **IMU noise covariance (tuned on exp14, `docs/journal.md` run
  `20260915T133833Z_fast_lio2_exp14`, kept).** `mapping.acc_cov`/`gyr_cov` were the generic
  Velodyne-config defaults (0.1/0.1); `lio-bench imu-noise` measures per-axis white-noise
  variance from `calibration/imu_noise_calibration.bag` (`inspection.py::imu_noise`, a simple
  std, not a full Allan-variance fit), now baked into `configs/fast_lio2/hilti22.yaml` as
  3.677e-04/1.183e-05. Every metric improved, rotational ATE RMSE most (4.86 -> 1.34 deg).
  `b_acc_cov`/`b_gyr_cov` (bias random-walk) are still untuned defaults.
- **Registration voxel size (tuned on exp14, `docs/journal.md` run
  `20260915T152627Z_fast_lio2_exp14`, kept).** `filter_size_surf`/`filter_size_map` are
  `mapping_velodyne.launch` top-level params (not nested under `mapping:` in FAST-LIO2's own
  rosparam schema), now recorded in `configs/fast_lio2/hilti22.yaml`'s `launch:` section and
  applied by `scripts/run_fast_lio2.sh`. The generic 0.5 m default voxel-merges 15-140x more
  points than this sequence's measured point spacing (0.36-3.4 cm); shrinking to 0.2 m
  improved every metric (ATE trans RMSE 0.125 -> 0.041 m). A sibling 0.1 m candidate (run
  `20260915T152922Z_fast_lio2_exp14`) was strictly worse on every metric and reverted — 0.2 m
  is a measured sweet spot, not "finer is always better".
- **Bayesian sweep (phase 2, `docs/protocol.md` §6.2, `docs/journal.md` sweep `yf5zcpr1`).**
  15 trials over the region phase 1 established (noise covariance, voxel size, plus
  previously-untried `point_filter_num`/`max_iteration`), `scripts/fast_lio2_sweep.py`. No
  trial beat the manually-tuned baseline on both ATE trans and rot RMSE together — a negative
  result; the config is unchanged.
- **Held-out evaluation (`docs/journal.md`).** The frozen config (tune-split, exp14) was run
  on exp16 and exp18 unchanged. exp18: a normal, bounded generalization gap (ATE trans RMSE
  0.207 m, rot RMSE 2.26°, roughly 5x/2.7x worse than exp14 — no runaway RPE). exp16: a
  catastrophic, reproducible divergence (ATE trans RMSE 66.4 m, rot RMSE 62.9°) starting
  around t=170-180s of a 200s sequence and never recovering — status **open, not tuned
  around** per protocol §6 (held-out results don't feed back into the frozen config). Root
  cause not yet investigated.
- **Map artifacts.** `pcd_save.pcd_save_en: true` (was `false`) in `configs/fast_lio2/
  hilti22.yaml` — an output setting, not a tuning parameter. `scripts/run_fast_lio2.sh` sends
  `SIGINT` to `fastlio_mapping` before shutdown (FAST-LIO2 only saves its map there, never on
  plain `kill`/SIGTERM) and copies the resulting `map.pcd` into the run directory;
  `lio-bench eval --run-dir` renders it to `map.png` (`plots.plot_pcd_map`, Open3D headless
  EGL, top-down orthographic, colored by height). Also fixed while implementing this: dropped
  `rosbag play --clock`/`use_sim_time` entirely, since it made `fastlio_mapping`'s shutdown
  hang forever once bag playback ended (`ros::Rate::sleep()` blocks on `/clock`, which stops
  advancing) — FAST-LIO2 and the adapters only ever use message `header.stamp`, never
  `ros::Time::now()`, so this cost nothing and fixed a real bug. Default playback rate is now
  1.0 (real-time; was 0.5).
- **Extrinsics (point 5).** `extrinsic_T`/`extrinsic_R` in `configs/fast_lio2/hilti22.yaml`
  are `T_I_L` (confirmed **verify**: FAST-LIO2's README states extrinsic_T/R map LiDAR into
  IMU, i.e. `p_IMU = R * p_LiDAR + T`, the same convention as `T_I_L`), taken from
  `configs/dataset/hilti22.yaml` via `frames.extrinsic` and checked with
  `frames.check_lidar_extrinsics`.
- **Output frame (point 6, verify resolved).** FAST-LIO2's `/Odometry` is the estimated IMU
  pose directly (the ESKF state is IMU-centric), so evaluation uses `--frame imu`.
- **Orientation (point 1, verify resolved).** FAST-LIO2's velodyne/IMU handling never reads
  `sensor_msgs/Imu.orientation`, only angular velocity and linear acceleration, so the all-zero
  orientation quaternion is a non-issue for this method.
- **Run wrapper.** `scripts/run_fast_lio2.sh` (the image's entry point convention, no
  `ENTRYPOINT` so the devcontainer still gets a plain shell) starts `roscore`, the adapter, an
  `/Odometry` to TUM exporter (`adapters/fast_lio2/odom_to_tum.py`), and `fastlio_mapping`;
  waits for the mapping node to subscribe before playing the bag; times out the playback; and
  fails if no trajectory was written. Use the original ROS 1 bag, not the rosbag2/MCAP
  conversion (this method's environment is ROS 1 Noetic).

## LIO-SAM integration

`docker/lio_sam/Dockerfile` builds `TixiaoShan/LIO-SAM` pinned at `0be1fbe` (2023-04-17, latest
master at integration time), on `ros:noetic-ros-base` (same pinned digest as `fast_lio2`).

- **Noetic build validation.** LIO-SAM's bundled instructions target Kinetic; master has never
  merged a Noetic port (PRs `#393`/`#408`, both open/closed unmerged). The Dockerfile applies
  the fix upstream's own maintainer (TixiaoShan) summarized and endorsed in
  `github.com/TixiaoShan/LIO-SAM/issues/206`, not an improvised patch: (1) GTSAM 4.0.3 from
  the official `ppa:borglab/gtsam-release-4.0` (README's own instructions), not built from
  source -- building 4.0.2 from source was the original reported failure; (2)
  `include/utility.h`'s `#include <opencv/cv.h>` replaced with `#include <opencv2/opencv.hpp>`
  placed after the PCL headers, avoiding a FLANN/OpenCV `unordered_map::serialize` symbol
  clash (confirmed independently by two issue reporters); (3) `CMakeLists.txt`'s
  `-std=c++11` bumped to `-std=c++14`. No GPU/CUDA dependency (`package.xml` lists only
  roscpp/rospy/tf/cv_bridge/pcl_conversions/message_generation/GTSAM/OpenMP/PCL/OpenCV/Boost
  -- verified against the file, not assumed).
- **Orientation adapter (point 1, resolved).** `adapters/lio_sam/orientation_filter.py` is a
  standard 6-axis Madgwick filter (Madgwick 2010, gradient-descent variant, no magnetometer
  term), `beta = 0.1` (Madgwick's own paper-recommended value for a MEMS-class IMU),
  operating at the measured 399.2 Hz `/alphasense/imu` rate. It reads only this IMU's own
  `angular_velocity`/`linear_acceleration` and never ground truth.
  `adapters/lio_sam/imu_orientation_node.py` runs it statefully per message and republishes
  on `/alphasense/imu/oriented`, which `configs/lio_sam/hilti22.yaml`'s `imuTopic` points at.
  Without a magnetometer, yaw is unobservable and free-drifts from an arbitrary initial
  value -- this only ever supplies a gravity-referenced roll/pitch, which is what LIO-SAM's
  `extrinsicRPY` rotation and low-confidence `imuRPYWeight` (0.01) actually need it for, not
  a global heading reference.
  - **Bug caught by the adapter's own unit test.** Seeding the filter at a fixed identity
    quaternion is a gradient-descent singularity whenever the true attitude is near-antipodal
    to the filter's `[0,0,1]` reference -- which it is here: this IMU's "up" reaction force
    reads along `-z` (docs/dataset.md's "up -z" at-rest measurement), diametrically opposite
    the reference. From identity the correction gradient is exactly zero at that point, and
    small gyro/floating-point asymmetries then drove the filter to an unrelated, wrong
    attitude over a few thousand steps instead of converging -- caught by
    `test_madgwick_converges_to_measured_gravity_direction_at_rest`
    (`tests/test_adapters.py`), not by inspection. Fixed by seeding the initial quaternion
    from the first accelerometer reading (`orientation_filter.initial_quaternion`), the
    standard practical fix, used identically in `imu_orientation_node.py` and the test.
- **Point-cloud adapter.** LIO-SAM's `VelodynePointXYZIRT`
  (`src/imageProjection.cpp`) is byte-identical to FAST-LIO2's velodyne layout (x, y, z,
  intensity as f4, `ring` u2, `time` f4 seconds relative to the header stamp;
  `imageProjection.cpp` accepts a point-time field named `"time"` or `"t"` and adds it to the
  scan's header stamp to deskew each point -- confirmed against source). Because the layouts
  match, `adapters/lio_sam/pointcloud_adapter.py`'s `to_lio_sam_points` is functionally the
  same conversion as FAST-LIO2's, unit-tested the same way in `tests/test_adapters.py`
  against the shared synthetic-scan helper.
- **Extrinsics (point 5, resolved above).** `configs/lio_sam/hilti22.yaml`'s `extrinsicRot`/
  `extrinsicTrans`/`extrinsicRPY` are `T_L_I` (`T_I_L` from `configs/dataset/hilti22.yaml`,
  inverted), verified by `tests/test_frames.py::test_lio_sam_extrinsic_is_T_L_I_not_T_I_L`.
  `extrinsicRPY` is set equal to `extrinsicRot` since the synthesized orientation is computed
  directly in the same raw IMU frame as accel/gyro (no separate AHRS-frame offset to correct
  for, unlike a genuine 9-axis IMU with its own internal fusion frame).
- **GPS factor and loop closure (`docs/protocol.md` #1, hard requirement).**
  `loopClosureEnableFlag: false`. No GPS topic is ever published in this benchmark
  (online-odometry scope); `mapOptmization.cpp::addGPSFactor()` no-ops on an empty
  `gpsQueue`, confirmed from source, so no separate disable flag is needed for GPS.
- **Blind zone (point 4).** `lidarMinRange: 0.1` m, same reasoning as FAST-LIO2's `blind`.
- **Run wrapper.** `scripts/run_lio_sam.sh` launches four nodes (`lio_sam_imageProjection`,
  `lio_sam_featureExtraction`, `lio_sam_imuPreintegration`, `lio_sam_mapOptmization` --
  LIO-SAM has no single combined node like FAST-LIO2's `fastlio_mapping`), plus the
  orientation and point-cloud adapters and the TUM exporter. Readiness gates on
  `lio_sam_imageProjection` subscribing to the adapted point-cloud topic. No
  `--clock`/`use_sim_time`, same reasoning as `run_fast_lio2.sh` (every node here keys off
  `header.stamp`, never `ros::Time::now()`).
  - **Shutdown/save (verify resolved).** Unlike FAST-LIO2's single `SIGINT`-triggered save,
    `mapOptmization.cpp`'s `visualizeGlobalMapThread()` runs `while (ros::ok()) rate.sleep();`
    (`rate(0.2)`, i.e. a 5 s period) and only falls through to `saveMapService()` once that
    loop notices shutdown -- still `SIGINT`-driven, but with up to ~5 s of latency before the
    node even checks, then more time to downsample and write the full map. The wrapper polls
    up to 90 s (versus FAST-LIO2's 30 s) for the output file.
  - **Save path (verify resolved).** `saveMapService`'s default (empty `req.destination`)
    resolves to `$HOME` + `savePCDDirectory` (`config/params.yaml`'s value, `/pcd_out/` here),
    **not** the literal config value -- and the code deletes and recreates that directory on
    every save (confirmed from source: `rm -rf` then `mkdir -p`), so the wrapper treats it as
    ephemeral scratch, cleared at the start of every run. The map artifact is
    `GlobalMap.pcd`, copied out as `map.pcd` like FAST-LIO2's.
- **Config baseline vs. tuning (departure from the FAST-LIO2 pattern).** IMU noise
  covariances, feature/registration leaf sizes, and keyframe thresholds are left at LIO-SAM's
  own upstream defaults in the baseline config -- phase-1 manual/hypothesis-driven tuning
  (`docs/protocol.md` §6.1) is **explicitly skipped for this method** (confirmed decision).
  These become `scripts/lio_sam_sweep.py`'s search parameters directly, with ranges centered
  on the upstream defaults and spread 1-2 orders of magnitude wider than FAST-LIO2's
  phase-1-bounded sweep, since nothing measured bounds them here. Per `docs/protocol.md` §6.2,
  this is a documented deviation ("sweeping without a phase-1-justified region is guessing
  with extra steps, not a real phase 2"), not presented as equivalent rigor to FAST-LIO2's
  sweep -- every sweep-trial run record and the journal entry say so explicitly. LIO-SAM has
  no configurable optimization-iteration-count param (`mapOptmization.cpp` hardcodes 30 LM
  iterations at `src/mapOptmization.cpp:1292`), unlike FAST-LIO2's `max_iteration` -- verified
  against source, so no such sweep dimension exists for this method.
- **Status: unresolved rotation failure, not a working baseline yet.** The exp14 baseline, all
  8 sweep trials, and both held-out runs (`docs/journal.md`) share one pattern: ATE rotation
  RMSE stays 100-170 deg in every single run regardless of config, while translation error
  varies with the sampled params. This is not a normal tuning or generalization gap like
  FAST-LIO2's -- it is a structural failure. A diagnostic run
  (`20260915T222509Z_lio_sam_exp14`, `docs/journal.md`) zeroed `imuRPYWeight` (removing the
  Madgwick-synthesized orientation's influence on `mapOptmization`'s pose graph): translation
  improved dramatically (ATE trans RMSE 349.1 -> 29.3 m, >10x), confirming that constraint
  *was* corrupting translation, but rotation RMSE barely moved (124.7 -> 129.1 deg) -- so the
  orientation adapter's RPY soft-constraint is **not**, by itself, the dominant cause of the
  rotation failure. Remaining candidates, none yet isolated: IMU preintegration/scan-matching
  producing bad rotation independent of the RPY factor (raw gyro/accel drive preintegration
  via `extrinsicRot`, unaffected by `imuRPYWeight`); `Horizon_SCAN: 1800` (a datasheet
  estimate, not measured) degrading feature-based rotation estimation; or, less likely,
  something in evaluation/alignment itself. Root-causing this fully is exactly what phase-1
  manual investigation (`docs/protocol.md` §6.1) exists to catch before a sweep, and it was
  explicitly skipped for this method (confirmed decision) -- its absence is the direct,
  visible cost, not a silent one. **Do not use this integration for cross-method comparison
  until the rotation failure is fully root-caused and fixed.**

## Exclusions

None yet. Any method dropped later is listed here with the concrete reason: build failure on
the target environment, an unresolvable input incompatibility, or a runtime beyond the
hardware.
