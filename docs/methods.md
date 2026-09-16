# Methods

FAST-LIO2 and LIO-SAM are fully integrated (`docker/fast_lio2/`, `adapters/fast_lio2/`;
`docker/lio_sam/`, `adapters/lio_sam/`), both merged to `main`. GLIM integration is in progress
(`docker/glim/`, `configs/glim/`). This page records
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
| GLIM | CPU LiDAR-inertial odometry; global mapping only as secondary | Ubuntu 22.04 / ROS 2 Humble, no CUDA | integrating, see below |
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
   - **GLIM (resolved):** ignores it. `glim_ros2/src/glim_ros/glim_ros.cpp`'s `imu_callback`
     reads only `linear_acceleration`/`angular_velocity`, never `msg->orientation` (confirmed
     against source) -- same conclusion as FAST-LIO2, no adapter needed.
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
   - **GLIM (resolved):** `preprocess.distance_near_thresh: 0.1` (upstream default 0.5, which
     would drop real short-range returns), same reasoning as FAST-LIO2's `blind`/LIO-SAM's
     `lidarMinRange`.
5. **Extrinsics.** T_I_L rotates z_L to −z_I (the LiDAR is mounted upside down relative to
   the IMU), with a 5.6 cm lever arm. Each method's extrinsic convention (T_I_L versus T_L_I,
   rotation matrix order) is checked with a known-answer test before the first run.
   - **LIO-SAM (resolved):** needs `T_L_I` (`T_I_L` inverted), not `T_I_L` directly, despite
     `config/params.yaml`'s own comment calling it `"T_lb (lidar -> imu)"`. Confirmed by
     reading `imuConverter()`'s actual usage (`acc = extrinsicRot * acc_imu`, rotating an
     IMU-frame vector into the lidar/`base_link`-aligned frame LIO-SAM assumes throughout),
     not the misleading comment. See `configs/lio_sam/hilti22.yaml` and
     `tests/test_frames.py::test_lio_sam_extrinsic_is_T_L_I_not_T_I_L`.
   - **GLIM (resolved):** also needs `T_L_I`, same direction as LIO-SAM.
     `glim/src/glim/preprocess/cloud_preprocessor.cpp` computes `T_imu_lidar =
     T_lidar_imu.inverse()`, then applies `p_imu = T_imu_lidar * p_lidar` -- so the config
     value `sensors.T_lidar_imu` (its name notwithstanding) is `T_L_I`, `T_I_L` inverted.
     Numerically identical to LIO-SAM's `extrinsicRot`/`extrinsicTrans` (`T_I_L`'s rotation is
     self-inverse; translation is not). See `configs/glim/hilti22.yaml` and
     `tests/test_frames.py::test_glim_extrinsic_is_T_L_I_not_T_I_L`.
6. **Output frame.** Each adapter records whether the method publishes IMU or LiDAR body
   poses, so that `lio-bench eval --frame` converts them correctly.
   - **LIO-SAM (resolved):** LiDAR-frame, the opposite of FAST-LIO2. `mapOptmization.cpp`
     keeps `lidarFrame == baselinkFrame == "base_link"` and publishes its optimized pose
     directly on `lio_sam/mapping/odometry` with no further frame conversion -- use
     `--frame lidar`.
   - **GLIM (resolved):** IMU-frame, like FAST-LIO2. The `librviz_viewer.so` extension module
     (`glim_ros2/src/glim_ros/rviz_viewer.cpp`) publishes both `<node>/odom` (`T_world_imu`)
     and `<node>/lidar_odom` continuously as the online estimate is produced -- use
     `<node>/odom`, `--frame imu`. (Its `*_corrected` topics are the retrospectively-optimized
     global-mapping poses; per `docs/protocol.md` #1 those are the secondary comparison only,
     never substituted for the online primary poses.)
