# Methods

FAST-LIO2 integration is in progress (`docker/fast_lio2/`, `adapters/fast_lio2/`); no other
method is integrated yet. This page records scope decisions, the variants we mean, and
the integration questions each method raises for this dataset. The measured input facts are
in [dataset.md](dataset.md). Any claim about upstream behaviour below that is marked
**verify** has not yet been checked against the pinned source.

## Scope

| Method | Role | Planned environment | Status |
|---|---|---|---|
| FAST-LIO2 | core tightly coupled LIO, **first integration** | Ubuntu 20.04 / ROS Noetic | integrating, see below |
| FAST-LIO (original) | separate implementation, pinned to its own revision | its supported environment | not started |
| LIO-SAM | core LIO, GPS and loop closure disabled | Ubuntu 20.04 / Noetic, pinned GTSAM | not started; IMU orientation issue below |
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
   - **LIO-SAM:** use either (a) a documented, sensor-only orientation adapter (for example
     a complementary or Madgwick filter on the same IMU, never ground truth, with its
     parameters recorded), or (b) an explicitly named 6-axis derivative such as LIORF. A
     derivative is never labelled "LIO-SAM".
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
6. **Output frame.** Each adapter records whether the method publishes IMU or LiDAR body
   poses, so that `lio-bench eval --frame` converts them correctly.
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
  16 trials over the region phase 1 established (noise covariance, voxel size, plus
  previously-untried `point_filter_num`/`max_iteration`), `scripts/fast_lio2_sweep.py`. No
  trial beat the manually-tuned baseline on both ATE trans and rot RMSE together — a negative
  result; the config is unchanged.
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

## Exclusions

None yet. Any method dropped later is listed here with the concrete reason: build failure on
the target environment, an unresolvable input incompatibility, or a runtime beyond the
hardware.
