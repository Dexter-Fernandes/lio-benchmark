# lio-benchmark — agent handoff

Prepared: 14 September 2026. Updated: 15 September 2026. Status: foundation done, **FAST-LIO2
fully integrated, tuned and evaluated held-out**, merged to `main`. **LIO-SAM integration
scaffolding is complete and runs end-to-end (branch `feat/lio-sam-integration`, not merged),
but has an unresolved, structural rotation failure across every run — not a working baseline
for comparison yet.** See "LIO-SAM: status and open issue" below.

## Goal and confirmed decisions

Build an interview portfolio project comparing LiDAR-inertial odometry methods on Hilti–Oxford 2022. Demonstrate reproducible integration, tuning (manual, then automated search once a manual phase bounds the search region), held-out evaluation, and failure analysis.

- Repo: `https://github.com/Dexter-Fernandes/lio-benchmark.git` (origin). Work happens on
  `feat/<method>-integration` branches, fast-forward merged into `main` when done (confirm with
  the user before merging/pushing).
- Tune on **exp14**; hold out **exp16, exp18** (see [docs/protocol.md](docs/protocol.md) §2).
- Devcontainers for execution, Weights & Biases for tracking (**online by default** now — see
  below, this changed from the original "offline first" plan).
- Tuning is two-phase (`docs/protocol.md` §6): manual/hypothesis-driven first, then an
  automated (Bayesian) search once phase 1 has bounded a sensible region. Not a blind sweep
  from upstream defaults.
- Methods requested: LOAM, LIO-SAM, GLIM, FAST-LIO, FAST-LIO2, RTAB-Map and other applicable
  methods. Explain exclusions and distinguish variants accurately (`docs/methods.md`).
- User delegated metric recommendations to the assistant.

## Current state (15 September 2026)

**Foundation** (from the original `scaffold/foundation` branch, now in `main`): `lio-bench` CLI,
tools image + devcontainer, manifest, verified/converted/inspected Hilti-Oxford data for
exp14/exp16/exp18, the evaluator, run-record system. See README.md for commands; unchanged in
substance since the last handoff, so not repeated here in full — read `docs/dataset.md` for the
measured sensor facts (GT quaternion order, IMU orientation validity, per-point timestamp
format, extrinsics) that **every** method integration needs.

**FAST-LIO2: done, merged to `main`.** This is the reference integration for every method after
it — read `docs/methods.md`'s "FAST-LIO2 integration" section and `scripts/run_fast_lio2.sh`
before starting LIO-SAM; the pattern (adapter, config, run wrapper, tuning, held-out eval, map
artifacts) repeats with method-specific changes only. Summary:

- `docker/fast_lio2/Dockerfile` + `.devcontainer/fast_lio2/`: ROS Noetic, `hku-mars/FAST_LIO`
  pinned at `7cc4175`, base image pinned by digest.
- `adapters/fast_lio2/`: point-time adapter (absolute epoch `timestamp` → FAST-LIO2's relative
  `time` field), unit-tested in `tests/test_adapters.py`; a `/Odometry` → TUM exporter.
- `configs/fast_lio2/hilti22.yaml`: frozen, tuned config (measured IMU noise covariance,
  measured registration voxel size). `scripts/fast_lio2_candidate.py` generates dotted-override
  candidates for tuning attempts; reusable as-is for any method's config.
- `scripts/run_fast_lio2.sh`: launch/readiness/timeout/shutdown wrapper, exports
  trajectory.tum + map.pcd. **Read this before writing a LIO-SAM equivalent** — it has two
  non-obvious fixes worth not re-discovering: (1) `filter_size_surf`/`filter_size_map` are
  flat top-level rosparams, not nested — check each method's actual `nh.param()` calls rather
  than assuming config nesting from a launch file's XML structure; (2) never use
  `rosbag play --clock`/`use_sim_time` with a node whose shutdown-save logic runs inside
  `ros::Rate::sleep()` — sim time stops advancing the instant bag playback ends, and the node
  hangs forever waiting on `/clock`. Use wall-clock ROS time; every method here keys off
  message `header.stamp`, never `ros::Time::now()`, so this costs nothing.
- Tuned on exp14 (`docs/journal.md`): measured IMU noise covariance (kept), measured
  registration voxel size 0.2 m (kept), a 15-trial Bayesian sweep over the phase-1-bounded
  region (no improvement, negative result — config unchanged).
- Held out on exp16 (catastrophic divergence starting ~t=170-180s, open failure-analysis case,
  root cause not yet investigated) and exp18 (normal generalization gap).