7. **ROS 2 input.** The rosbag2 conversions used metadata version 9 by default. ROS 2 Humble
   (GLIM, RTAB-Map) needs `lio-bench data convert --dst-version N` with an older version.
   - **GLIM (resolved for exp14).** Metadata version 9 (the original conversions'
     `rosbags`-library default) does not parse under Humble: `ros2 bag info` fails with
     `yaml-cpp: error ... bad conversion` on the version-9 metadata's `type_description_hash`
     field, a schema element newer than Humble's `rosbag2_storage`. Humble's own `ros2 bag
     record` writes version 5, confirmed directly inside the built image; re-running
     `lio-bench data convert exp14 --dst-version 5` (equivalence-checked, content matched)
     produces a bag Humble reads cleanly. **exp16/exp18 still need the same re-conversion
     before they can be used with GLIM** (their held-out evaluation is out of scope for the
     current phase-1 tuning work, so not done yet).

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
  - **Accuracy of the substitute, measured against ground truth.** Upstream's README requires
    a 9-axis IMU, and states what it needs the estimate for: roll/pitch "to initialize the
    system at the correct attitude", yaw "to initialize the system at the right heading when
    using GPS data" (no GPS in this benchmark, `docs/protocol.md` #1, so the yaw role does not
    apply). Running the filter over exp14's full IMU stream and comparing the gravity
    direction it implies in the body frame against dense GT (yaw-independent, so the
    unobservable heading does not contaminate it): tilt error mean 1.60 deg, median 0.93 deg,
    p95 4.64 deg, max 7.92 deg, and **0.70 deg over the 6 s static window the system
    initializes in**. Yaw drift relative to GT over the whole 74 s sequence is 1.2 deg max --
    small only because the sequence is short; it is unbounded in principle. So the deviation
    from the 9-axis requirement is real but quantified, and small exactly where the README
    says the estimate matters.
  - **What the deviation costs, bounded with a synthetic perfect IMU.** Hilti's own GT
    orientation, interpolated to 400 Hz, was fed to LIO-SAM in place of the Madgwick output as
    a stand-in for a real 9-axis sensor (a **GT-fed diagnostic that violates
    `docs/protocol.md` §3 and is never reportable**, run `20260916T0006*`, `docs/journal.md`).
    Result, on exp14 with the fixed config: at the frozen `imuRPYWeight: 0.0` the orientation
    source makes no measurable difference, because at weight 0 the quaternion only seeds the
    initial attitude and the fallback guess. With upstream's `imuRPYWeight: 0.01` restored, a
    perfect orientation is worth roughly 0.19 m ATE translation, 3.8 deg ATE rotation and
    5.9 deg RPE 10 s rotation against the compliant Madgwick control. So the 9-axis deviation
    is moot as configured today and modest but real if the RPY constraint is re-enabled --
    which that experiment also showed is no longer harmful post-degeneracy-fix, unlike the
    pre-fix diagnostic that motivated setting it to 0.
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
  - **Checked physically, not just by convention.** The README's requirement is that IMU data,
    once transformed, is in the lidar frame under ROS REP-105 (x forward, y left, z up), and
    it asks the user to verify by rotating the sensor suite while printing the transformed
    readings in `imuHandler()`. That procedure is impossible on a recorded bag, so the
    equivalent was done numerically against ground truth, which is stronger than reading
    printed values: (a) the measured at-rest specific force [0.173, 0.164, -9.660] m/s^2
    (`docs/dataset.md`) maps through `extrinsicRot` to [-0.164, -0.173, **+9.66**], i.e. z up
    and +9.8-ish as REP-105 requires; (b) the raw gyro matches GT body angular velocity per
    axis with correlation 0.9994 / 0.9997 / 1.0000 and slope 1.001 / 1.001 / 0.998, ruling out
    any axis swap, sign flip or scale error before `extrinsicRot` is applied at all. Note also
    that `T_I_L` here is a 180 deg rotation about (1, -1, 0) and therefore self-inverse, so the
    `T_L_I` vs `T_I_L` direction cannot change the rotation part either way -- the distinction
    matters for `extrinsicTrans`, not for `extrinsicRot`. `extrinsicRPY` satisfies the README's
    own definition: it asks for `q_lb`, and `imuConverter()` forms `q_final = q_from * extQRPY`
    with `extQRPY = extRPY.inverse()`, giving `q_wl = q_wb * q_bl` as documented.
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
- **Degeneracy threshold patch (root cause of the rotation failure, resolved).** Every early
  LIO-SAM run (exp14 baseline, all 8 sweep trials, both held-out runs, four diagnostics)
  shared ATE rotation RMSE of 100-170 deg regardless of config. Offline analysis of those
  trajectories showed yaw was tracked (1 s yaw-rate correlation with GT 0.69) while roll and
  pitch were not (0.1-0.2), z spanned 72 m against GT's 4 m, and -- decisively -- ground truth
  is motionless for the first 6 s of exp14 yet every run tilted identically to ~-30 deg
  pitch and sank ~1.1 m in that window. Against a fixed single-scan map with nothing moving,
  scan-to-map can only drift like that if it is not applying the tilt/z updates. Recording
  LIO-SAM's internals (`scripts/run_lio_sam.sh` with `LIO_SAM_RECORD`, analysed by
  `scripts/lio_sam_diag.py`; run `20260915T230256Z`) showed `mapOptmization::LMOptimization()`'s
  degeneracy flag set on 91% of scans from the very first, feature counts healthy (~480 corner
  / ~1500 surf per scan) and IMU delivery complete, and the LM output's per-scan z step equal
  to the IMU-preintegration guess's. Mechanism: upstream zeroes any update direction whose
  J^T J eigenvalue is below a hardcoded 100 -- an outdoor-Velodyne scale (rotation-block
  eigenvalues scale with range squared; this scene's median range is ~1 m), so tilt/z were
  classed as degenerate, their updates discarded, the pose rode the preintegration on those
  axes, and the corrupted keyframes poisoned the map. `docker/lio_sam/degeneracy_threshold.patch`
  (applied with `git apply` next to the Noetic patches) exposes the cutoff as
  `lio_sam/degeneracyThreshold` (default 100, upstream-identical) and logs the six
  eigenvalues per scan. With it at 0 (run `20260915T230642Z`) the static phase holds to
  +-0.4 deg / 2 cm, resets drop to 0, and exp14 goes from ATE 29.3 m / 129 deg to
  1.07 m / 18.8 deg (RPE 1 s rot 26.6 -> 4.5 deg). Measured eigenvalues: the smallest is 30-48
  while the rig is static and LM holds exactly, median 42, p10 12.6, so 73% of scans sit
  below upstream's 100. A measured 10 (run `20260915T231202Z`) was not better, and the
  projection has only ever been seen to harm on this data, so the frozen config keeps it
  off (`degeneracyThreshold: 0.0`); 0 vs 10 is a phase-1 item to settle with repeats.
  **Confirmed against upstream's own data**: replaying LIO-SAM's `walking_dataset` (VLP-16,
  outdoor, real 9-axis Microstrain, upstream `params.yaml` verbatim, threshold left at its
  default 100) runs clean with zero warnings of any kind, and its smallest LM eigenvalue has a
  median of 564.6 against Hilti's 42.2 -- 13x larger, tripping upstream's threshold on 2.5% of
  scans versus 73% here. So the constant is well-calibrated for the range regime LIO-SAM was
  developed in and simply encodes an assumption this dataset violates; nothing about this
  integration is at fault. That run also validates the build end to end on reference data and
  confirms the patch is behaviour-preserving when the param is unset (`docs/journal.md`).
  Also learnt on the way: `imuRPYWeight: 0.0` (run `20260915T222509Z`, the Madgwick roll/pitch
  slerp cost >10x in translation; kept), and the run-to-run variance of a diverged estimator is
  enormous (an identical config gave 0 and 46 preintegration resets), which is why the three
  earlier single-run diagnostics (Horizon_SCAN 1630, heading init off, loop closure on) read
  as "worse" without meaning anything.
- **Gravity magnitude (measured, kept).** `imuGravity: 9.663`, the at-rest specific-force norm
  from `docs/dataset.md` (9.660-9.668 across all three sequences), not upstream's 9.80511.
  LIO-SAM fixes gravity magnitude inside GTSAM's preintegration and its accel-bias random walk
  cannot absorb a 0.14 m/s^2 mismatch (FAST-LIO2 estimates gravity as a state and never saw
  this). Evidence: at 9.80511 the preintegration guess sank at ~0.125 m/s^2 on a provably
  static rig; at 9.663 its static-phase z step is ~0 (run `20260915T231502Z`). Metrics inside
  the fixed config's measured run-to-run spread (repeat `20260915T231728Z`: ATE trans
  0.74-1.07 m, rot 19-22 deg, RPE 10 s rot 6-27 deg on exp14 -- large, so phase-1 judgements
  need >=3 repeats; rate-1.0 playback on a 2c/4t machine is the suspected source).
