# Dataset: Hilti-Oxford 2022

- **Source:** [hilti-challenge.com/dataset-2022](https://hilti-challenge.com/dataset-2022),
  hosted at Hugging Face `Hilti-Research/hilti-slam-challenge-2022`. All downloads are pinned
  to revision `e62017f907007fdc5ab8c721842e4ae7359d7f49`.
- **Licence:** CC BY-NC-SA 3.0.
- **Citation:** Zhang et al., RA-L 8(1), 2023, doi:10.1109/LRA.2022.3226077.
- **Manifest:** [`manifests/hilti22.yaml`](../manifests/hilti22.yaml) lists every file with
  its size and published hash.

## Sequences and split

| Key | Sequence | Environment | Official difficulty | Role | Bag (GB) | Dense GT (poses, s) | Sparse points |
|---|---|---|---|---|---|---|---|
| exp14 | exp14_basement_2 | Basement 2 | Medium | tune | 6.26 | 689, 73.8 | 4 |
| exp16 | exp16_attic_to_upper_gallery_2 | Attic to Upper Gallery 2 | Hard | heldout | 15.52 | 2001, 200.1 | 9 |
| exp18 | exp18_corridor_lower_gallery_2 | Corridor Lower Gallery 2 | Hard | heldout | 8.66 | 789, 86.6 | 3 |

These are the only 2022 sequences with **dense 6-DoF** reference trajectories, so they are
the only ones that support rotation and drift (RPE) evaluation. The other sequences have
sparse position-only references. exp16 and exp18 were chosen as held-out sequences to fit
the tune-on-exp14 decision. Both held-out sequences are rated harder than the tuning
sequence, which should be kept in mind when comparing tune and held-out errors.

All three were recorded with the same handheld Phasma rig. They are Sheldonian Theatre
sequences: the official page marks construction-site sequences "Constr." and these three
are not marked. That is an inference from the page, not an explicit statement in it.

## Two kinds of ground truth

| | Dense `*_imu.txt` | Sparse `*_imu_3dof.txt` |
|---|---|---|
| Content | T_W_I at ~10 Hz, TUM `t x y z qx qy qz qw` | IMU-origin positions at a few instants |
| Provenance | a separate reconstruction; accuracy not documented at the level of the survey | surveyed control points, described by the dataset authors as millimetre-accurate |
| Used for | primary ATE/RPE and alignment | secondary per-point position error (not used for alignment) |

File-format facts (checked by the parsers and tests):

- The sparse files' header reads `# timestamp_s id x y z`, but every row has **eight**
  columns `t x y z 0 0 0 1`. The trailing identity quaternion is (x, y, z, w).
  `trajectory.load_sparse` reads the rows and ignores the header.
- The dense files have **gaps**: the largest is 0.61 s in exp14, 0.20 s in exp16 and 1.30 s
  in exp18, and the mean rates are 9.32, 10.00 and 9.10 Hz. The evaluator never
  interpolates ground truth; a gap simply contributes no samples.
- exp18's dense trajectory ends at t = 1649856314.3, but its last control point is at
  t = 1649856335.7. That control point lies outside the dense span, so it is evaluated only
  if the estimate covers it.
- Dense quaternions are (x, y, z, w) in a z-up world. At rest, rotating the measured specific
  force by the ground-truth orientation lands 0.65–4.7° from +z_W under that reading, and
  60–120° away under (w, x, y, z) (table below).

## Frames and calibration

From `calibration/calibration_files/lidar_calibration.yaml` ("Calibration Phasma25 22/03/22"),
copied into [`configs/dataset/hilti22.yaml`](../configs/dataset/hilti22.yaml) and checked
against the file by `lio-bench inspect`:

- **T_I_L** (PandarXT-32, parent `imu`): q_xyzw = (0.7071068, −0.7071068, 0, 0), t =
  (−0.001, −0.00855, 0.055) m. This is a 180° rotation about (1, −1, 0)/√2: z_L → −z_I and
  x_L → −y_I, with a lever arm of 5.6 cm. Read wrongly as (w, x, y, z), it would be a 90°
  rotation. A known-answer test (`tests/test_frames.py`) catches that.
- The IMU's own extrinsic is the identity (the IMU defines the body frame).
- **IMU intrinsics** in the same file: `bias_a`, `bias_g`, and a `gravity` vector along +y_I.
  The at-rest measurements below put "up" along −z_I at the start of every sequence, so that
  `gravity` entry reflects the rig's attitude during calibration. It is not a frame
  convention, and methods must not use it as one.
- `calibration/imu_noise_calibration.bag` (138 MB) is the static IMU recording for noise
  characterisation, for example Allan variance. The dataset page does not publish noise
  densities for the BMI085, so any values used are derived from this bag and recorded with
  their method.
- Camera calibration (`calib_3_cam0-1-camchain-imucam.yaml`) is downloaded for completeness
  but not used by LiDAR-inertial methods.

## Measured sensor facts

Produced by `lio-bench inspect <seq>` (reports in `<data root>/_provenance/inspect/`) and
reproduced here without editing.

| Measured | exp14 | exp16 | exp18 |
|---|---|---|---|
| Bag duration (s) | 74.0 | 200.4 | 109.4 |
| LiDAR scans / rate (Hz) | 740 / 10.00 | 2003 / 10.00 | 1094 / 10.00 |
| Points per scan (median, min–max) | 60948 (47959–63563) | 59477 (50535–63097) | 58934 (52181–63013) |
| Point layout | x:f4@0, y:f4@4, z:f4@8, intensity:f4@16, timestamp:f8@24, ring:u2@32; step 48 | x:f4@0, y:f4@4, z:f4@8, intensity:f4@16, timestamp:f8@24, ring:u2@32; step 48 | x:f4@0, y:f4@4, z:f4@8, intensity:f4@16, timestamp:f8@24, ring:u2@32; step 48 |
| Per-point time | `timestamp` seconds_absolute | `timestamp` seconds_absolute | `timestamp` seconds_absolute |
| Scan time spread (median s) | 0.1000 | 0.1000 | 0.1000 |
| First point − header (median µs) | +1.0 | +1.0 | +1.0 |
| Ring range | 0–31 | 0–31 | 0–31 |
| Range p01 / median / p99 (m) | 0.20 / 1.10 / 10.2 | 0.20 / 0.90 / 22.8 | 0.17 / 0.82 / 22.0 |
| Non-finite points | 0.00% | 0.00% | 0.00% |
| IMU samples / rate (Hz) | 29539 / 399.2 | 79958 / 399.2 | 43656 / 399.2 |
| IMU max gap (ms) / non-monotonic | 2.54 / 0 | 2.54 / 0 | 2.54 / 0 |
| IMU orientation | all zero, cov[0]=[0.0], usable=False | all zero, cov[0]=[0.0], usable=False | all zero, cov[0]=[0.0], usable=False |
| At-rest specific force (m/s², first 1 s) | [0.173, 0.164, -9.660], up -z | [0.172, 0.053, -9.668], up -z | [0.161, -0.006, -9.666], up -z |
| At-rest gyro mean (rad/s) | [1.06e-03, -2.66e-04, -2.34e-05] | [7.51e-04, 5.65e-05, 4.34e-05] | [8.61e-04, 2.90e-04, -7.35e-05] |
| Bag time − header (max abs, µs) | 0.24 | 0.24 | 0.24 |
| Dense GT poses / rate (Hz) / max gap (s) | 689 / 9.32 / 0.61 | 2001 / 10.00 / 0.20 | 789 / 9.10 / 1.30 |
| Dense GT start after sensors / end before (s) | +0.08 / +0.00 | +0.04 / +0.00 | +0.05 / +22.60 |
| Dense GT path length (m) | 37.8 | 116.9 | 50.6 |
| Sparse control points (outside dense span) | 4 (0) | 9 (0) | 3 (1) |
| Gravity check xyzw / wxyz (deg) | 0.65 / 91.2 | 1.32 / 120.4 | 4.66 / 59.9 |
| Calibration file matches config | True | True | True |

Notes on the table:

- **Topics.** Every bag also carries five camera topics (`/alphasense/cam0`–`cam4`) and a
  `/Point_name` topic. `/Point_name` has exactly as many messages as the sequence has sparse
  control points (4, 9 and 3), so it marks the control-point measurements. Neither is used.
- **At-rest window.** This is the first 1 s of each bag. exp14 and exp18 are still
  (accelerometer std ≤ 0.02 m/s²). exp16 moves slightly (std 0.13–0.29 m/s²).
- **Gravity check.** The (x, y, z, w) reading wins on every sequence, 0.65–4.7° versus
  60–120°. exp18's 4.7° is larger than its stillness and accelerometer bias (about 0.5°)
  explain. The cause is **not established**: it could be dense-GT orientation error near the
  start, or a world frame that is not exactly gravity-aligned. It is worth rechecking before
  interpreting small rotation errors on exp18.
- **exp18 dense GT ends 22.6 s before the sensors stop.** Methods run over the whole bag, but
  only the first 86.6 s are scored against dense ground truth.

Consequences for integration are listed in [methods.md](methods.md#dataset-specific-integration-questions):
- **IMU orientation:** all zero, and the covariance does not flag it as absent.
- **Per-point time:** absolute timestamps.
- **Range:** very short near-range returns.
- **Timing:** log time equals header stamp, so latency cannot be measured from the recording.

## Derived data

`lio-bench data convert <seq>` writes `rosbag2/<sequence>/` (MCAP, LiDAR and IMU topics
only) for ROS 2 methods. A conversion is accepted only if, for each topic, the message type,
count, first and last log time, first and last header stamp, and a SHA-256 over the consumed
content all match the ROS 1 bag. The content is header stamps plus IMU vectors and
covariances, or PointCloud2 layout plus point bytes. Records are kept in
`_provenance/conversions/`.

| Sequence | Topic | ROS 1 msgs | MCAP msgs | Content SHA-256 match | Produced by |
|---|---|---|---|---|---|
| exp14 | `/alphasense/imu` | 29539 | 29539 | yes | pre-existing (ranger-lio `convert_bag.sh`), checked |
| exp14 | `/hesai/pandar` | 740 | 740 | yes | pre-existing (ranger-lio `convert_bag.sh`), checked |
| exp16 | `/alphasense/imu` | 79958 | 79958 | yes | `lio-bench data convert` |
| exp16 | `/hesai/pandar` | 2003 | 2003 | yes | `lio-bench data convert` |
| exp18 | `/alphasense/imu` | 43656 | 43656 | yes | `lio-bench data convert` |
| exp18 | `/hesai/pandar` | 1094 | 1094 | yes | `lio-bench data convert` |

All three use rosbag2 metadata version 9 (`rosbags` 0.11.5, MCAP storage).

## Local layout

```
$LIO_DATA_ROOT/                       (default ~/data/hilti22; mounted at /data/hilti22)
  rosbags/<sequence>.bag              ROS 1 originals (verified SHA-256)
  rosbag2/<sequence>/                 derived MCAP (equivalence-checked)
  ground_truth/                       dense and sparse references (verified git blob SHA-1)
  calibration/                        calibration YAMLs, imu_noise_calibration.bag
  _provenance/verified.json           what was hashed, when, against which revision
  _provenance/conversions/*.json      conversion equivalence records
  _provenance/inspect/*.json          measured sensor facts
```

The layout matches what ranger-lio's scripts expect, so both projects can share one copy of
the data.