- Map artifacts (`map.pcd`/`map.png`) generated per run; `lio-bench view <run_id>` / `--traj`
  visualizes them (GLFW/Wayland interactive viewer is broken on this user's desktop — `--png`
  is the reliable fallback, always available).

**W&B**: entity is the user's default (`retro.aspect520@gmail.com`'s account), project
`lio-benchmark`. `WANDB_MODE` defaults to **online** now (not offline as originally planned) —
every run lands on the dashboard automatically. `scripts/wandb_setup.sh` does one-time login.
`lio-bench report` builds/updates a saved W&B Report comparing every logged run.

Not done (working): LIO-SAM (see below), GLIM, DLIO, original FAST-LIO, RTAB-Map, LOAM. No
cross-method comparison yet (only FAST-LIO2 has trustworthy results).

## Hardware and execution constraints

User-reported machine (unchanged):

| Component | Specification |
|---|---|
| Laptop | Acer Aspire F5-573G |
| OS | Kubuntu 26.04.1 LTS, x86_64 |
| Kernel | Linux 7.0.0-31-generic |
| CPU | Intel Core i7-7500U, 2 cores / 4 threads |
| GPUs | NVIDIA GeForce 940MX and Intel HD Graphics 620 |
| RAM | 11.55 GiB total |
| Swap | 16.12 GiB |
| Root partition | ~54 GiB free (build cache) |
| Home partition | ~111 GiB free (data, out of Git) |
| Desktop | KDE Plasma / Wayland |

One headless experiment at a time; CPU-only for GLIM; one or two compile jobs. FAST-LIO2 ran
fine on this hardware at 1.0x real-time playback — a reasonable default to try for LIO-SAM too,
falling back to slower playback only if it overloads.

## LIO-SAM: status and open issue

Branch `feat/lio-sam-integration` (not merged — do not merge until the rotation failure below
is fixed and results are trustworthy). Full scaffolding done and builds/runs end-to-end,
following the FAST-LIO2 pattern (`docker/lio_sam/`, `adapters/lio_sam/`, `configs/lio_sam/`,
`scripts/run_lio_sam.sh`), with two confirmed decisions from this session:

- **Orientation:** a Madgwick filter adapter (`adapters/lio_sam/orientation_filter.py`,
  `imu_orientation_node.py`), not a named derivative — genuine upstream `TixiaoShan/LIO-SAM`
  with a sensor-only dataset adapter. Confirmed necessary: `imuConverter()`
  (`include/utility.h`) calls `ros::shutdown()` on a near-zero-norm quaternion, which the raw
  all-zero orientation triggers immediately.
- **Tuning:** phase-1 manual/hypothesis-driven tuning (`docs/protocol.md` §6.1) was
  **explicitly skipped** for this method (confirmed decision) — went straight from baseline
  to a wide, upstream-default-centered Bayesian sweep. **This turned out to matter**: see
  below.