- **Status: rotation failure fixed; not yet a tuned, comparable baseline.** The remaining gap
  to FAST-LIO2 on exp14 (0.04 m / 0.8 deg) is ordinary integration and tuning work. Still to
  do before this method's numbers can be compared: the phase-1 manual tuning that was skipped
  (repeats to bound run-to-run variance, ideally at rate 0.5; `degeneracyThreshold` 0 vs 10; `Horizon_SCAN` 2000
  from the measured 0.18 deg azimuth step -- the config's 1800 is a datasheet guess and the
  earlier 1630 test was a returned-point count, not the grid), then a properly bounded
  phase-2 sweep and a fresh held-out evaluation. The old sweep and held-out numbers describe
  the bug, not the method.

## GLIM integration

`docker/glim/Dockerfile` installs `ros-humble-glim-ros` (pinned `1.2.2-0jammy`) from
koide3's own official binary PPA (`https://koide3.github.io/ppa/`) on `ros:humble-ros-base`
(pinned by digest) -- the no-CUDA variant, which is what makes the image CPU-only
(`docs/protocol.md` #5: "GLIM runs CPU-only"), not a runtime config flag.

Building GTSAM + `gtsam_points` + `glim` + `glim_ros2` from source was tried first and
abandoned: the `ppa:borglab/gtsam-release-4.0` package LIO-SAM uses on Noetic/focal does not
actually publish `jammy` packages (its Launchpad overview page's series list is misleading;
its real `dists/` directory only has `bionic`/`devel`/`focal`/`xenial` -- checked directly by
hitting the apt URL, not by reading the web page), and `gtsam_points` has since moved to
GTSAM 4.3a1 regardless, unrelated to LIO-SAM's 4.0.3. koide3's own PPA ships a maintained,
versioned, no-CUDA binary for exactly this combination (confirmed dependency chain:
`ros-humble-glim-ros` -> `ros-humble-glim` -> `libgtsam-points-dev` -> `libgtsam-notbb-dev`,
i.e. GTSAM 4.3.0 built with `GTSAM_WITH_TBB=OFF`) -- this is upstream's own documented,
recommended install path (`gtsam_points`'s README "Install from PPA" section), not a shortcut
around it, and avoids building four C++ projects from source on this machine's 2c/4t CPU.

- **No point-cloud or orientation adapter needed (unlike FAST-LIO2/LIO-SAM).** Verified
  against the pinned source, not assumed:
  - `include/glim/util/ros_cloud_converter.hpp`'s `extract_raw_points` auto-detects the
    per-point time field by trying `"t"`/`"time"`/`"time_stamp"`/`"timestamp"` -- Hilti's
    field is literally named `timestamp` (`docs/dataset.md` point 2), an exact match.
    `ring_field`/`intensity_field` are plain config strings matching Hilti's own field names
    (`"ring"`/`"intensity"`) directly.
  - `glim_ros2/src/glim_ros/glim_ros.cpp`'s `imu_callback` never reads `msg->orientation`
    (dataset question 1, resolved above).
  - So the "adapter" for GLIM is config values only (`configs/glim/hilti22.yaml`), verified
    end-to-end by a run rather than by a point-cloud unit test.
- **Per-point time (point 2, resolved).** `sensors.autoconf_perpoint_times: false` and
  `sensors.perpoint_relative_time: false`, pinned rather than trusting `TimeKeeper`'s
  auto-detect heuristic, because Hilti's `timestamp` field is absolute epoch seconds, not
  relative -- same reasoning as FAST-LIO2's `timestamp_unit: 0`. To be confirmed with a short
  run + log inspection before relying on it (**verify**).
- **Extrinsics (point 5, resolved above).** `configs/glim/hilti22.yaml`'s `sensors.T_lidar_imu`
  is `T_L_I`, verified by `tests/test_frames.py::test_glim_extrinsic_is_T_L_I_not_T_I_L`.
- **Blind zone (point 4, resolved above).** `preprocess.distance_near_thresh: 0.1`.
- **Output frame (point 6, resolved above).** `<node>/odom` (IMU frame, `T_world_imu`),
  published by the `librviz_viewer.so` extension module -- not a GUI, needs only
  `rclcpp`/`tf2`/`nav_msgs` (`glim_ros2/src/glim_ros/rviz_viewer.cpp`), so it runs fine
  headless; `libstandard_viewer.so` (Iridescence/OpenGL) is left out of
  `ros.extension_modules`, same reasoning as the GLFW/Wayland viewer note in `HANDOFF.md`.
- **Run wrapper: no roscore, no bag player, no sim-time hazard.** GLIM ships its own offline
  bag-replay binary, `glim_rosbag <rosbag2 dir>` (`glim_ros2/src/glim_rosbag.cpp`), which
  auto-detects `mcap` vs `sqlite3` storage from `metadata.yaml`, drives everything off
  in-process message timestamps (a `playback_speed` config value, read directly from
  `config_ros.json`, not a ROS param, controls the real-time factor), and calls
  `glim->save(dump_path)` on exit -- this replaces the entire
  roscore/`rosbag play`/readiness-poll/SIGINT dance both prior wrappers needed, because
  nothing here depends on a live `/clock` topic. `scripts/run_glim.sh` materializes
  `configs/glim/hilti22.yaml`'s sections into GLIM's native `config/*.json` file set
  (`scripts/glim_materialize_config.py`, on top of upstream's own defaults for files this repo
  doesn't override) before launch, then discovers the odometry topic via `ros2 topic list`
  once `glim_rosbag` actually advertises it (confirmed by a real run to resolve to
  `/glim_ros/odom`, discovered rather than hardcoded in case a future version changes the node
  name) and runs the TUM exporter (`adapters/glim/odom_to_tum.py`, `rclpy`) against that topic.
  `glim->save(dump_path)`'s output is at most a secondary artifact (global map,
  `docs/protocol.md` #1) -- the primary comparison is the online `<node>/odom` stream the
  exporter captures live, same pattern as `odom_to_tum.py`.
- **Two real bugs found only by running it, not by reading source.** (1) An empty
  `ros.image_topic` (the config section's own field was simply unset at first) crashes the
  whole node on startup: `rclcpp::exceptions::InvalidTopicNameError`, because GLIM's image
  callback still calls `create_subscription` on the empty string rather than treating it as
  "disabled" -- fixed by setting a real, harmless, never-published placeholder topic. (2)
  `configs/glim/hilti22.yaml` was first written against config values fetched from GLIM's
  GitHub `master` branch, which has diverged from the pinned stable package (1.2.2-0jammy):
  `sensors.imu_bias_noise` is one field on 1.2.2, split into
  `imu_bias_noise_acc`/`imu_bias_noise_gyro` on `master`; `odometry_estimation.
  initialization_mode` only recognizes `"LOOSE"` on 1.2.2, not `master`'s `"ROBUST"` (silent
  `[odom] [error] unknown initialization mode` at runtime, not a build-time failure). Both
  fixed by dumping `$(ros2 pkg prefix glim)/share/glim/config/*.json` from inside the built
  image and reconciling against that, not GitHub source alone -- the same lesson as checking
  actual `nh.param()` calls instead of assumed config nesting (FAST-LIO2) or the actual
  compiled cutoff instead of a misleading comment (LIO-SAM), just one layer further out: for a
  binary-packaged dependency, the installed version's own shipped config is the ground truth,
  not any particular git ref.
- **Config: dataset adaptation vs tuning.** `configs/glim/hilti22.yaml` mirrors GLIM's own
  JSON sections; `sensors`/`preprocess`/`ros` hold the dataset-adaptation values above.
  `odometry_cpu` (the CPU registration backend, `libodometry_estimation_cpu.so` -- already
  the code's own hardcoded fallback default, so this is upstream's intended CPU path, not a
  workaround) is left at upstream defaults in the adapted baseline
  (`registration_type: GICP`, `ivox_resolution: 1.0`, `vgicp_resolution: 0.5`); these, plus
  `num_threads`, are the phase-1 tuning candidates (`docs/protocol.md` #6.1), by direct
  analogy with FAST-LIO2's `filter_size_surf`/`filter_size_map` finding (same measured point
  spacing, 0.36-3.4 cm, and the same short-range scene). `sub_mapping_cpu`/`global_mapping_cpu`
  are left at upstream CPU defaults throughout -- this benchmark's primary comparison is
  online odometry only (`docs/protocol.md` #1); GLIM's global mapping is secondary and out of
  scope for tuning.
- **Status: integrating, first phase-1 pass done, not yet a comparable baseline.** Adapted
  baseline established (3 repeats, exp14: ATE trans RMSE 0.51-1.69 m, rot RMSE 16.7-36.6 deg --
  large run-to-run spread, same lesson LIO-SAM's tuning drew). Phase-1 (`docs/protocol.md`
  #6.1, `docs/journal.md` "GLIM integration and phase-1 tuning summary"):
  `odometry_cpu.ivox_resolution` 1.0 -> 0.2 m **kept** (3 repeats: ATE trans 0.088-0.106 m,
  rot 1.4-2.2 deg -- competitive with FAST-LIO2's 0.04 m / 0.8 deg, direct analogue of its
  `filter_size_surf`/`filter_size_map` finding); `ivox_resolution` 0.1 m, `registration_type`
  VGICP (matched resolution), and `odometry_cpu.num_threads` 4 all tried and **reverted** (not
  shown better, VGICP clearly worse). Still open: IMU noise covariance (GLIM's preintegration
  noise-unit convention needs verifying against source before reusing FAST-LIO2's measured std
  values -- not yet done, unlike LIO-SAM's/FAST-LIO2's completed noise tuning),
  `smoother_lag`/`max_iterations`, a properly bounded phase-2 sweep, and held-out evaluation on
  exp16/exp18 (their rosbag2 conversions still need the same `--dst-version 5` regeneration
  exp14 got, point 7 above).

## Exclusions

None yet. Any method dropped later is listed here with the concrete reason: build failure on
the target environment, an unresolvable input incompatibility, or a runtime beyond the
hardware.