**What happened, in order** (full detail in `docs/journal.md`, `docs/methods.md` "LIO-SAM
integration"):

1. Noetic/GTSAM build: LIO-SAM's own bundled Docker instructions target Kinetic; used the
   upstream-maintainer-endorsed fix from `github.com/TixiaoShan/LIO-SAM/issues/206` (GTSAM
   4.0.3 from the official PPA, two source patches for OpenCV/FLANN and C++14) — builds clean.
2. First run attempt crashed immediately: three of LIO-SAM's four nodes hardcode
   `ros::init(..., "lio_sam")` in source and rely on `roslaunch`'s automatic per-node name
   remapping; plain `rosrun` calls (this project's convention, no `roslaunch`) collided and
   evicted each other from the ROS master. Fixed with explicit `__name:=` remaps in
   `scripts/run_lio_sam.sh` — a real bug, not a config issue.
3. **Baseline run on exp14 diverges catastrophically**: ATE trans RMSE 349 m, rot RMSE
   124.7 deg (run `20260915T214917Z_lio_sam_exp14`, decision `investigate`), with 36 "Large
   velocity, reset IMU-preintegration!" warnings in the log — a real estimator failure, not a
   normal integration gap.
4. **8-trial Bayesian sweep** (wide ranges, phase-1 skipped, sweep `udrqijbp`) over IMU
   noise/leaf-size/keyframe params: translation RMSE varies hugely across trials (7.9 m to
   2877 m), but **rotation RMSE stays 100-170 degrees in every single trial** with no visible
   trend against any swept param. No trial beats the baseline on both metrics — config stays
   unchanged (frozen = baseline), matching FAST-LIO2's own "no trial beats baseline on both"
   precedent, just far more extreme here.
5. **Held-out evaluation on exp16 and exp18** (frozen config, unchanged): both also
   catastrophically diverge (exp16: ATE trans RMSE 2297 m, rot RMSE 141.7 deg, status
   incomplete; exp18: ATE trans RMSE 286.5 m, rot RMSE 147.2 deg, status incomplete) — the
   same rotation-failure pattern, a third time, on different sequences.

**Diagnosis (not yet confirmed — the next action item):** the total absence of any trend in
rotation RMSE across 9 different parameter configurations and 3 different sequences points at
something the sweep's params can't reach — most plausibly the Madgwick orientation adapter's
accel-based tilt correction, which assumes near-static conditions to treat the accelerometer
as a gravity reference. This handheld, fast-moving rig genuinely violates that assumption
during motion, and the resulting bad roll/pitch feeds into `mapOptmization`'s pose graph via
`imuRPYWeight`. **This is exactly the failure mode phase-1 manual/hypothesis-driven
investigation exists to catch before a sweep** — its absence here (a decision confirmed with
the user this session) has a direct, now-visible cost.

**Next action for whoever picks this up:**
1. Root-cause the rotation failure — start by disabling the Madgwick adapter's influence
   (e.g. temporarily zero `imuRPYWeight` or feed a fixed identity quaternion) and see if
   rotation RMSE improves; if it does, that confirms the adapter as the cause and the real fix
   is either a better filter (a proper EKF-based AHRS, or accepting that a lightweight
   complementary/Madgwick filter can't handle this rig's dynamics) or reducing its influence
   on the pose graph. If disabling it does *not* fix rotation, look elsewhere (extrinsics,
   `Horizon_SCAN` mismatch degrading features — both flagged as unverified assumptions in
   `docs/methods.md`).
2. Once fixed, this method still needs the phase-1 manual tuning it skipped, then a proper
   phase-2 sweep bounded by that, before its results can be trusted for cross-method
   comparison — treat the current sweep/held-out results as informative about the bug, not as
   this method's real performance.
3. Only then: merge to `main` (confirm with the user first, per this repo's convention).

## Benchmark protocol

Normative document: [docs/protocol.md](docs/protocol.md) — read it, don't re-derive it here.
Covers: online-odometry scope, data split, frames/inputs, gap-aware metrics (ATE/RPE
definitions, association, alignment, coverage), reliability/compute reporting, and the
two-phase tuning process. `configs/eval/default.yaml` holds the frozen evaluation parameters;
`src/lio_benchmark/evaluation.py` is the implementation.

## Deliverables and structure

| Path | Purpose |
|---|---|
| README.md | Scope, setup, quick start, status |
| HANDOFF.md | This file — continuation state |
| .devcontainer/, docker/ | Per-method dev environments and images, one per method |
| manifests/ | Dataset files, hashes, revisions, split |
| configs/ | Per-method baseline/frozen configs; `configs/eval/` shared evaluation params |
| adapters/ | Per-method input/output conversion, each with real unit tests |
| scripts/ | Download, inspect, run, tune, evaluate, log, report — reuse across methods |
| src/lio_benchmark/ | Shared library: manifest, download, evaluation, tracking, CLI |
| tests/ | Hashing, download, manifest, frames, trajectory, evaluator, adapters, tracking |
| docs/ | protocol (normative), dataset (measured facts), methods (per-method notes and
integration decisions), journal (chronological experiment log) |
| results/ | Curated publishable tables/plots (none yet — needs ≥2 methods) |

## Next steps

1. ~~Foundation~~, ~~FAST-LIO2 baseline/tuning/held-out eval~~ — done, see above.
2. **LIO-SAM: root-cause the rotation failure** — see "LIO-SAM: status and open issue" above.
   Not mergeable until fixed; not usable for cross-method comparison until then either.
3. Add GLIM, DLIO, original FAST-LIO, RTAB-Map ICP+IMU through the same interface. Resolve
   LOAM's implementation ambiguity or drop it with a stated reason (`docs/methods.md`
   "Exclusions" section — currently empty).
4. Once ≥2 methods have frozen configs and trustworthy held-out results: first cross-method
   comparison, `results/`, `lio-bench report`.

Ask only for information that materially blocks the next action. Do not claim benchmark
rankings before ≥2 methods have real, trustworthy runs — LIO-SAM's current numbers reflect an
unresolved bug, not the method's actual performance.

## Suggested skills

- **handoff**: update this document after substantive progress (a method fully integrated and
  merged, a protocol change, a milestone).
- **domain-modeling**: if defining CONTEXT.md, terminology or architecture decision records.

Read `docs/methods.md`, `docs/protocol.md` and `docs/journal.md` before acting — they carry
the actual decisions and measured facts; this file is a pointer and a punch list, not the
source of truth.
